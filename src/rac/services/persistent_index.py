"""Persistent corpus index (ADR-100, ADR-101) — the single-node-scale read path.

This module is the Movement-B replacement for "walk + parse + graph + tokenise,
every call". It builds an on-disk, memory-mapped index once, refreshes it by
changeset, and serves warm queries whose cost is bound by query selectivity, not
corpus size.

The contract, in the terms the decisions bind us to:

- **Analyzer parity is the contract (ADR-100).** Index-served output is
  byte-identical to the fresh walk-and-parse path for any corpus state. We do not
  re-implement the ranker: candidate generation prunes the corpus to a provably
  complete superset of the true match set, and the *frozen* matcher/scorer from
  ``rac.services.resolve`` (``_match_entry`` / ``_bm25f`` / ``_competition_ranks``
  / RRF fusion) runs over the candidates with corpus-global BM25 statistics
  reconstructed from stored aggregates. Because the statistics are global and the
  matcher is the frozen one, byte-parity follows.
- **Candidate pruning is provably complete for ADR-037 semantics.** Matching is
  equality-or-prefix, AND across terms, over a *document-level* term index (a term
  is in a document's posting list iff it appears in any of the five fields). The
  candidate set for a query is the intersection, over the query's distinct terms,
  of the union of postings across each term's prefix range — exactly the set of
  documents in which every term matches somewhere, i.e. the true match set (so
  trivially a superset). The union sizes are also the *union-over-fields document
  frequencies* BM25F consumes (per the AUDIT CORRECTION in the search-resolve
  brief): df is per-document, keyed by term, and the single global IDF derives
  from it — never a per-field df.
- **Bytes decide; mtime is a hint, never authority (ADR-100).** Refresh
  enumerates with stat-only calls, selects candidates whose ``(size, mtime_ns)``
  differ from the manifest (plus path-set adds/removes), reads and hashes only the
  candidates, and re-indexes only files whose content hash actually changed. A
  byte edit that preserves both size and mtime is invisible to the stat hint
  outside ``verify=True``; ``verify=True`` re-hashes everything and recovers the
  strict per-call byte guarantee. The stored authority is always the sha256.
- **Recency is git-keyed, not content-keyed (ADR-101).** The last-committed
  timestamp is materialised per document and invalidated by the indexed git head,
  not the content manifest — an amend/rebase changes the answer without changing
  any artifact's bytes. One ``git log`` walk per refresh replaces one subprocess
  per match.
- **Disposable, never authoritative (ADR-100).** The files in git are the truth.
  The index carries a pinned schema version; any corruption, version mismatch, or
  deletion degrades to a full rebuild — a latency cost, never an answer change.
- **Determinism (ADR-002).** Identical corpus bytes → byte-identical index files:
  everything is sorted, and the multiprocessing chunk merge is keyed by document
  id so it is order-stable regardless of worker completion order. (The binary
  arrays are written in the host's native byte order; the index is a disposable,
  per-machine derived structure, so this is not a portability contract.)

Isolation posture (mirrors ``rac.services.relationships`` / ``resolve``): this
module lives under ``rac.services`` and imports no ``mcp``/``rac.mcp`` SDK, no
network module, and no write service. Git is reached through ``subprocess`` only,
the same offline read-only touchpoint ``recency.py`` uses (ADR-043/ADR-045).
"""

from __future__ import annotations

import hashlib
import json
import mmap
import os
import shutil
import struct
import subprocess
from array import array
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rac.core.artifacts import spec_for
from rac.core.classification import classify
from rac.core.fs import find_markdown_files
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.limits import (
    MAX_TRAVERSAL_DEPTH,
    MAX_TRAVERSAL_FRONTIER,
    MAX_TRAVERSAL_WORK,
)
from rac.core.markdown import parse_file
from rac.core.models import SearchSection
from rac.core.relationship_types import edge_spec
from rac.services.index import IndexEntry
from rac.services.relationships import (
    ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS,
    ISSUE_TARGET_NOT_FOUND,
    IncomingReferences,
    Neighborhood,
    NeighborhoodNode,
    OutgoingReferences,
    Relationship,
    _relationship_order,
    extract_relationships_full,
    incoming_references,
    outgoing_references,
)
from rac.services.resolve import (
    _GRAPH_WEIGHT,
    _RRF_K,
    OUTCOME_DUPLICATE,
    OUTCOME_NOT_FOUND,
    OUTCOME_RESOLVED,
    ResolutionResult,
    ResolvedArtifact,
    SearchResult,
    _bm25f,
    _competition_ranks,
    _field_tokens,
    _Match,
    _match_entry,
    _score_evidence,
    tokenize,
)

# Bumping this discards every existing index (a mismatch on load is a miss and
# forces a full rebuild), so a format change can never rehydrate stale bytes.
SCHEMA_VERSION = "1"

# The five scorable fields, in the ADR-078 boost order. Mirrors resolve._FIELD_BOOSTS
# keys; the per-field total token length aggregate below is what BM25F's mean field
# length divides, so this order is the one the scorer expects.
FIELDS: tuple[str, ...] = ("id", "title", "path", "heading", "body")

# Above this document count a cold build fans parsing across processes; below it
# the pool overhead is not worth paying and the build stays in-process (also keeps
# the determinism/parity tests single-process and simple).
_PARALLEL_THRESHOLD = 2000

_HEADER = "header.json"
_MANIFEST = "manifest.json"


class PersistentIndexError(Exception):
    """The on-disk index is missing, corrupt, or a schema mismatch — a miss.

    Callers treat this as "rebuild from the corpus"; per ADR-100 it is only ever a
    latency cost, never an answer change.
    """


# ---------------------------------------------------------------------------
# Cold build: one parallel walk + parse + tokenise pass, written atomically.
# ---------------------------------------------------------------------------


def _relpath(root: Path, path: Path) -> str:
    """Repository-relative POSIX path — the stable manifest / doc-store key."""
    return path.relative_to(root).as_posix()


