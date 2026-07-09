"""Persistent memory-mapped index store + base/delta fold (ADR-104).

This is the on-disk substrate that replaces ADR-099's serialised-blob cache
representation: instead of one ``{hash}.json`` document rehydrated whole on every
call, the derived read-model is written as a directory of length-prefixed binary
*segment* files (:mod:`rac.services.index_format`), memory-mapped and read by
point access. ``get_artifact``/``get_related`` touch only the identity rows they
need; ``search`` — Θ(N) by contract (ADR-078) — reconstructs the field vectors it
scores, but from mapped pages, never from a multi-megabyte JSON string and dict
co-resident in the heap. The per-call peak-allocation spike ADR-099's rehydration
paid is removed; freshness is untouched (the corpus content hash is still the
key, recomputed every call — ADR-032/ADR-099).

**Base + delta fold.** Every read goes through :class:`Fold`, a view over an
immutable mapped :class:`MmapIndexReader` (the *base*) combined with a small
mutable :class:`Delta` overlay under ``live = (base − tombstones) ∪ delta``. In
this bundle the delta is always :data:`EMPTY_DELTA`: the base is the whole answer.
The seam exists so a later bundle can add mutation (tombstones, added rows, stat
adjustments) without touching a single consumer — the read API is already the
fold, not the reader. The freshness decision that populates the delta is recorded
separately (ADR-105).

**Doc identity is the path string.** A positional docid indexes the segments
compactly, but it is never the identity or the tie-break: each row carries its
real ``entry.path``, and scoring/sort key off that string exactly as a fresh walk
does (ADR-078). Rehydrated path strings are data — the store never opens one as a
filesystem target.

Byte-parity is by construction: the store serialises only what a fresh
``build_derived_index`` produced and materialises it back into the identical
Python structures, so ``open_read_model(...) == build_derived_index(...)`` for any
corpus. It is asserted against a *fresh build*, never against the store's own
round-trip (the quality lens's serialisation-drift trap).
"""

from __future__ import annotations

import json
import mmap
import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from rac.core.models import Issue, SearchSection
from rac.services.derived_cache import DerivedIndex, ScopeRow
from rac.services.index import IndexEntry
from rac.services.index_format import (
    IndexedSegment,
    IndexFormatError,
    Reader,
    Writer,
    encode_segment,
    segment_payload,
    write_indexed,
)
from rac.services.relationships import Relationship
from rac.services.resolve import (
    _BM25_B,
    _BM25_K1,
    _FIELD_BOOSTS,
    _GRAPH_WEIGHT,
    _RRF_K,
    OUTCOME_DUPLICATE,
    OUTCOME_NOT_FOUND,
    OUTCOME_RESOLVED,
    ResolutionResult,
    ResolvedArtifact,
    SearchableArtifact,
    SearchResult,
    _bm25f_scored,
    _entry_has_tags,
    _Match,
    _match_entry,
    _rank_and_build,
    _tokenize_entry,
    tokenize,
)

# The scorable field families, in the exact BM25F iteration order (ADR-078). The
# store persists per-field token-id sequences and length accumulators in this
# order; the fold feeds them back to the shared scorer in the same order, so the
# float summation order — the parity-critical one — is preserved.
FIELDS: tuple[str, ...] = tuple(_FIELD_BOOSTS)
assert FIELDS == ("id", "title", "path", "heading", "body", "tags"), (
    "field order is a parity contract"
)

# On-disk layout root and version. A layout bump lands in a new subdirectory, so
# stores from an older layout are simply never found (a miss) — never rehydrated.
STORE_DIRNAME = "store"
STORE_LAYOUT_VERSION = "v1"

# Segment file names within one corpus-hash store directory.
_SEG_HEADER = "header.seg"
_SEG_ENTRIES = "entries.seg"
_SEG_SECTIONS = "sections.seg"
_SEG_TOKENS = "tokens.seg"
_SEG_TERMDICT = "termdict.seg"
_SEG_POSTINGS = "postings.seg"
_SEG_RELATIONSHIPS = "relationships.seg"
_SEG_LIVE = "live.seg"
_SEG_SCOPE = "scope.seg"
_SEG_PORTFOLIO = "portfolio.seg"
# Point-resolution segments (ADR-104). ``aliasmap`` is the sorted casefolded
# identifier -> docids map exact resolution binary-searches, so ``get_artifact``
# and ``get_related`` resolve an id without reconstructing every identity row.
# ``pathmap`` is the sorted path-string -> docid map ``get_related`` binary-
# searches to resolve a neighbour path's identity on demand, so its
# ``identity_by_path`` touches only the edges near the artifact, never O(N) rows.
_SEG_ALIASMAP = "aliasmap.seg"
_SEG_PATHMAP = "pathmap.seg"

_ALL_SEGMENTS = (
    _SEG_HEADER,
    _SEG_ENTRIES,
    _SEG_SECTIONS,
    _SEG_TOKENS,
    _SEG_TERMDICT,
    _SEG_POSTINGS,
    _SEG_RELATIONSHIPS,
    _SEG_LIVE,
    _SEG_SCOPE,
    _SEG_PORTFOLIO,
    _SEG_ALIASMAP,
    _SEG_PATHMAP,
)

# The artifact type the live-decision topic query filters to (ADR-067), named
# here so the store's decision-scoped search reads cleanly; it must equal
# ``resolve._DECISION_TYPE``.
_DECISION_TYPE = "decision"


def scoring_fingerprint() -> str:
    """A stable fingerprint of the scoring constants the store's stats assume.

    Persisted in the header and checked on open: if a scoring constant changes
    (a boost, k1/b, the RRF weights), every existing store fails the gate closed
    and is rebuilt, so a store can never feed the scorer stale-assumption numbers
    (v2 §1.2 scoring-constant snapshot).
    """
    parts = [f"{name}={boost!r}" for name, boost in _FIELD_BOOSTS.items()]
    parts += [f"k1={_BM25_K1!r}", f"b={_BM25_B!r}", f"rrf={_RRF_K!r}", f"graph={_GRAPH_WEIGHT!r}"]
    return "|".join(parts)


# =============================================================================
# Writer — one DerivedIndex -> a directory of segment files, written atomically.
# =============================================================================


def store_root(cache_dir: Path) -> Path:
    """The layout-versioned root the corpus-hash store directories live under."""
    return cache_dir / STORE_DIRNAME / STORE_LAYOUT_VERSION


def store_dir(cache_dir: Path, corpus_hash: str) -> Path:
    return store_root(cache_dir) / corpus_hash