def _parse_one(root_str: str, doc_id: int, path_str: str) -> dict:
    """Parse, classify, tokenise and extract one artifact into a build record.

    Pure and deterministic (ADR-002). The heavy per-file work — parse, classify,
    the ADR-037 tokeniser over all five fields — happens exactly once here, at
    index time, never per query. Resolution of relationship targets is *not* done
    here: it needs the whole-corpus identity index and is folded in the main
    process so resolved edges match ``relationships_from_corpus`` byte-for-byte.
    """
    root = Path(root_str)
    path = Path(path_str)
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()  # confirming manifest hash, computed in-worker
    st = path.stat()
    product = parse_file(path_str)
    artifact_type = classify(product).type
    spec = spec_for(artifact_type)  # None for Unknown documents
    ident = artifact_identifier(product, spec, path_str)
    aliases = artifact_identifiers(product, spec, path_str)
    entry = IndexEntry(
        id=ident,
        type=artifact_type,
        title=product.title,
        path=path_str,
        aliases=aliases,
        search_sections=product.search_sections,
    )
    # The frozen tokeniser, reused (ADR-037): the same per-field token vectors the
    # scorer consumes, so stored postings and query-time re-tokenisation agree.
    field_tokens = _field_tokens(entry)
    field_lengths = {name: len(field_tokens[name]) for name in FIELDS}
    # A term is in a document's posting list iff it appears in ANY field — the
    # union-over-fields, document-level index that makes df per-document.
    distinct = sorted({tok for name in FIELDS for tok in field_tokens[name]})
    extracted = extract_relationships_full(product, spec) if spec is not None else {}
    return {
        "doc_id": doc_id,
        "relpath": _relpath(root, path),
        "id": ident,
        "type": artifact_type,
        "title": product.title,
        "aliases": aliases,
        "sections": [[sec.heading, list(sec.lines)] for sec in product.search_sections],
        "field_lengths": field_lengths,
        "tokens": distinct,
        "extracted": {section: list(refs) for section, refs in extracted.items()},
        "known": spec is not None,
        "sha256": sha,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
    }


def _parse_chunk(payload: tuple[str, list[tuple[int, str]]]) -> list[dict]:
    """Worker entrypoint: parse a contiguous slice of the sorted file list."""
    root_str, items = payload
    return [_parse_one(root_str, doc_id, path_str) for doc_id, path_str in items]


def _chunk(items: list[tuple[int, str]], parts: int) -> list[list[tuple[int, str]]]:
    """Split the sorted (doc_id, path) list into ``parts`` contiguous slices.

    Contiguous slices of the already-sorted list keep global document order, so
    reassembly by doc_id is order-stable no matter which worker finishes first.
    """
    if parts <= 1:
        return [items]
    size = (len(items) + parts - 1) // parts
    return [items[i : i + size] for i in range(0, len(items), size)] or [[]]


def _resolution_index(records: list[dict]) -> dict[str, list[str]]:
    """``{casefold(identifier) -> [relpath, ...]}`` over every document.

    Reproduces ``relationships._build_resolution_index``: canonical id plus legacy
    aliases, every document included (Unknown too, so they can be edge *targets*),
    in document order. Reference resolution reads this map exactly as the
    relationship graph does, so resolved edges — and thus inbound counts and the
    neighbourhood — match ``relationships_from_corpus`` byte-for-byte.
    """
    index: dict[str, list[str]] = {}
    for rec in records:
        for alias in rec["aliases"]:
            index.setdefault(alias.casefold(), []).append(rec["relpath"])
    return index


def _resolved_edges(
    records: list[dict], resolution: dict[str, list[str]]
) -> list[tuple[int, int, str]]:
    """Resolved, unique, non-self, non-external edges as ``(src_id, dst_id, section)``.

    The resolution precedence mirrors ``relationships_from_corpus``: external
    sections (ADR-087 — related tickets, verified by, applies to) declare no
    in-corpus edge; otherwise a reference resolves iff it maps to exactly one
    document that is not the source itself. Edges are emitted in document order,
    then section order, then reference order — the deterministic order the graph
    contract pins.
    """
    id_by_relpath = {rec["relpath"]: rec["doc_id"] for rec in records}
    edges: list[tuple[int, int, str]] = []
    for rec in records:
        if not rec["known"]:
            continue
        src = rec["relpath"]
        for section, refs in rec["extracted"].items():
            spec = edge_spec(section)
            if spec is not None and spec.external:
                continue
            for ref in refs:
                targets = resolution.get(ref.casefold(), [])
                if len(targets) != 1:
                    continue  # not-found or ambiguous — no resolved edge
                target = targets[0]
                if target == src:
                    continue  # self-reference — no inbound edge
                edges.append((rec["doc_id"], id_by_relpath[target], section))
    return edges