def _iter_segment_files(
    corpus_hash: str, bundle_version: str, derived: DerivedIndex
) -> Iterator[tuple[str, bytes]]:
    """Encode a :class:`~rac.services.derived_cache.DerivedIndex` to segment files.

    Yields ``(filename, encoded-bytes)`` one segment at a time, releasing each
    segment's source rows before encoding the next, so the whole encoded store is
    never co-resident (ADR-107 streaming cold-build write). Docids are assigned in
    ``index_entries`` order — the corpus walk's sorted-path order — and every
    structure keyed to a doc uses that order, so the streamed store reproduces the
    fresh bundle byte-for-byte; the yield order does not affect any byte.
    """
    entries: list[IndexEntry] = list(derived.index_entries)
    field_tokens = derived.field_tokens_by_path

    # Global vocabulary -> sorted term dictionary -> term id. Sorted so a query
    # term's prefix set is a contiguous id range found by binary search (ADR-037).
    vocab: set[str] = set()
    for fields in field_tokens.values():
        for name in FIELDS:
            vocab.update(fields[name])
    termdict = sorted(vocab)
    term_id = {term: i for i, term in enumerate(termdict)}

    length_sums = [0] * len(FIELDS)
    entry_rows: list[bytes] = []
    section_rows: list[bytes] = []
    token_rows: list[bytes] = []
    # Term-major postings: term id -> the docids holding that term in ANY field.
    # Built by appending each docid as we walk entries in docid (sorted-path)
    # order, so every list is sorted ascending by construction — deterministic,
    # no post-sort. This is the segment the postings-served search reads: a query
    # term's candidate docs and its distinct-docid df both come from the union of
    # the term's prefix-range rows, touching O(matches) not O(corpus) (ADR-104).
    postings_lists: list[list[int]] = [[] for _ in termdict]
    # Casefolded identifier -> ascending docids, the exact identity set exact
    # resolution matches (``resolve_in_index``: casefolded equality over an
    # entry's canonical id and aliases). Each list stays ascending and
    # duplicate-free by construction — docids are appended in order, and two
    # aliases of one entry that casefold to the same key touch the same (last)
    # docid, guarded here — so the persisted map reproduces the walk's outcomes.
    alias_docids: dict[str, list[int]] = {}
    for docid, entry in enumerate(entries):
        fields = field_tokens[entry.path]
        lengths = [len(fields[name]) for name in FIELDS]
        for i, value in enumerate(lengths):
            length_sums[i] += value

        for alias in entry.aliases:
            docids = alias_docids.setdefault(alias.casefold(), [])
            if not docids or docids[-1] != docid:
                docids.append(docid)

        row = Writer()
        row.text(entry.id)
        row.text(entry.type)
        row.opt_text(entry.title)
        row.text(entry.path)
        row.text_list(list(entry.aliases))
        # Raw tags in the identity block (ADR-109) so the `--tag` facet matches
        # whole tags reconstructed from the store; placed after aliases and before
        # inbound so entry_path (which stops at path) is untouched.
        row.text_list(list(entry.tags))
        row.u32(entry.inbound_count)
        for value in lengths:
            row.u32(value)
        entry_rows.append(row.payload)

        sec = Writer()
        sec.u32(len(entry.search_sections))
        for section in entry.search_sections:
            sec.text(section.heading)
            sec.text_list(list(section.lines))
        section_rows.append(sec.payload)

        doc_term_ids: set[int] = set()
        tok = Writer()
        for name in FIELDS:
            ids = [term_id[token] for token in fields[name]]
            tok.u32_list(ids)
            doc_term_ids.update(ids)
        token_rows.append(tok.payload)
        for tid in doc_term_ids:
            postings_lists[tid].append(docid)

    # Scalar header inputs, captured before the structures they summarise are
    # released; the header segment is emitted last.
    n_entries = len(entries)
    n_terms = len(termdict)
    del term_id

    # Per-doc indexed segments. Each is encoded, yielded, and its source rows
    # released before the next, so the whole encoded store is never co-resident.
    # The yield order does not affect any byte — each file is whole and
    # independent — and is chosen to free the largest encoded rows first.
    yield _SEG_ENTRIES, encode_segment(write_indexed(entry_rows))
    del entry_rows
    yield _SEG_SECTIONS, encode_segment(write_indexed(section_rows))
    del section_rows
    yield _SEG_TOKENS, encode_segment(write_indexed(token_rows))
    del token_rows

    postings_rows = [_encode_u32_list(docids) for docids in postings_lists]
    del postings_lists
    yield _SEG_POSTINGS, encode_segment(write_indexed(postings_rows))
    del postings_rows

    termdict_rows = [_encode_text(term) for term in termdict]
    del termdict
    yield _SEG_TERMDICT, encode_segment(write_indexed(termdict_rows))
    del termdict_rows

    # Alias map: rows sorted by casefolded key so a query id's exact match is a
    # binary search. Each row is ``key`` then its ascending docids.
    aliasmap_rows: list[bytes] = []
    for key in sorted(alias_docids):
        writer = Writer()
        writer.text(key)
        writer.u32_list(alias_docids[key])
        aliasmap_rows.append(writer.payload)
    del alias_docids
    yield _SEG_ALIASMAP, encode_segment(write_indexed(aliasmap_rows))
    del aliasmap_rows

    # Path map: rows sorted by path *string* so a neighbour path's docid is a
    # binary search. Docids index in walk (Path-sorted) order, which is not the
    # same as string order, so the rows are re-sorted by the string key here.
    pathmap_rows: list[bytes] = []
    for path, docid in sorted((entry.path, docid) for docid, entry in enumerate(entries)):
        writer = Writer()
        writer.text(path)
        writer.u32(docid)
        pathmap_rows.append(writer.payload)
    del entries
    yield _SEG_PATHMAP, encode_segment(write_indexed(pathmap_rows))
    del pathmap_rows

    relationships = Writer()
    rels: list[Relationship] = list(derived.relationships)
    relationships.u32(len(rels))
    for rel in rels:
        relationships.text(rel.source_path)
        relationships.text(rel.relationship)
        relationships.text(rel.target)
        relationships.opt_text(rel.resolved_path)
        relationships.opt_text(rel.issue)
    yield _SEG_RELATIONSHIPS, encode_segment(relationships.payload)

    live = Writer()
    live.text_list(list(derived.live_decision_paths))
    yield _SEG_LIVE, encode_segment(live.payload)

    scope = Writer()
    scope_rows = list(derived.scope_rows)
    scope.u32(len(scope_rows))
    for scope_row in scope_rows:
        scope.text(scope_row.id)
        scope.text(scope_row.title)
        scope.text(scope_row.status)
        scope.text(scope_row.path)
        scope.text_list(list(scope_row.scope_entries))
    yield _SEG_SCOPE, encode_segment(scope.payload)

    portfolio = Writer()
    # The portfolio summary is itself a JSON wire payload (get_summary serves it
    # verbatim). It is stored as its canonical JSON text in a single leaf blob —
    # data, decoded with ``json.loads`` on demand, never code (no pickle). This is
    # the one place JSON survives; every structural segment is binary.
    portfolio.text(json.dumps(derived.portfolio_summary, ensure_ascii=False))
    yield _SEG_PORTFOLIO, encode_segment(portfolio.payload)

    header = Writer()
    header.text(corpus_hash)
    header.text(bundle_version)
    header.text(scoring_fingerprint())
    header.u32(n_entries)
    for value in length_sums:
        header.u32(value)
    header.u32(n_terms)
    yield _SEG_HEADER, encode_segment(header.payload)


def _encode_text(value: str) -> bytes:
    writer = Writer()
    writer.text(value)
    return writer.payload


def _encode_u32_list(values: list[int]) -> bytes:
    writer = Writer()
    writer.u32_list(values)
    return writer.payload


def write_store(
    cache_dir: Path, corpus_hash: str, bundle_version: str, derived: DerivedIndex
) -> bool:
    """Write the store for ``corpus_hash`` atomically; return whether it landed.

    Segments are built in a temp directory, fsynced, then ``os.replace``d into the
    content-addressed name in one step, so a concurrent reader never sees a
    half-written store (the atomic-write property). A pre-existing store for the
    same hash is already correct (content addressing), so a lost replace race is
    benign — the temp dir is discarded and the call reports success. Any OS error
    degrades to "not written": the freshly built structures are already in hand,
    so the cache is a latency nicety, never a requirement (ADR-080).
    """
    root = store_root(cache_dir)
    final = root / corpus_hash
    if final.is_dir():
        # Content addressing makes a same-hash store byte-equivalent only within
        # one segment format. A dir left by an older format version is unreadable
        # (fail-closed on open) and skipping here would brick this hash forever:
        # every compaction would "succeed", every open would miss, and serving
        # would silently stay on the slow path. Probe readability; replace if bad.
        if _store_is_openable(final, corpus_hash, bundle_version):
            return True
        _remove_tree(final)
    tmp = root / f".{corpus_hash}.tmp-{os.getpid()}-{os.urandom(4).hex()}"
    try:
        tmp.mkdir(parents=True, exist_ok=True)
        for name, payload in _iter_segment_files(corpus_hash, bundle_version, derived):
            _write_file(tmp / name, payload)
        _fsync_dir(tmp)
        try:
            os.replace(tmp, final)
        except OSError:
            # Target already populated by a concurrent writer (identical content),
            # or the rename otherwise failed: discard the temp build and report the
            # store's presence honestly.
            _remove_tree(tmp)
            return final.is_dir()
        return True
    except OSError:
        _remove_tree(tmp)
        return False


def _store_is_openable(directory: Path, corpus_hash: str, bundle_version: str) -> bool:
    """Whether an existing store dir opens under the CURRENT format and version.

    The full reader open is the one truthful gate — it applies every fail-closed
    check (magic, format version, bundle version, scoring fingerprint, hash echo,
    truncation) exactly as serving would. Runs only on the rare
    write-with-existing-dir path, never per call.
    """
    try:
        reader = MmapIndexReader(directory, corpus_hash, bundle_version)
    except (IndexFormatError, OSError, ValueError):
        return False
    reader.close()
    return True


def remove_store(cache_dir: Path, corpus_hash: str) -> None:
    """Best-effort removal of a store directory (used to clear a corrupt one).

    Unlinking a mapped segment is safe on POSIX — an open reader's mapping
    persists — so a concurrent call is never disturbed; the next build writes a
    fresh store into the freed name.
    """
    _remove_tree(store_dir(cache_dir, corpus_hash))