def _run_git(args: list[str], cwd: str) -> str | None:
    """Run git read-only, returning stdout text or None when it cannot answer.

    The same offline, ``.git``-non-mutating touchpoint ``recency.py`` uses
    (ADR-043/ADR-045). Never raises across the boundary.
    """
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, check=False, text=True
        )
    except (FileNotFoundError, NotADirectoryError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _git_head(root: str) -> str | None:
    """The indexed git head (``git rev-parse HEAD``), or None outside a repo."""
    out = _run_git(["rev-parse", "HEAD"], root)
    return out.strip() if out is not None else None


def _parse_stamp(raw: str) -> str | None:
    """Normalise a git ``%cI`` stamp to the same ISO string recency emits."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _git_last_committed(root: str, relpaths: Iterable[str]) -> dict[str, str]:
    """``{relpath -> ISO last-committed}`` for the current head, one subprocess.

    A single ``git log --name-only`` walk from HEAD (ADR-101 R4): newest commit
    first, so the first time a path is seen is its last-committed time. This
    replaces one ``git log -1`` fork per matched path with one walk per refresh.
    The stored value is normalised exactly as ``recency._last_committed(...)``
    would return it (parse then ``isoformat``), so the parity assertion against
    the live git answer holds.
    """
    wanted = set(relpaths)
    if not wanted:
        return {}
    toplevel = _run_git(["rev-parse", "--show-toplevel"], root)
    if toplevel is None:
        return {}
    repo_root = Path(toplevel.strip())
    try:
        prefix = Path(root).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return {}
    prefix = "" if prefix == "." else prefix
    log = _run_git(["log", "--format=%x00%cI", "--name-only", "--no-renames"], str(repo_root))
    if log is None:
        return {}
    result: dict[str, str] = {}
    current: str | None = None
    for line in log.splitlines():
        if line.startswith("\x00"):
            current = line[1:]
            continue
        if not line or current is None:
            continue
        # ``line`` is a repository-relative path git touched in ``current``.
        if prefix:
            if not line.startswith(prefix + "/"):
                continue
            rel = line[len(prefix) + 1 :]
        else:
            rel = line
        if rel in wanted and rel not in result:
            stamp = _parse_stamp(current)
            if stamp is not None:
                result[rel] = stamp
    return result


def _sha256(path: Path) -> str:
    """SHA-256 of a file's bytes — the confirming authority (never mtime)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sort_key(root: Path, relpath: str) -> tuple[str, ...]:
    """Sort key reproducing ``find_markdown_files`` (sorted PosixPath) order."""
    return (root / relpath).parts


# ---------------------------------------------------------------------------
# Assembly + serialisation (main process only).
# ---------------------------------------------------------------------------


@dataclass
class _BuildData:
    """The fully-assembled index contents, ready to serialise."""

    records: list[dict]
    field_totals: dict[str, int]
    postings: dict[str, list[int]]
    edges: list[tuple[int, int, str]]
    edge_sections: list[str]
    inbound: list[int]
    recency: list[str | None]
    manifest: list[tuple[str, str, int, int]]  # (relpath, sha256, size, mtime_ns)
    git_head: str | None
    root: str


def _assemble(
    root: str, records: list[dict], manifest: list[tuple[str, str, int, int]]
) -> _BuildData:
    """Fold per-file build records into whole-corpus index structures.

    No artifact bytes are read here (the manifest — with its confirming hashes — is
    supplied by the caller, which alone knows which files it actually read). The
    only I/O is one ``git log`` walk for recency (ADR-101).
    """
    records.sort(key=lambda r: r["doc_id"])
    n = len(records)

    field_totals = {name: 0 for name in FIELDS}
    postings: dict[str, list[int]] = {}
    for rec in records:
        for name in FIELDS:
            field_totals[name] += rec["field_lengths"][name]
        doc_id = rec["doc_id"]
        for tok in rec["tokens"]:  # already sorted-distinct per document
            postings.setdefault(tok, []).append(doc_id)

    resolution = _resolution_index(records)
    edges = _resolved_edges(records, resolution)
    edge_sections = sorted({section for _, _, section in edges})
    inbound = [0] * n
    for _src, dst, _section in edges:
        inbound[dst] += 1

    git_head = _git_head(root)
    last_by_rel = _git_last_committed(root, (rec["relpath"] for rec in records))
    recency: list[str | None] = [last_by_rel.get(rec["relpath"]) for rec in records]

    return _BuildData(
        records=records,
        field_totals=field_totals,
        postings=postings,
        edges=edges,
        edge_sections=edge_sections,
        inbound=inbound,
        recency=recency,
        manifest=sorted(manifest),
        git_head=git_head,
        root=root,
    )


def _write_blob(index_dir: Path, name: str, chunks: list[bytes]) -> None:
    """Write a ``name.dat`` blob plus a ``name.off`` byte-offset array (u64)."""
    offsets = [0]
    cursor = 0
    with open(index_dir / f"{name}.dat", "wb") as handle:
        for chunk in chunks:
            handle.write(chunk)
            cursor += len(chunk)
            offsets.append(cursor)
    (index_dir / f"{name}.off").write_bytes(array("Q", offsets).tobytes())


def _serialise(index_dir: Path, data: _BuildData) -> None:
    """Write the whole index to ``index_dir`` (an existing empty temp directory)."""
    records = data.records
    n = len(records)

    # Term dictionary (sorted by UTF-8 bytes → contiguous prefix ranges) + the
    # document-level postings that back both candidate generation and df.
    terms = sorted(data.postings, key=lambda t: t.encode("utf-8"))
    _write_blob(index_dir, "terms", [t.encode("utf-8") for t in terms])
    _write_blob(index_dir, "post", [array("I", data.postings[t]).tobytes() for t in terms])

    # Document store: everything needed to reconstruct an IndexEntry and its
    # snippet without touching the corpus, plus the declared relationship refs so a
    # surviving document can be re-spliced without a re-read.
    docrecs: list[bytes] = []
    for i, rec in enumerate(records):
        payload = {
            "relpath": rec["relpath"],
            "id": rec["id"],
            "type": rec["type"],
            "title": rec["title"],
            "aliases": rec["aliases"],
            "sections": rec["sections"],
            "extracted": rec["extracted"],
            "known": rec["known"],
            "inbound": data.inbound[i],
            "recency": data.recency[i],
        }
        docrecs.append(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    _write_blob(index_dir, "docrec", docrecs)

    # CSR adjacency, both directions. Out-edges carry the section (as a small vocab
    # id) so the neighbourhood walk reconstructs the exact relationship rank.
    section_id = {section: i for i, section in enumerate(data.edge_sections)}
    out_by_src: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    in_by_dst: list[list[int]] = [[] for _ in range(n)]
    for src, dst, section in data.edges:
        out_by_src[src].append((dst, section_id[section]))
        in_by_dst[dst].append(src)
    _write_blob(
        index_dir,
        "cout",
        [b"".join(struct.pack("<II", dst, sid) for dst, sid in out_by_src[i]) for i in range(n)],
    )
    _write_blob(index_dir, "cin", [array("I", in_by_dst[i]).tobytes() for i in range(n)])

    header = {
        "schema_version": SCHEMA_VERSION,
        "n": n,
        "n_terms": len(terms),
        "fields": list(FIELDS),
        "field_totals": data.field_totals,
        "edge_sections": data.edge_sections,
        "git_head": data.git_head,
        "root": data.root,
    }
    (index_dir / _HEADER).write_text(json.dumps(header), encoding="utf-8")
    manifest = {"entries": [list(row) for row in data.manifest]}
    (index_dir / _MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")


def _atomic_replace(tmp_dir: Path, index_dir: Path) -> None:
    """Move a freshly-built temp index into place (build-to-temp, then rename)."""
    if index_dir.exists():
        shutil.rmtree(index_dir)
    os.replace(tmp_dir, index_dir)


def _write_index(index_dir: str, data: _BuildData) -> None:
    """Serialise ``data`` to a sibling temp dir and atomically swap it into place."""
    tmp_dir = Path(f"{index_dir}.tmp-{os.getpid()}")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        _serialise(tmp_dir, data)
        _atomic_replace(tmp_dir, Path(index_dir))
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def build_index(root: str, index_dir: str, workers: int | None = None) -> None:
    """Cold build: one parallel walk + parse + tokenise pass, written atomically.

    Files arrive in ``find_markdown_files`` sorted order and are assigned document
    ids by that order, so the store matches ``build_repository_index`` order and
    reassembly after the parallel parse is order-stable. The finished index is
    built into a sibling temp directory and ``os.replace``d into place, so a reader
    never observes a half-written index (ADR-100 disposability).
    """
    paths = find_markdown_files(root)
    items = [(i, str(path)) for i, path in enumerate(paths)]

    if workers is None:
        workers = os.cpu_count() or 1
    records: list[dict]
    if workers > 1 and len(items) >= _PARALLEL_THRESHOLD:
        records = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for chunk_records in pool.map(
                _parse_chunk, [(root, chunk) for chunk in _chunk(items, workers)]
            ):
                records.extend(chunk_records)
    else:
        records = [_parse_one(root, doc_id, path_str) for doc_id, path_str in items]

    # Cold build is the one path that must read every artifact's bytes; the
    # confirming manifest hash is computed once, in the parse worker (parallel),
    # from the same read — never a second pass over the corpus. Refresh reuses
    # these hashes for survivors.
    manifest = [(rec["relpath"], rec["sha256"], rec["size"], rec["mtime_ns"]) for rec in records]

    _write_index(index_dir, _assemble(root, records, manifest))


# ---------------------------------------------------------------------------
# Memory-mapped reader.
# ---------------------------------------------------------------------------


class _Blob:
    """A ``name.dat`` blob mapped lazily, indexed by an in-memory u64 offset array.

    The large blob (postings, term bytes, document records, CSR runs) is
    memory-mapped and sliced on demand — loading the index never pulls it fully
    into Python, and never reads the corpus. The offset array is small (one u64 per
    record) and is loaded eagerly for O(1) random access.
    """

    def __init__(self, index_dir: Path, name: str) -> None:
        self._offsets: array[int] = array("Q")
        self._offsets.frombytes((index_dir / f"{name}.off").read_bytes())
        dat_path = index_dir / f"{name}.dat"
        size = dat_path.stat().st_size
        self._file = open(dat_path, "rb")
        self._mm: mmap.mmap | None = None
        if size > 0:
            self._mm = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)

    def count(self) -> int:
        return len(self._offsets) - 1

    def raw(self, i: int) -> bytes:
        start = self._offsets[i]
        end = self._offsets[i + 1]
        if self._mm is None or end == start:
            return b""
        return self._mm[start:end]

    def close(self) -> None:
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        self._file.close()


def load_index(index_dir: str) -> PersistentIndex:
    """Open an index directory with mmap; never reads the corpus.

    Raises :class:`PersistentIndexError` on a missing directory, a schema-version
    mismatch, or a corrupt/short-read header — every one is a "miss" the caller
    turns into a rebuild (ADR-100).
    """
    directory = Path(index_dir)
    try:
        header = json.loads((directory / _HEADER).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PersistentIndexError(f"unreadable index header: {exc}") from exc
    if header.get("schema_version") != SCHEMA_VERSION:
        raise PersistentIndexError(f"schema mismatch: {header.get('schema_version')!r}")
    try:
        return PersistentIndex(directory, header)
    except (OSError, ValueError, KeyError, struct.error) as exc:
        raise PersistentIndexError(f"corrupt index: {exc}") from exc


def open_index(root: str, index_dir: str, *, rebuild: bool = True) -> PersistentIndex:
    """Load ``index_dir``; on any miss (missing/corrupt/schema) rebuild then load.

    The clean-rebuild fallback ADR-100 requires: a disposable index degrades to a
    cold build, a latency cost only.
    """
    try:
        return load_index(index_dir)
    except PersistentIndexError:
        if not rebuild:
            raise
        build_index(root, index_dir)
        return load_index(index_dir)


class PersistentIndex:
    """A loaded, memory-mapped corpus index serving warm, query-bound reads."""

    def __init__(self, directory: Path, header: dict) -> None:
        self._dir = directory
        self._header = header
        self.n: int = header["n"]
        self.field_totals: dict[str, int] = header["field_totals"]
        self.edge_sections: list[str] = header["edge_sections"]
        self.git_head: str | None = header.get("git_head")
        self._root: str = header["root"]
        self._terms = _Blob(directory, "terms")
        self._post = _Blob(directory, "post")
        self._docrec = _Blob(directory, "docrec")
        self._cout = _Blob(directory, "cout")
        self._cin = _Blob(directory, "cin")
        self._docrec_cache: dict[int, dict] = {}
        # Per-generation derived lookups the four index seams would otherwise
        # rebuild over the whole corpus on every call. A loaded index is immutable
        # until a refresh swaps its mapped state, so each is built once, memoised,
        # and dropped in ``_adopt`` — warm repeats reuse one build and stay
        # query-bound (O(query), not O(corpus)) instead of re-deriving an O(N)/O(E)
        # structure per call. Byte-identical either way: the same construction the
        # frozen path does once per call, done once per generation.
        self._entries_cache: list[IndexEntry] | None = None
        self._relationships_cache: list[Relationship] | None = None
        self._recency_cache: dict[str, str | None] | None = None
        # resolve_in_index's per-call identity scan, folded into one map:
        # ``{casefold(alias) -> [doc_id]}`` (one doc_id per document per distinct
        # casefolded alias). A lookup replaces the O(N) alias scan get_artifact /
        # get_related pay to resolve one id.
        self._resolution_cache: dict[str, list[int]] | None = None
        # ``{path -> (id, type, title)}`` — the identity map get_related builds
        # inline over every entry each call, and the neighbourhood walk reads.
        self._identity_cache: dict[str, tuple[str, str, str | None]] | None = None
        # The full relationship list grouped by endpoint, so get_related touches
        # only the requested node's edges instead of scanning every edge:
        # ``{source_path -> [rel]}`` for outgoing, ``{resolved_path -> [rel]}`` for
        # incoming (resolved edges only). Order within each group is the frozen
        # ``relationships()`` order, so the shaped result is byte-identical.
        self._rels_by_source_cache: dict[str, list[Relationship]] | None = None
        self._rels_by_resolved_cache: dict[str, list[Relationship]] | None = None
        # Undirected resolved-edge adjacency ``{path -> [(neighbor, rank)]}`` the
        # neighbourhood BFS expands, built once so a depth>1 walk touches only the
        # visited frontier, never the whole edge list.
        self._adjacency_cache: dict[str, list[tuple[str, int]]] | None = None

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        for blob in (self._terms, self._post, self._docrec, self._cout, self._cin):
            blob.close()

    def __enter__(self) -> PersistentIndex:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- document store ----------------------------------------------------

    def _record(self, doc_id: int) -> dict:
        cached = self._docrec_cache.get(doc_id)
        if cached is None:
            cached = json.loads(self._docrec.raw(doc_id))
            self._docrec_cache[doc_id] = cached
        return cached

    def _path_for(self, relpath: str) -> str:
        # Reconstruct the exact path string ``find_markdown_files(root)`` yielded,
        # so index-served entries carry byte-identical paths to the fresh walk.
        return str(Path(self._root) / relpath)

    def _entry(self, doc_id: int) -> IndexEntry:
        rec = self._record(doc_id)
        return IndexEntry(
            id=rec["id"],
            type=rec["type"],
            title=rec["title"],
            path=self._path_for(rec["relpath"]),
            aliases=list(rec["aliases"]),
            search_sections=[
                SearchSection(heading=heading, lines=list(lines))
                for heading, lines in rec["sections"]
            ],
            inbound_count=rec["inbound"],
        )

    def entries(self) -> list[IndexEntry]:
        """Every document as an :class:`IndexEntry`, in ``build_repository_index``
        order — structurally identical to what the fresh index produces.

        Memoised for the life of the mapped state (dropped on refresh): the server
        calls this once per resolve/lookup, so warm repeats reuse the built list."""
        if self._entries_cache is None:
            self._entries_cache = [self._entry(i) for i in range(self.n)]
        return self._entries_cache

    # -- resolution (exact-id lookup) --------------------------------------

    def _resolution_map(self) -> dict[str, list[int]]:
        """``{casefold(alias) -> [doc_id, ...]}`` — the id→document lookup.

        The same document set ``resolve_in_index`` finds by scanning every entry's
        aliases per call, precomputed once for the life of the mapped state. Each
        document contributes its ``doc_id`` once per *distinct* casefolded alias, so
        a key never lists the same document twice (two aliases of one document that
        casefold alike still count it once, exactly as ``resolve_in_index``'s
        ``any(...)`` matches an entry once). Documents are visited in id order, so a
        key's list is in document order — the order ``resolve_in_index`` produces
        before it sorts duplicate paths.
        """
        if self._resolution_cache is None:
            index: dict[str, list[int]] = {}
            for i in range(self.n):
                for alias in {a.casefold() for a in self._record(i)["aliases"]}:
                    index.setdefault(alias, []).append(i)
            self._resolution_cache = index
        return self._resolution_cache

    def resolve(self, artifact_id: str) -> ResolutionResult:
        """Resolve ``artifact_id`` — byte-identical to ``resolve_in_index`` over
        ``entries()``, via the ``{alias -> doc_id}`` map instead of an O(N) scan.

        Same three outcomes and the same tie/duplicate handling: no match is
        not-found, more than one distinct document is a duplicate (paths sorted,
        never resolved by order), exactly one is resolved. Only the matched
        documents are materialised, so a hit is O(1) plus the (tiny) match set.
        """
        wanted = artifact_id.strip().casefold()
        doc_ids = self._resolution_map().get(wanted, [])
        if not doc_ids:
            return ResolutionResult(artifact_id=artifact_id, outcome=OUTCOME_NOT_FOUND)
        if len(doc_ids) > 1:
            return ResolutionResult(
                artifact_id=artifact_id,
                outcome=OUTCOME_DUPLICATE,
                duplicate_paths=sorted(self._entry(i).path for i in doc_ids),
            )
        return ResolutionResult(
            artifact_id=artifact_id,
            outcome=OUTCOME_RESOLVED,
            artifact=ResolvedArtifact.from_entry(self._entry(doc_ids[0])),
        )

    # -- term dictionary / postings ---------------------------------------

    def _term_bytes(self, i: int) -> bytes:
        return self._terms.raw(i)

    def _lower_bound(self, key: bytes) -> int:
        lo, hi = 0, self._terms.count()
        while lo < hi:
            mid = (lo + hi) // 2
            if self._term_bytes(mid) < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _postings(self, i: int) -> array[int]:
        ids: array[int] = array("I")
        ids.frombytes(self._post.raw(i))
        return ids

    def _docset_for_prefix(self, term: str) -> set[int]:
        """Documents matching ``term`` by equality-or-prefix, over any field.

        The union of postings across the contiguous term-dictionary range whose
        entries start with ``term`` (ADR-037 prefix, done as a byte-range scan —
        never a compiled regex over untrusted query input, ADR-065). The size of
        this set is exactly the union-over-fields document frequency BM25F needs.
        """
        key = term.encode("utf-8")
        docs: set[int] = set()
        i = self._lower_bound(key)
        count = self._terms.count()
        while i < count and self._term_bytes(i).startswith(key):
            docs.update(self._postings(i))
            i += 1
        return docs

    # -- search ------------------------------------------------------------

    def search_entries(self, query: str, artifact_type: str | None = None) -> SearchResult:
        """Search the index with ``rac find`` semantics — byte-identical to
        ``resolve.search_index`` over a fresh ``build_repository_index``.

        Candidate generation prunes to the exact match set (a superset, trivially),
        then the frozen matcher and scorer run over the candidates with global BM25
        statistics reconstructed from stored aggregates. Because the statistics are
        corpus-global (n, per-field mean length, and the document-level df) and the
        matcher/fusion are the frozen ``resolve`` functions, the matched set,
        ranking, snippets, evidence and inbound signal reproduce exactly.
        """
        terms = tokenize(query)
        if not terms:  # empty / all-punctuation query — a valid empty result
            return SearchResult(query=query, artifact_type=artifact_type, matches=[])

        distinct = list(dict.fromkeys(terms))
        per_term = {t: self._docset_for_prefix(t) for t in distinct}
        # AND across terms: intersection of the per-term document sets.
        candidate_ids: set[int] = set(per_term[distinct[0]])
        for t in distinct[1:]:
            candidate_ids &= per_term[t]
        # df is the union-over-fields, per-document count keyed by term (the AUDIT
        # CORRECTION pin) — the same value _corpus_stats computes over the corpus.
        df = {t: len(per_term[t]) for t in distinct}

        return self._score(query, terms, df, artifact_type, sorted(candidate_ids))

    def _score(
        self,
        query: str,
        terms: list[str],
        df: dict[str, int],
        artifact_type: str | None,
        candidate_ids: list[int],
    ) -> SearchResult:
        """The frozen ``search_index`` tail, over candidates, with injected stats.

        This mirrors ``resolve.search_index`` from the match loop through the fused
        sort; the ONLY substitution is corpus-global ``n`` / df / avglen from stored
        aggregates instead of a full re-tokenising pass. Every arithmetic primitive
        (``_bm25f``, ``_competition_ranks``, ``_score_evidence``, the RRF fusion and
        the rounded sort key) is the frozen one, so the floats match the goldens
        bit-for-bit.
        """
        n = self.n
        avglen = {name: (self.field_totals[name] / n if n else 0.0) for name in FIELDS}

        matched: list[tuple[IndexEntry, _Match]] = []
        cand_tokens: dict[str, dict[str, list[str]]] = {}
        for doc_id in candidate_ids:
            entry = self._entry(doc_id)
            if artifact_type is not None and entry.type != artifact_type:
                continue
            match, field_tokens = _match_entry(entry, terms)
            cand_tokens[entry.path] = field_tokens
            if match is not None:
                matched.append((entry, match))
        if not matched:
            return SearchResult(query=query, artifact_type=artifact_type, matches=[])

        bm25 = {e.path: _bm25f(cand_tokens[e.path], terms, n, df, avglen) for e, _ in matched}
        inbound = {e.path: float(getattr(e, "inbound_count", 0)) for e, _ in matched}
        lexical_rank = _competition_ranks(bm25)
        graph_rank = _competition_ranks(inbound)
        fused = {
            path: 1.0 / (_RRF_K + lexical_rank[path]) + _GRAPH_WEIGHT / (_RRF_K + graph_rank[path])
            for path in bm25
        }
        matched.sort(key=lambda em: (-round(fused[em[0].path], 12), em[0].path))
        return SearchResult(
            query=query,
            artifact_type=artifact_type,
            matches=[
                ResolvedArtifact.from_entry(
                    e,
                    section=m.section,
                    snippet=m.snippet,
                    evidence=_score_evidence(
                        m,
                        fused=fused[e.path],
                        bm25=bm25[e.path],
                        lexical_rank=lexical_rank[e.path],
                        graph_rank=graph_rank[e.path],
                        inbound=int(inbound[e.path]),
                    ),
                )
                for e, m in matched
            ],
        )

    # -- graph -------------------------------------------------------------

    def inbound_counts(self) -> dict[str, int]:
        """``{path -> inbound resolved-edge count}`` (0-count paths absent).

        Byte-identical to ``relationships.inbound_counts_from_corpus`` — the same
        resolved, non-self edge definition, counted with multiplicity, materialised
        at build time and read here as a column.
        """
        counts: dict[str, int] = {}
        for i in range(self.n):
            rec = self._record(i)
            if rec["inbound"]:
                counts[self._path_for(rec["relpath"])] = rec["inbound"]
        return counts

    def relationships(self) -> list[Relationship]:
        """Every declared reference as a :class:`Relationship` — byte-identical to
        ``relationships.relationships_from_corpus`` over the same corpus.

        The CSR adjacency stores only resolved, non-self, non-external edges (all
        the graph walk needs); the ``get_related`` ``outgoing``/``incoming`` shapes
        also need the *unresolved* and *external* declared references and the raw
        reference text, which the CSR discards. Those live in the document store
        (``extracted`` + ``known`` + ``aliases``), so this reconstructs the full
        list from stored data without a corpus read — same document order (sorted
        path), same section order, same reference order, and the same resolution
        precedence (external declares no in-corpus target; otherwise a reference
        resolves iff it maps to exactly one non-self document).

        Memoised for the life of the mapped state (dropped on refresh), so the
        server's get_related seam reuses one reconstruction across warm calls."""
        if self._relationships_cache is not None:
            return self._relationships_cache
        resolution = _resolution_index([self._record(i) for i in range(self.n)])
        rels: list[Relationship] = []
        for i in range(self.n):
            rec = self._record(i)
            if not rec["known"]:
                continue
            src_path = self._path_for(rec["relpath"])
            for section, refs in rec["extracted"].items():
                spec = edge_spec(section)
                external = spec is not None and spec.external
                for ref in refs:
                    if external:
                        rels.append(Relationship(src_path, section, ref, None, None))
                        continue
                    targets = resolution.get(ref.casefold(), [])
                    resolved: str | None = None
                    issue: str | None = None
                    if not targets:
                        issue = ISSUE_TARGET_NOT_FOUND
                    elif len(targets) > 1:
                        issue = ISSUE_TARGET_AMBIGUOUS
                    elif targets == [rec["relpath"]]:
                        issue = ISSUE_SELF_REFERENCE
                    else:
                        resolved = self._path_for(targets[0])
                    rels.append(Relationship(src_path, section, ref, resolved, issue))
        self._relationships_cache = rels
        return rels

    def _identity_by_path(self) -> dict[str, tuple[str, str, str | None]]:
        """``{path -> (id, type, title)}`` over every document (memoised).

        The identity map get_related builds inline over the whole index each call
        and the neighbourhood walk reads for every node it emits. Built once for the
        life of the mapped state so warm calls reuse it instead of re-scanning."""
        if self._identity_cache is None:
            result: dict[str, tuple[str, str, str | None]] = {}
            for i in range(self.n):
                rec = self._record(i)
                result[self._path_for(rec["relpath"])] = (rec["id"], rec["type"], rec["title"])
            self._identity_cache = result
        return self._identity_cache

    def _rels_by_source(self) -> dict[str, list[Relationship]]:
        """``relationships()`` grouped by ``source_path`` (memoised).

        The declared references each artifact owns, keyed by source, in the frozen
        ``relationships()`` order — so slicing a node's group and shaping it is
        byte-identical to filtering the full list, but touches only that node."""
        if self._rels_by_source_cache is None:
            grouped: dict[str, list[Relationship]] = {}
            for rel in self.relationships():
                grouped.setdefault(rel.source_path, []).append(rel)
            self._rels_by_source_cache = grouped
        return self._rels_by_source_cache

    def _rels_by_resolved(self) -> dict[str, list[Relationship]]:
        """Resolved edges from ``relationships()`` grouped by ``resolved_path``.

        The incoming edges pointing at each artifact, in ``relationships()`` order.
        Only uniquely-resolved edges have a ``resolved_path``, so unresolved and
        external declarations — which are never incoming edges — are absent."""
        if self._rels_by_resolved_cache is None:
            grouped: dict[str, list[Relationship]] = {}
            for rel in self.relationships():
                if rel.resolved_path is not None:
                    grouped.setdefault(rel.resolved_path, []).append(rel)
            self._rels_by_resolved_cache = grouped
        return self._rels_by_resolved_cache

    def outgoing(self, source_path: str, *, limit: int | None = None) -> OutgoingReferences:
        """The references ``source_path`` declares — byte-identical to
        ``outgoing_references`` over the full list, but over that node's group only.

        ``outgoing_references`` filters the list to ``source_path`` then groups by
        section; feeding it exactly that node's edges (all with the right source, in
        the same order) yields the identical ``by_section`` / ``total`` / cap."""
        return outgoing_references(
            self._rels_by_source().get(source_path, []), source_path, limit=limit
        )

    def incoming(self, target_path: str, *, limit: int | None = None) -> IncomingReferences:
        """Artifacts whose references resolve to ``target_path`` — byte-identical to
        ``incoming_references`` over the full list, over that node's group only.

        The group holds every edge whose ``resolved_path`` is ``target_path``, in
        ``relationships()`` order; ``incoming_references`` applies the same self-edge
        skip, identity lookup, cap and final sort, so the result is unchanged."""
        return incoming_references(
            self._rels_by_resolved().get(target_path, []),
            self._identity_by_path(),
            target_path,
            limit=limit,
        )

    def _adjacency(self) -> dict[str, list[tuple[str, int]]]:
        """Undirected resolved-edge adjacency ``{path -> [(neighbor, rank)]}``.

        The exact adjacency the frozen ``relationships.neighborhood`` builds from a
        relationship list: one entry per direction per resolved, non-self edge, each
        carrying the edge's relationship rank. Built once for the life of the mapped
        state so a depth>1 walk expands only its frontier, never the whole edge set.
        """
        if self._adjacency_cache is None:
            adjacency: dict[str, list[tuple[str, int]]] = {}
            for rel in self.relationships():
                if rel.resolved_path is None or rel.source_path == rel.resolved_path:
                    continue
                rank = _relationship_order(rel.relationship)
                adjacency.setdefault(rel.source_path, []).append((rel.resolved_path, rank))
                adjacency.setdefault(rel.resolved_path, []).append((rel.source_path, rank))
            self._adjacency_cache = adjacency
        return self._adjacency_cache

    def neighborhood(
        self,
        origin_path: str,
        *,
        depth: int,
        max_frontier: int = MAX_TRAVERSAL_FRONTIER,
        work_budget: int = MAX_TRAVERSAL_WORK,
    ) -> Neighborhood:
        """Bounded multi-hop neighbourhood — byte-identical to the fresh graph walk.

        The identical breadth-first walk ``relationships.neighborhood`` runs, over
        the memoised undirected adjacency and identity map (built once per
        generation) instead of an adjacency reconstructed per call. The caps,
        discovery order, deterministic ``(hops, rank, id, path)`` sort and final
        ``(hops, type, id)`` ordering are the frozen ones, so a depth>1 walk touches
        only the visited frontier while staying byte-identical (get_related parity).
        """
        depth = max(0, min(depth, MAX_TRAVERSAL_DEPTH))
        adjacency = self._adjacency()
        identity_by_path = self._identity_by_path()

        visited: set[str] = {origin_path}
        discovered: list[tuple[int, int, str, str]] = []  # (hops, rank, id, path)
        frontier = [origin_path]
        work = 0
        truncated = False

        for current_depth in range(1, depth + 1):
            next_frontier: list[str] = []
            for path in sorted(frontier):
                for neighbor_path, rank in sorted(set(adjacency.get(path, []))):
                    work += 1
                    if work > work_budget:
                        truncated = True
                        break
                    if neighbor_path in visited:
                        continue
                    visited.add(neighbor_path)
                    identity = identity_by_path.get(neighbor_path)
                    if identity is None:  # pragma: no cover — every edge target is indexed
                        continue
                    discovered.append((current_depth, rank, identity[0], neighbor_path))
                    if len(next_frontier) >= max_frontier:
                        truncated = True
                    else:
                        next_frontier.append(neighbor_path)
                if truncated and work > work_budget:
                    break
            frontier = next_frontier
            if not frontier:
                break

        discovered.sort()  # (hops, rank, id, path) — deterministic, stable truncation
        nodes = [
            NeighborhoodNode(
                id=identity_by_path[path][0],
                type=identity_by_path[path][1],
                title=identity_by_path[path][2],
                path=path,
                hops=hops,
            )
            for hops, _rank, _id, path in discovered
        ]
        nodes.sort(key=lambda node: (node.hops, node.type, node.id))
        return Neighborhood(nodes=nodes, truncated=truncated)

    # -- recency (ADR-101) -------------------------------------------------

    def recency(self) -> dict[str, str | None]:
        """``{path -> ISO last-committed}`` for the indexed git head (column read).

        Memoised for the life of the mapped state (dropped on refresh): the search
        seam annotates each result from this column, so warm searches reuse one
        built map and stay query-bound instead of re-scanning the whole store."""
        if self._recency_cache is None:
            result: dict[str, str | None] = {}
            for i in range(self.n):
                rec = self._record(i)
                result[self._path_for(rec["relpath"])] = rec["recency"]
            self._recency_cache = result
        return self._recency_cache

    # -- refresh (ADR-100 changeset invalidation) --------------------------

    def _manifest(self) -> dict[str, tuple[str, int, int]]:
        manifest = json.loads((self._dir / _MANIFEST).read_text(encoding="utf-8"))
        return {rel: (sha, size, mtime) for rel, sha, size, mtime in manifest["entries"]}

    def refresh(self, root: str, *, verify: bool = False) -> int:
        """Changeset refresh (ADR-100): stat-diff, hash candidates, splice truth.

        Enumerates with stat-only calls, selects candidates whose ``(size,
        mtime_ns)`` differ from the manifest plus path-set adds/removes, reads and
        hashes ONLY the candidates, and re-indexes only files whose content hash
        actually changed. Mtime is a hint to avoid reading unchanged bytes, never an
        authority — the sha256 confirms or dismisses each candidate. ``verify``
        re-hashes every file, recovering the strict per-call byte guarantee (and
        catching the rare byte edit that preserves size+mtime, which the stat hint
        alone cannot see). Returns the number of files re-parsed (added + changed).

        NOTE: with zero changes this does stat-only work and returns 0 without
        reading any artifact bytes or rewriting the index.
        """
        root_path = Path(root)
        old_manifest = self._manifest()
        current: dict[str, Path] = {_relpath(root_path, p): p for p in find_markdown_files(root)}

        removed = set(old_manifest) - set(current)
        added = set(current) - set(old_manifest)

        # Stat hint: which existing files might have changed?
        if verify:
            suspects = set(current) & set(old_manifest)
        else:
            suspects = {
                rel
                for rel in set(current) & set(old_manifest)
                if _stat_differs(current[rel], old_manifest[rel])
            }

        # Confirm suspects and adds by byte hash — bytes decide.
        changed: set[str] = set()
        new_sha: dict[str, str] = {}
        new_stat: dict[str, tuple[int, int]] = {}
        for rel in added | suspects:
            path = current[rel]
            new_sha[rel] = _sha256(path)
            st = path.stat()
            new_stat[rel] = (st.st_size, st.st_mtime_ns)
            if rel in added or new_sha[rel] != old_manifest[rel][0]:
                changed.add(rel)

        reindexed = added | changed
        head_moved = _git_head(root) != self.git_head

        if not reindexed and not removed and not head_moved:
            return 0  # zero-change fast path: stat only, no rewrite

        # Load the surviving document records from the mapped store (no corpus
        # reads) and splice: drop removed + changed, (re)parse added + changed.
        drop = removed | changed
        rebuilt: list[dict] = [
            self._survivor_record(rec)
            for i in range(self.n)
            if (rec := self._record(i))["relpath"] not in drop
        ]
        for rel in sorted(reindexed):
            rebuilt.append(_parse_one(root, -1, str(current[rel])))

        # Re-establish canonical document order and ids.
        rebuilt.sort(key=lambda r: _sort_key(root_path, r["relpath"]))
        for doc_id, rec in enumerate(rebuilt):
            rec["doc_id"] = doc_id

        # Manifest: reuse the survivors' stored hashes; only candidates were read.
        manifest: list[tuple[str, str, int, int]] = []
        for rel in current:
            if rel in new_sha:
                size, mtime = new_stat[rel]
                manifest.append((rel, new_sha[rel], size, mtime))
            else:
                sha, size, mtime = old_manifest[rel]
                manifest.append((rel, sha, size, mtime))

        data = _assemble(root, rebuilt, manifest)
        self.close()
        _write_index(str(self._dir), data)
        self._adopt(load_index(str(self._dir)))
        return len(reindexed)

    def _survivor_record(self, rec: dict) -> dict:
        """Re-derive a build record for an unchanged document from its stored data.

        Tokens/field-lengths are recomputed from the stored sections + identity with
        the frozen tokeniser (the bytes are unchanged, so this is exact); the stored
        ``extracted`` refs and ``known`` flag are reused directly. No corpus read.
        """
        entry = IndexEntry(
            id=rec["id"],
            type=rec["type"],
            title=rec["title"],
            path=self._path_for(rec["relpath"]),
            aliases=list(rec["aliases"]),
            search_sections=[SearchSection(heading=h, lines=list(ls)) for h, ls in rec["sections"]],
        )
        field_tokens = _field_tokens(entry)
        return {
            "doc_id": -1,
            "relpath": rec["relpath"],
            "id": rec["id"],
            "type": rec["type"],
            "title": rec["title"],
            "aliases": list(rec["aliases"]),
            "sections": rec["sections"],
            "field_lengths": {name: len(field_tokens[name]) for name in FIELDS},
            "tokens": sorted({tok for name in FIELDS for tok in field_tokens[name]}),
            "extracted": rec["extracted"],
            "known": rec["known"],
        }

    def _adopt(self, other: PersistentIndex) -> None:
        """Take over another freshly-loaded index's mapped state after a refresh."""
        self._header = other._header
        self.n = other.n
        self.field_totals = other.field_totals
        self.edge_sections = other.edge_sections
        self.git_head = other.git_head
        self._root = other._root
        self._terms = other._terms
        self._post = other._post
        self._docrec = other._docrec
        self._cout = other._cout
        self._cin = other._cin
        self._docrec_cache = {}
        # Every per-generation derived view is stale after a splice; drop them all
        # so the next read rebuilds against the new mapped state (no stale-memo bug:
        # an edit/add/remove that changes an answer changes it after the refresh).
        self._entries_cache = None
        self._relationships_cache = None
        self._recency_cache = None
        self._resolution_cache = None
        self._identity_cache = None
        self._rels_by_source_cache = None
        self._rels_by_resolved_cache = None
        self._adjacency_cache = None


def _stat_differs(path: Path, manifest_row: tuple[str, int, int]) -> bool:
    """True when a file's ``(size, mtime_ns)`` differs from the manifest hint."""
    _sha, size, mtime = manifest_row
    st = path.stat()
    return st.st_size != size or st.st_mtime_ns != mtime