def _write_file(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _remove_tree(path: Path) -> None:
    try:
        for child in path.iterdir():
            child.unlink()
        path.rmdir()
    except OSError:
        pass


# =============================================================================
# Reader — mmap the segments, validate on open, point-access the rows.
# =============================================================================


class MmapIndexReader:
    """Memory-mapped reader over one corpus-hash store directory (the base).

    On open it maps every segment and validates each segment's framing header
    (magic, format version, and the length gate that catches truncation) — O(1)
    per segment, no payload scan — then reads the tiny header segment fully and
    checks the bundle version, the scoring fingerprint, and the echoed corpus
    hash. Any mismatch or truncation raises :class:`IndexFormatError`, which
    :func:`open_read_model` turns into a miss. Bulk pages fault in only when a
    query touches them.
    """

    def __init__(self, directory: Path, corpus_hash: str, bundle_version: str) -> None:
        self._maps: dict[str, mmap.mmap] = {}
        self._views: dict[str, memoryview] = {}
        try:
            for name in _ALL_SEGMENTS:
                self._map(directory / name, name)
            self._read_header(corpus_hash, bundle_version)
        except BaseException:
            self.close()
            raise
        self._terms_cache: list[str] | None = None
        self._postings_seg: IndexedSegment | None = None
        self._aliasmap_seg: IndexedSegment | None = None
        self._pathmap_seg: IndexedSegment | None = None

    def _map(self, path: Path, name: str) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            if os.fstat(fd).st_size == 0:
                raise IndexFormatError(f"empty segment: {name}")
            handle = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
        finally:
            # The mapping outlives the descriptor on POSIX, so no fd is held past
            # open — only the mapping, released on close/GC. This keeps a
            # long-lived server from leaking descriptors across per-call reads.
            os.close(fd)
        self._maps[name] = handle
        # Keep the parent memoryview explicit so it can be released on a validation
        # failure: an un-released export (lingering in the exception frame while
        # __init__ unwinds) would make the handle's close raise BufferError and mask
        # the miss. On success it is GC'd; only the payload slice keeps an export.
        view = memoryview(handle)
        try:
            self._views[name] = segment_payload(view)
        except BaseException:
            view.release()
            raise

    def _read_header(self, corpus_hash: str, bundle_version: str) -> None:
        reader = Reader(self._views[_SEG_HEADER])
        stored_hash = reader.text()
        stored_bundle = reader.text()
        stored_fingerprint = reader.text()
        self.doc_count = reader.u32()
        self.field_length_sums = [reader.u32() for _ in FIELDS]
        self.term_count = reader.u32()
        if stored_hash != corpus_hash:
            raise IndexFormatError("store corpus-hash mismatch")
        if stored_bundle != bundle_version:
            raise IndexFormatError("store bundle-version mismatch")
        if stored_fingerprint != scoring_fingerprint():
            raise IndexFormatError("store scoring-constant mismatch")

    # --- point access ---------------------------------------------------------

    def _entries(self) -> IndexedSegment:
        return IndexedSegment(self._views[_SEG_ENTRIES])

    def _sections(self) -> IndexedSegment:
        return IndexedSegment(self._views[_SEG_SECTIONS])

    def _tokens(self) -> IndexedSegment:
        return IndexedSegment(self._views[_SEG_TOKENS])

    def _termdict(self) -> IndexedSegment:
        return IndexedSegment(self._views[_SEG_TERMDICT])

    def identity_entry(self, docid: int) -> IndexEntry:
        """The lightweight identity row (id/type/title/path/aliases) — no sections.

        This is the point-access path resolution takes: ``get_artifact`` and
        ``get_related`` read only these fields, so their pages never pull in the
        section text or token vectors — the RSS win over rehydrating the whole
        bundle.
        """
        reader = self._entries().row(docid)
        entry_id = reader.text()
        entry_type = reader.text()
        title = reader.opt_text()
        path = reader.text()
        aliases = reader.text_list()
        tags = reader.text_list()
        return IndexEntry(
            id=entry_id, type=entry_type, title=title, path=path, aliases=aliases, tags=tags
        )

    def full_entry(self, docid: int) -> IndexEntry:
        """The full index row: identity plus searchable sections and inbound count."""
        reader = self._entries().row(docid)
        entry_id = reader.text()
        entry_type = reader.text()
        title = reader.opt_text()
        path = reader.text()
        aliases = reader.text_list()
        tags = reader.text_list()
        inbound = reader.u32()
        sections = self._read_sections(docid)
        return IndexEntry(
            id=entry_id,
            type=entry_type,
            title=title,
            path=path,
            aliases=aliases,
            search_sections=sections,
            inbound_count=inbound,
            tags=tags,
        )

    def _read_sections(self, docid: int) -> list[SearchSection]:
        reader = self._sections().row(docid)
        count = reader.u32()
        return [
            SearchSection(heading=reader.text(), lines=reader.text_list()) for _ in range(count)
        ]

    def entry_path(self, docid: int) -> str:
        reader = self._entries().row(docid)
        reader.text()  # id
        reader.text()  # type
        reader.opt_text()  # title
        return reader.text()  # path

    def field_length(self, docid: int, field_name: str) -> int:
        reader = self._entries().row(docid)
        reader.text()
        reader.text()
        reader.opt_text()
        reader.text()
        reader.text_list()  # aliases
        reader.text_list()  # tags
        reader.u32()  # inbound
        lengths = [reader.u32() for _ in FIELDS]
        return lengths[FIELDS.index(field_name)]

    def forward_token_ids(self, docid: int) -> dict[str, list[int]]:
        reader = self._tokens().row(docid)
        return {name: reader.u32_list() for name in FIELDS}

    def _all_terms(self) -> list[str]:
        # Materialised once, lazily, only when a search reconstructs field vectors
        # or scans the vocabulary — never on open. Point lookups never trigger it.
        if self._terms_cache is None:
            segment = self._termdict()
            self._terms_cache = [segment.row(i).text() for i in range(segment.count)]
        return self._terms_cache

    def term_at(self, term_id: int) -> str:
        return self._all_terms()[term_id]

    def field_tokens(self, docid: int) -> dict[str, list[str]]:
        """Reconstruct one doc's per-field token vectors in document order.

        Byte-identical to ``field_tokens_for_entries`` for this doc: the forward
        token-id sequences are stored in the original document order, so the token
        lists come back in the same order the fresh tokeniser produced them.
        """
        terms = self._all_terms()
        ids = self.forward_token_ids(docid)
        return {name: [terms[i] for i in ids[name]] for name in FIELDS}

    # --- term dictionary: binary-searched prefix ranges (ADR-037) -------------

    def _bisect_left(self, target: str) -> int:
        segment = self._termdict()
        lo, hi = 0, segment.count
        while lo < hi:
            mid = (lo + hi) // 2
            if segment.row(mid).text() < target:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def prefix_range(self, term: str) -> tuple[int, int]:
        """The ``[lo, hi)`` term-id range of every indexed term ``term`` prefixes.

        A query term matches an indexed term by casefolded equality or prefix
        (ADR-037); in a sorted dictionary those matches are exactly the contiguous
        run ``[bisect_left(term), bisect_left(successor(term)))``, where the
        successor is ``term`` with its last character incremented — strictly above
        every string that starts with ``term``. df and tf both flow from this one
        range.
        """
        if not term:
            return (0, 0)
        lo = self._bisect_left(term)
        successor = term[:-1] + chr(ord(term[-1]) + 1)
        hi = self._bisect_left(successor)
        return (lo, hi)

    # --- term-major postings: term id -> docids holding it (ADR-104) ----------

    def _postings(self) -> IndexedSegment:
        # One IndexedSegment reused across a call: a prefix range walks many
        # rows, so caching the offset table avoids re-reading the row count each
        # time. Materialised lazily — a point lookup never opens the postings.
        if self._postings_seg is None:
            self._postings_seg = IndexedSegment(self._views[_SEG_POSTINGS])
        return self._postings_seg

    def postings(self, term_id: int) -> list[int]:
        """The ascending docids that hold ``term_id`` in any field (delta-free base)."""
        return self._postings().row(term_id).u32_list()

    def prefix_docids(self, term: str) -> set[int]:
        """Distinct base docids matching ``term`` under the prefix predicate (ADR-037).

        The union of the postings rows across ``term``'s binary-searched prefix
        range — every doc holding, in any field, a token ``term`` equals or
        prefixes — which is exactly the set of docs a term match would find on a
        walk. Touches only the range's postings, never the whole corpus.
        """
        lo, hi = self.prefix_range(term)
        result: set[int] = set()
        for term_id in range(lo, hi):
            result.update(self.postings(term_id))
        return result

    # --- point resolution: alias/path maps binary-searched (ADR-104) ----------

    def _aliasmap(self) -> IndexedSegment:
        if self._aliasmap_seg is None:
            self._aliasmap_seg = IndexedSegment(self._views[_SEG_ALIASMAP])
        return self._aliasmap_seg

    def _pathmap(self) -> IndexedSegment:
        if self._pathmap_seg is None:
            self._pathmap_seg = IndexedSegment(self._views[_SEG_PATHMAP])
        return self._pathmap_seg

    def alias_docids(self, wanted: str) -> list[int]:
        """The ascending docids whose identity set holds ``wanted`` (casefolded).

        ``wanted`` must already be ``strip().casefold()``d by the caller — the same
        normalisation ``resolve_in_index`` applies to the query — so the binary
        search over the casefolded-key rows finds the exact identity set a walk's
        ``any(alias.casefold() == wanted ...)`` would. Empty when nothing matches.
        """
        segment = self._aliasmap()
        lo, hi = 0, segment.count
        while lo < hi:
            mid = (lo + hi) // 2
            reader = segment.row(mid)
            key = reader.text()
            if key < wanted:
                lo = mid + 1
            elif key > wanted:
                hi = mid
            else:
                return reader.u32_list()
        return []

    def docid_for_path(self, path: str) -> int | None:
        """The docid whose stored path equals ``path``, or ``None`` — binary search.

        The path map is sorted by path string, so a neighbour path's identity row
        is found in O(log N) without materialising the whole identity projection.
        """
        segment = self._pathmap()
        lo, hi = 0, segment.count
        while lo < hi:
            mid = (lo + hi) // 2
            reader = segment.row(mid)
            key = reader.text()
            if key < path:
                lo = mid + 1
            elif key > path:
                hi = mid
            else:
                return reader.u32()
        return None

    def relationships(self) -> list[Relationship]:
        reader = Reader(self._views[_SEG_RELATIONSHIPS])
        count = reader.u32()
        result: list[Relationship] = []
        for _ in range(count):
            result.append(
                Relationship(
                    source_path=reader.text(),
                    relationship=reader.text(),
                    target=reader.text(),
                    resolved_path=reader.opt_text(),
                    issue=reader.opt_text(),
                )
            )
        return result

    def live_decision_paths(self) -> list[str]:
        return Reader(self._views[_SEG_LIVE]).text_list()

    def scope_rows_raw(self) -> list[tuple[str, str, str, str, tuple[str, ...]]]:
        reader = Reader(self._views[_SEG_SCOPE])
        count = reader.u32()
        rows: list[tuple[str, str, str, str, tuple[str, ...]]] = []
        for _ in range(count):
            rows.append(
                (
                    reader.text(),
                    reader.text(),
                    reader.text(),
                    reader.text(),
                    tuple(reader.text_list()),
                )
            )
        return rows

    def portfolio_summary(self) -> dict:
        return json.loads(Reader(self._views[_SEG_PORTFOLIO]).text())

    def close(self) -> None:
        # Drop cached views that export a pointer into a mapping before release.
        self._postings_seg = None
        self._aliasmap_seg = None
        self._pathmap_seg = None
        for view in self._views.values():
            view.release()
        self._views.clear()
        for handle in self._maps.values():
            try:
                handle.close()
            except BufferError:
                # A slice still exports a pointer (a read raced close); the mapping
                # is released on GC either way, and a failed close is never fatal.
                pass
        self._maps.clear()


# =============================================================================
# Delta + Fold — the mutation seam (empty in this bundle) and the read API.
# =============================================================================


@dataclass(frozen=True)
class Delta:
    """The mutable overlay a later bundle folds over the base — EMPTY here (ADR-104).

    The seams are declared now so mutation can be added without touching any
    consumer, which already reads through :class:`Fold`:

    - ``tombstones`` — base docids whose file changed or vanished, masked from
      every fold (docs, postings, stats, edges, scope, live).
    - ``added_paths`` — the identity of docs the delta adds, so the fold's key-set
      stays exactly the live corpus set (the cache-key-set == entry-set invariant).
    - stat adjustments, added rows, and term deltas belong here too; they stay
      unpopulated until the freshness decision (ADR-105) that owns them.
    """

    tombstones: frozenset[int] = frozenset()
    added_paths: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.tombstones and not self.added_paths


EMPTY_DELTA = Delta()


class Fold:
    """The deterministic read view over ``(base − tombstones) ∪ delta``.

    Every consumer reads through this, never the raw reader, so the empty-delta
    base case and a future non-empty delta share one code path. With
    :data:`EMPTY_DELTA` the live docids are exactly the base's, in order, and each
    fold method returns the base structure unchanged — so the store's output is
    byte-identical to a fresh build.
    """

    def __init__(self, base: MmapIndexReader, delta: Delta = EMPTY_DELTA) -> None:
        self.base = base
        self.delta = delta

    def live_docids(self) -> Iterator[int]:
        tombstones = self.delta.tombstones
        for docid in range(self.base.doc_count):
            if docid not in tombstones:
                yield docid

    def identity_entries(self) -> list[IndexEntry]:
        return [self.base.identity_entry(docid) for docid in self.live_docids()]

    def resolve(self, artifact_id: str) -> ResolutionResult:
        """Exact resolution over the persisted alias map, byte-identical to a walk.

        Reproduces :func:`resolve.resolve_in_index` exactly from the mapped alias
        segment: ``artifact_id.strip().casefold()`` is looked up against the same
        casefolded identity set (canonical id plus aliases), and the three outcomes
        are the same — not-found when nothing matches, duplicate (with the matching
        paths sorted, never resolved by order) when more than one distinct doc
        matches, resolved otherwise. A binary search plus O(matches) row reads
        replaces the O(N) identity-row reconstruction (ADR-104). Tombstoned docs are
        folded out first, so a future non-empty delta stays correct through this
        one path (empty here, so the base is the whole answer).
        """
        wanted = artifact_id.strip().casefold()
        docids = self.base.alias_docids(wanted)
        tombstones = self.delta.tombstones
        if tombstones:
            docids = [docid for docid in docids if docid not in tombstones]
        if not docids:
            return ResolutionResult(artifact_id=artifact_id, outcome=OUTCOME_NOT_FOUND)
        if len(docids) > 1:
            return ResolutionResult(
                artifact_id=artifact_id,
                outcome=OUTCOME_DUPLICATE,
                duplicate_paths=sorted(self.base.entry_path(docid) for docid in docids),
            )
        entry = self.base.identity_entry(docids[0])
        return ResolutionResult(
            artifact_id=artifact_id,
            outcome=OUTCOME_RESOLVED,
            artifact=ResolvedArtifact.from_entry(entry),
        )

    def identity_for_path(self, path: str) -> tuple[str, str, str | None] | None:
        """``(id, type, title)`` for ``path`` via the path map, or ``None``.

        A binary search over the path->docid map plus one identity-row read, with
        tombstoned docs folded out — the per-path primitive :class:`LazyIdentityByPath`
        resolves ``get_related``'s edges through, so its ``identity_by_path`` never
        materialises the whole corpus.
        """
        docid = self.base.docid_for_path(path)
        if docid is None or docid in self.delta.tombstones:
            return None
        entry = self.base.identity_entry(docid)
        return (entry.id, entry.type, entry.title)

    def index_entries(self) -> list[IndexEntry]:
        return [self.base.full_entry(docid) for docid in self.live_docids()]

    def field_tokens_by_path(self) -> dict[str, dict[str, list[str]]]:
        result: dict[str, dict[str, list[str]]] = {}
        for docid in self.live_docids():
            result[self.base.entry_path(docid)] = self.base.field_tokens(docid)
        return result

    def relationships(self) -> list[Relationship]:
        if self.delta.is_empty():
            return self.base.relationships()
        live = {self.base.entry_path(docid) for docid in self.live_docids()}
        return [
            rel
            for rel in self.base.relationships()
            if rel.source_path in live and (rel.resolved_path is None or rel.resolved_path in live)
        ]

    def live_decision_paths(self) -> list[str]:
        if self.delta.is_empty():
            return self.base.live_decision_paths()
        live = {self.base.entry_path(docid) for docid in self.live_docids()}
        return [path for path in self.base.live_decision_paths() if path in live]

    def scope_rows_raw(self) -> list[tuple[str, str, str, str, tuple[str, ...]]]:
        if self.delta.is_empty():
            return self.base.scope_rows_raw()
        live = {self.base.entry_path(docid) for docid in self.live_docids()}
        return [row for row in self.base.scope_rows_raw() if row[3] in live]

    def portfolio_summary(self) -> dict:
        # The portfolio summary is an aggregate; folding a non-empty delta into it
        # needs the stat-adjustment seam (ADR-105). With the empty delta the base
        # summary is exact.
        return self.base.portfolio_summary()

    # --- scoring over the accumulators + prefix ranges (v2 §1.2; B3 substrate) --

    def doc_count_live(self) -> int:
        return sum(1 for _ in self.live_docids())

    def field_length_sum(self, field_name: str) -> int:
        return self.base.field_length_sums[FIELDS.index(field_name)]

    def prefix_df(self, term: str) -> int:
        """Document frequency of ``term`` under the prefix predicate (ADR-037).

        The count of live docs holding, in any field, a token in ``term``'s
        prefix range — the same value ``_corpus_stats`` derives by walking tokens.
        Computed from the term-major postings: the distinct union of the prefix
        range's rows, minus any tombstoned docid, so a doc holding both ``cache``
        and ``caches`` counts once and the cost is O(matches), not O(corpus).
        """
        docids = self.base.prefix_docids(term)
        tombstones = self.delta.tombstones
        if tombstones:
            docids -= tombstones
        return len(docids)

    def candidate_docids(self, terms: Sequence[str]) -> set[int]:
        """Live docids matching at least one of ``terms`` — the candidate set.

        The union of each term's prefix-range postings, tombstones removed. It is
        a superset of the AND-matched set (a doc matching every term matches at
        least one), so :func:`resolve._match_entry` — run per candidate — remains
        the authoritative filter; a doc matching no term is never materialised.
        """
        tombstones = self.delta.tombstones
        result: set[int] = set()
        for term in terms:
            result |= self.base.prefix_docids(term)
        if tombstones:
            result -= tombstones
        return result

    def doc_field_tf(self, docid: int, term: str, field_name: str) -> int:
        """Term frequency of ``term`` in one field of one doc, prefix predicate."""
        lo, hi = self.base.prefix_range(term)
        if lo >= hi:
            return 0
        return sum(1 for tid in self.base.forward_token_ids(docid)[field_name] if lo <= tid < hi)

    def bm25f(self, docid: int, terms: list[str]) -> float:
        """BM25F for one doc over ``terms``, from stored integer accumulators.

        Reuses the shared scorer (``resolve._bm25f_scored``) fed store-derived
        integers — n and per-field Σ from the header (avglen is one division, never
        a stored float), df and tf from the prefix ranges, per-field lengths from
        the entry row — so the float arithmetic and its summation order are the
        production scorer's, byte-identical to a walk on the same corpus.
        """
        n = self.doc_count_live()
        avglen = {name: (self.field_length_sum(name) / n if n else 0.0) for name in FIELDS}
        df = {term: self.prefix_df(term) for term in terms}
        return _bm25f_scored(
            terms,
            n,
            df,
            avglen,
            tf_of=lambda term, name: self.doc_field_tf(docid, term, name),
            len_of=lambda name: self.base.field_length(docid, name),
        )

    # --- postings-served search (ADR-104; ADR-078 scoring unchanged) -----------

    def search(
        self,
        query: str,
        artifact_type: str | None = None,
        *,
        tags: Sequence[str] | None = None,
    ) -> SearchResult:
        """`rac find` search served from the postings, byte-identical to a walk.

        Reproduces :func:`resolve.search_index` without materialising the whole
        corpus: the candidate set (docs matching at least one term) comes from the
        term-major postings, only those candidates are reconstructed and matched,
        and the global stats the scorer needs — ``n`` and the per-field Σ from the
        header, ``df`` from the prefix ranges — carry the non-matching corpus's
        contribution without touching its rows. Matching, snippet selection, and
        the fused BM25F+RRF ranking all run through the shared scoring code on
        inputs value-identical to the fresh walk, so the emitted bytes match. The
        ``tags`` facet narrows the candidates to those carrying every tag, exactly
        as the fresh path does (ADR-109).
        """
        terms = tokenize(query)
        if not terms:
            return SearchResult(query=query, artifact_type=artifact_type, matches=[])
        tag_filter = frozenset(t.casefold() for t in tags) if tags else frozenset()
        matched: list[tuple[SearchableArtifact, _Match]] = []
        field_tokens_by_path: dict[str, dict[str, list[str]]] = {}
        for docid in sorted(self.candidate_docids(terms)):
            entry = self.base.full_entry(docid)
            if artifact_type is not None and entry.type != artifact_type:
                continue
            if tag_filter and not _entry_has_tags(entry, tag_filter):
                continue
            entry_tokens = _tokenize_entry(entry)
            match = _match_entry(entry_tokens, terms)
            if match is not None:
                matched.append((entry, match))
                field_tokens_by_path[entry.path] = entry_tokens.fields
        if not matched:
            return SearchResult(query=query, artifact_type=artifact_type, matches=[])
        n = self.doc_count_live()
        avglen = {name: (self.field_length_sum(name) / n if n else 0.0) for name in FIELDS}
        df = {term: self.prefix_df(term) for term in terms}
        return _rank_and_build(
            query, artifact_type, matched, terms, n, df, avglen, field_tokens_by_path
        )


class LazyIdentityByPath:
    """Path -> ``(id, type, title)`` resolved on demand from the store (ADR-104).

    ``get_related``'s relationship helpers read identity only for the paths on the
    artifact's incoming edges and within its bounded neighbourhood — never the whole
    corpus — so this resolves each *requested* path through the fold's path map (a
    binary search plus one identity-row read), memoising the result, rather than
    reconstructing every identity row up front. It duck-types the ``dict`` those
    helpers read: only ``.get`` (incoming edges and neighbourhood discovery) and
    ``[]`` (neighbourhood node assembly) are used, and both surface exactly what a
    full ``{path: (id, type, title)}`` dict would — a missing path is ``None`` from
    ``.get`` and a ``KeyError`` from ``[]``, identical to a plain dict. The server
    casts it to ``dict`` at the one call site (the helpers are not this bundle's to
    re-signature); the values are byte-identical to the materialised map.
    """

    def __init__(self, fold: Fold) -> None:
        self._fold = fold
        self._memo: dict[str, tuple[str, str, str | None] | None] = {}

    def _lookup(self, path: str) -> tuple[str, str, str | None] | None:
        if path not in self._memo:
            self._memo[path] = self._fold.identity_for_path(path)
        return self._memo[path]

    def get(
        self, path: str, default: tuple[str, str, str | None] | None = None
    ) -> tuple[str, str, str | None] | None:
        value = self._lookup(path)
        return default if value is None else value

    def __getitem__(self, path: str) -> tuple[str, str, str | None]:
        value = self._lookup(path)
        if value is None:
            raise KeyError(path)
        return value


# =============================================================================
# ReadModelView — the CorpusReadModel the cache hands consumers, backed by a fold.
# =============================================================================


class ReadModelView:
    """A read-model over the store, materialising each structure lazily on demand.

    Exposes the same surface as :class:`~rac.services.derived_cache.DerivedIndex`
    (the ``CorpusReadModel`` protocol), so ``mcp/server.py`` consumes it unchanged.
    Each property materialises through the fold on first access and caches the
    result for the call; ``get_artifact``/``get_related`` reach only
    :attr:`identity_entries`, so the bulky section and token pages stay unmapped.

    Equality materialises a full :class:`DerivedIndex` and compares — the store is
    asserted equal to a *fresh build*, which is what the disposability and
    byte-parity tests check.
    """

    def __init__(self, fold: Fold) -> None:
        self._fold = fold

    @cached_property
    def identity_entries(self) -> list[IndexEntry]:
        return self._fold.identity_entries()

    @cached_property
    def index_entries(self) -> list[IndexEntry]:
        return self._fold.index_entries()

    @cached_property
    def relationships(self) -> list[Relationship]:
        return self._fold.relationships()

    @cached_property
    def field_tokens_by_path(self) -> dict[str, dict[str, list[str]]]:
        return self._fold.field_tokens_by_path()

    @cached_property
    def live_decision_paths(self) -> list[str]:
        return self._fold.live_decision_paths()

    @cached_property
    def portfolio_summary(self) -> dict:
        return self._fold.portfolio_summary()

    @cached_property
    def scope_rows(self) -> list[ScopeRow]:
        return [
            ScopeRow(id=row[0], title=row[1], status=row[2], path=row[3], scope_entries=row[4])
            for row in self._fold.scope_rows_raw()
        ]

    def search(
        self,
        query: str,
        artifact_type: str | None = None,
        *,
        tags: Sequence[str] | None = None,
    ) -> SearchResult:
        """Postings-served `rac find` search — byte-identical to ``search_index``.

        The store fast path a search-shaped tool takes when the read-model is
        served from the memory-mapped base (the delta is empty): it touches only
        the query terms' prefix ranges and the matched docs' rows, never the whole
        corpus, while producing the same ordered matches, ``match_count``, and
        evidence a fresh whole-corpus walk would. ``tags`` narrows to artifacts
        carrying every requested tag (ADR-109).
        """
        return self._fold.search(query, artifact_type=artifact_type, tags=tags)

    def resolve(self, artifact_id: str) -> ResolutionResult:
        """Point resolution over the persisted alias map — byte-identical to a walk.

        The store fast path ``get_artifact``/``get_related`` take when the read-model
        is served from the memory-mapped base (the delta is empty): a binary search
        over the alias segment plus O(matches) row reads reproduces
        ``resolve_in_index``'s resolved/duplicate/not-found outcomes and sorted
        duplicate paths, never reconstructing the whole identity projection.
        """
        return self._fold.resolve(artifact_id)

    def lazy_identity_by_path(self) -> LazyIdentityByPath:
        """A lazy path -> ``(id, type, title)`` map for ``get_related`` (ADR-104).

        Resolves each requested path through the store's path map on demand, so the
        relationship helpers touch only the edges near the artifact — never the O(N)
        materialised identity projection — while returning the same values.
        """
        return LazyIdentityByPath(self._fold)

    def find_decisions(self, topic: str) -> SearchResult:
        """Live-decision topic search served from the postings (ADR-067).

        The store analogue of :func:`resolve.find_decisions_in`: the decision-typed
        postings search, then the liveness filter over the precomputed live-decision
        paths (a cheap leaf-segment read, not a whole-corpus token materialisation),
        byte-identical to the fresh path.
        """
        result = self._fold.search(topic, artifact_type=_DECISION_TYPE)
        live = set(self.live_decision_paths)
        result.matches = [m for m in result.matches if m.path in live]
        return result

    def to_derived_index(self) -> DerivedIndex:
        return DerivedIndex(
            index_entries=self.index_entries,
            relationships=self.relationships,
            field_tokens_by_path=self.field_tokens_by_path,
            live_decision_paths=self.live_decision_paths,
            portfolio_summary=self.portfolio_summary,
            scope_rows=self.scope_rows,
        )

    def close(self) -> None:
        self._fold.base.close()

    def __enter__(self) -> ReadModelView:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __eq__(self, other: object) -> bool:
        mine = self.to_derived_index()
        if isinstance(other, ReadModelView):
            return mine == other.to_derived_index()
        return mine == other

    __hash__ = None  # type: ignore[assignment]


def open_read_model(cache_dir: Path, corpus_hash: str, bundle_version: str) -> ReadModelView | None:
    """Open the store for ``corpus_hash`` as a read-model view, or ``None`` on a miss.

    A missing directory, a truncated or corrupt segment, a wrong bundle version, a
    scoring-constant change, or a hash mismatch all raise inside the reader and are
    caught here as a miss — never fatal, never an exception to the caller. Fresh
    build then rebuilds and rewrites, so enabling the store only ever changes
    latency.
    """
    directory = store_dir(cache_dir, corpus_hash)
    if not directory.is_dir():
        return None
    try:
        base = MmapIndexReader(directory, corpus_hash, bundle_version)
    except (IndexFormatError, OSError, ValueError):
        return None
    return ReadModelView(Fold(base))


# =============================================================================
# Per-file validation-result store — the incremental-validate substrate (ADR-106).
# =============================================================================
#
# `rac validate DIR --cache` reuses per-file validation results across runs. A
# file's `FileValidation` is a pure function of `(file bytes, resolved config)`
# (core-validate §4), so its result — artifact type, status, and the ordered
# `Issue` list — is cached keyed by content hash under a config fingerprint. The
# store is one binary segment file per corpus root; it doubles as the freshness
# manifest by carrying each file's `(size, mtime_ns, content_hash)` stat proxy in
# the same row, so the CLI needs no second on-disk structure. It follows the same
# ADR-104 discipline as the mmap store: fixed struct reads (no pickle), fail-closed
# on corruption (an `IndexFormatError` is a miss → full recompute), atomic writes.

VALIDATE_STORE_DIRNAME = "validate"
VALIDATE_LAYOUT_VERSION = "v1"


@dataclass(frozen=True)
class ValidationRow:
    """One file's cached validation result plus its freshness stat proxy (ADR-106).

    ``content_hash`` is the parity-bearing key (the result is reused verbatim when
    it is unchanged); ``size``/``mtime_ns`` are the cheap stat prefilter the
    detection scan diffs on. ``artifact_type``/``status``/``issues`` are the
    path-free validation outcome — no ``Issue`` message or line embeds the file
    path, so a rename (same bytes) reuses the row unchanged and the current path is
    re-attached at assembly time.
    """

    size: int
    mtime_ns: int
    content_hash: str
    artifact_type: str
    status: str
    issues: tuple[Issue, ...]


def validate_store_root(cache_dir: Path) -> Path:
    return cache_dir / VALIDATE_STORE_DIRNAME / VALIDATE_LAYOUT_VERSION


def _validate_store_path(cache_dir: Path, root_key: str) -> Path:
    return validate_store_root(cache_dir) / f"{root_key}.vseg"


def _encode_validation_store(config_hash: str, rows: dict[str, ValidationRow]) -> bytes:
    writer = Writer()
    writer.text(config_hash)
    writer.u32(len(rows))
    for rel, row in rows.items():
        writer.text(rel)
        writer.u64(row.size)
        writer.u64(row.mtime_ns)
        writer.text(row.content_hash)
        writer.text(row.artifact_type)
        writer.text(row.status)
        writer.u32(len(row.issues))
        for issue in row.issues:
            writer.text(issue.severity)
            writer.text(issue.code)
            writer.text(issue.message)
            # line is int | None: a presence flag then the value keeps the row a
            # fixed struct read (no sentinel line number can collide with "absent").
            if issue.line is None:
                writer.u32(0)
                writer.u32(0)
            else:
                writer.u32(1)
                writer.u32(issue.line)
    return encode_segment(writer.payload)


def _decode_validation_store(
    payload: memoryview, config_hash: str
) -> dict[str, ValidationRow] | None:
    reader = Reader(payload)
    stored_config = reader.text()
    if stored_config != config_hash:
        # An ancestor `.rac/config.yaml` edit (or a different governing config
        # resolved from another CWD) changes severity overrides / provider, so
        # every cached result is stale — fail closed to a full recompute.
        return None
    count = reader.u32()
    rows: dict[str, ValidationRow] = {}
    for _ in range(count):
        rel = reader.text()
        size = reader.u64()
        mtime_ns = reader.u64()
        content_hash_value = reader.text()
        artifact_type = reader.text()
        status = reader.text()
        issue_count = reader.u32()
        issues: list[Issue] = []
        for _ in range(issue_count):
            severity = reader.text()
            code = reader.text()
            message = reader.text()
            has_line = reader.u32()
            line_value = reader.u32()
            issues.append(
                Issue(
                    severity=severity,  # type: ignore[arg-type]
                    code=code,
                    message=message,
                    line=line_value if has_line else None,
                )
            )
        rows[rel] = ValidationRow(
            size=size,
            mtime_ns=mtime_ns,
            content_hash=content_hash_value,
            artifact_type=artifact_type,
            status=status,
            issues=tuple(issues),
        )
    return rows


def open_validation_store(
    cache_dir: Path, root_key: str, config_hash: str
) -> dict[str, ValidationRow] | None:
    """Load the per-file validation rows for a corpus root, or ``None`` on a miss.

    A missing file, a corrupt or truncated segment, or a config-fingerprint
    mismatch all return ``None`` — the incremental path then treats every file as
    changed and recomputes, so the answer is fresh either way. Never raises to the
    caller; enabling the cache can only change latency, not the result.
    """
    path = _validate_store_path(cache_dir, root_key)
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        payload = segment_payload(memoryview(data))
        return _decode_validation_store(payload, config_hash)
    except (IndexFormatError, ValueError, UnicodeDecodeError):
        return None


def write_validation_store(
    cache_dir: Path, root_key: str, config_hash: str, rows: dict[str, ValidationRow]
) -> bool:
    """Write the per-file validation rows atomically; return whether it landed.

    Built in memory, written to a temp file, fsynced, then ``os.replace``d into the
    root-keyed name in one step, so a concurrent reader never sees a half-written
    store. Any OS error degrades to "not written": the freshly computed results are
    already in hand, so the cache is a latency nicety, never a requirement (ADR-080).
    """
    root = validate_store_root(cache_dir)
    payload = _encode_validation_store(config_hash, rows)
    tmp = root / f".{root_key}.tmp-{os.getpid()}-{os.urandom(4).hex()}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        _write_file(tmp, payload)
        try:
            os.replace(tmp, _validate_store_path(cache_dir, root_key))
        except OSError:
            _silent_unlink_path(tmp)
            return False
        return True
    except OSError:
        _silent_unlink_path(tmp)
        return False


def _silent_unlink_path(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


# =============================================================================
# Per-root freshness-manifest store — the one-shot stat substrate (ADR-112).
# =============================================================================
#
# The one-shot `rac find` cache path verifies freshness with the shared
# stat-manifest scan (freshness.stat_scan) instead of a full byte re-hash, but a
# one-shot process holds no manifest across invocations, so the manifest — each
# file's `(size, mtime_ns, content_hash)` stat proxy — persists here, one binary
# segment file per corpus root and recursion mode. It follows the same discipline
# as the `.vseg` store: fixed struct reads (no pickle), fail-closed on corruption
# (any decode failure is a miss → content-confirm-all scan, which rewrites it),
# atomic writes. The manifest is a pure latency structure: it can never change an
# answer, only how many bytes freshness detection reads (ADR-080).

MANIFEST_DIRNAME = "manifest"
MANIFEST_LAYOUT_VERSION = "v1"
_MANIFEST_FORMAT_VERSION = 1


def manifest_store_root(cache_dir: Path) -> Path:
    return cache_dir / MANIFEST_DIRNAME / MANIFEST_LAYOUT_VERSION


def manifest_root_key(directory: str, *, recursive: bool = True) -> str:
    """A stable key for one corpus root in one recursion mode.

    The recursion mode folds into the key because `rac find` and
    `rac find --top-level` walk different file sets from the same root: a shared
    manifest would thrash between them and could vouch for files the narrower
    walk never enumerates.
    """
    import hashlib

    mode = "recursive" if recursive else "top-level"
    seed = f"{Path(directory).resolve()}\0{mode}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _manifest_store_path(cache_dir: Path, root_key: str) -> Path:
    return manifest_store_root(cache_dir) / f"{root_key}.fseg"


def open_freshness_manifest(cache_dir: Path, root_key: str) -> dict | None:
    """Load the persisted stat manifest for a corpus root, or ``None`` on a miss.

    A missing file, a corrupt or truncated segment, or a format-version mismatch
    all return ``None`` — the caller then runs the content-confirm-all scan, so
    the answer is fresh either way and the rewrite self-heals the store. Never
    raises to the caller.
    """
    from rac.services.freshness import FileState

    path = _manifest_store_path(cache_dir, root_key)
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        reader = Reader(segment_payload(memoryview(data)))
        if reader.u32() != _MANIFEST_FORMAT_VERSION:
            return None
        count = reader.u32()
        manifest: dict[str, FileState] = {}
        for _ in range(count):
            rel = reader.text()
            size = reader.u64()
            mtime_ns = reader.u64()
            digest = reader.text()
            manifest[rel] = FileState(content_hash=digest, size=size, mtime_ns=mtime_ns)
        return manifest
    except (IndexFormatError, ValueError, UnicodeDecodeError):
        return None


def write_freshness_manifest(cache_dir: Path, root_key: str, manifest: dict) -> bool:
    """Write the stat manifest atomically; return whether it landed.

    Built in memory, written to a temp file, then ``os.replace``d into the
    root-keyed name in one step. Any OS error degrades to "not written": the
    scan already produced the fresh manifest in memory, so persistence is a
    latency nicety, never a requirement.
    """
    root = manifest_store_root(cache_dir)
    writer = Writer()
    writer.u32(_MANIFEST_FORMAT_VERSION)
    writer.u32(len(manifest))
    for rel, state in manifest.items():
        writer.text(rel)
        writer.u64(state.size)
        writer.u64(state.mtime_ns)
        writer.text(state.content_hash)
    payload = encode_segment(writer.payload)
    tmp = root / f".{root_key}.tmp-{os.getpid()}-{os.urandom(4).hex()}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        _write_file(tmp, payload)
        try:
            os.replace(tmp, _manifest_store_path(cache_dir, root_key))
        except OSError:
            _silent_unlink_path(tmp)
            return False
        return True
    except OSError:
        _silent_unlink_path(tmp)
        return False
