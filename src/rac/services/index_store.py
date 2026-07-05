"""Persistent memory-mapped index store + base/delta fold (ADR-101).

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
separately (ADR-102).

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
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from rac.core.models import SearchSection
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
    _bm25f_scored,
)

# The scorable field families, in the exact BM25F iteration order (ADR-078). The
# store persists per-field token-id sequences and length accumulators in this
# order; the fold feeds them back to the shared scorer in the same order, so the
# float summation order — the parity-critical one — is preserved.
FIELDS: tuple[str, ...] = tuple(_FIELD_BOOSTS)
assert FIELDS == ("id", "title", "path", "heading", "body"), "field order is a parity contract"

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
_SEG_RELATIONSHIPS = "relationships.seg"
_SEG_LIVE = "live.seg"
_SEG_SCOPE = "scope.seg"
_SEG_PORTFOLIO = "portfolio.seg"

_ALL_SEGMENTS = (
    _SEG_HEADER,
    _SEG_ENTRIES,
    _SEG_SECTIONS,
    _SEG_TOKENS,
    _SEG_TERMDICT,
    _SEG_RELATIONSHIPS,
    _SEG_LIVE,
    _SEG_SCOPE,
    _SEG_PORTFOLIO,
)


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


def _build_segments(
    corpus_hash: str, bundle_version: str, derived: DerivedIndex
) -> dict[str, bytes]:
    """Encode a :class:`~rac.services.derived_cache.DerivedIndex` to segment bytes.

    Docids are assigned in ``index_entries`` order — the corpus walk's sorted-path
    order — and every structure keyed to a doc uses that order, so materialisation
    reproduces the fresh bundle exactly.
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
    for entry in entries:
        fields = field_tokens[entry.path]
        lengths = [len(fields[name]) for name in FIELDS]
        for i, value in enumerate(lengths):
            length_sums[i] += value

        row = Writer()
        row.text(entry.id)
        row.text(entry.type)
        row.opt_text(entry.title)
        row.text(entry.path)
        row.text_list(list(entry.aliases))
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

        tok = Writer()
        for name in FIELDS:
            tok.u32_list([term_id[token] for token in fields[name]])
        token_rows.append(tok.payload)

    termdict_rows = [_encode_text(term) for term in termdict]

    relationships = Writer()
    rels: list[Relationship] = list(derived.relationships)
    relationships.u32(len(rels))
    for rel in rels:
        relationships.text(rel.source_path)
        relationships.text(rel.relationship)
        relationships.text(rel.target)
        relationships.opt_text(rel.resolved_path)
        relationships.opt_text(rel.issue)

    live = Writer()
    live.text_list(list(derived.live_decision_paths))

    scope = Writer()
    scope_rows = list(derived.scope_rows)
    scope.u32(len(scope_rows))
    for scope_row in scope_rows:
        scope.text(scope_row.id)
        scope.text(scope_row.title)
        scope.text(scope_row.status)
        scope.text(scope_row.path)
        scope.text_list(list(scope_row.scope_entries))

    portfolio = Writer()
    # The portfolio summary is itself a JSON wire payload (get_summary serves it
    # verbatim). It is stored as its canonical JSON text in a single leaf blob —
    # data, decoded with ``json.loads`` on demand, never code (no pickle). This is
    # the one place JSON survives; every structural segment is binary.
    portfolio.text(json.dumps(derived.portfolio_summary, ensure_ascii=False))

    header = Writer()
    header.text(corpus_hash)
    header.text(bundle_version)
    header.text(scoring_fingerprint())
    header.u32(len(entries))
    for value in length_sums:
        header.u32(value)
    header.u32(len(termdict))

    return {
        _SEG_HEADER: encode_segment(header.payload),
        _SEG_ENTRIES: encode_segment(write_indexed(entry_rows)),
        _SEG_SECTIONS: encode_segment(write_indexed(section_rows)),
        _SEG_TOKENS: encode_segment(write_indexed(token_rows)),
        _SEG_TERMDICT: encode_segment(write_indexed(termdict_rows)),
        _SEG_RELATIONSHIPS: encode_segment(relationships.payload),
        _SEG_LIVE: encode_segment(live.payload),
        _SEG_SCOPE: encode_segment(scope.payload),
        _SEG_PORTFOLIO: encode_segment(portfolio.payload),
    }


def _encode_text(value: str) -> bytes:
    writer = Writer()
    writer.text(value)
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
        return True
    segments = _build_segments(corpus_hash, bundle_version, derived)
    tmp = root / f".{corpus_hash}.tmp-{os.getpid()}-{os.urandom(4).hex()}"
    try:
        tmp.mkdir(parents=True, exist_ok=True)
        for name, payload in segments.items():
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
        return IndexEntry(id=entry_id, type=entry_type, title=title, path=path, aliases=aliases)

    def full_entry(self, docid: int) -> IndexEntry:
        """The full index row: identity plus searchable sections and inbound count."""
        reader = self._entries().row(docid)
        entry_id = reader.text()
        entry_type = reader.text()
        title = reader.opt_text()
        path = reader.text()
        aliases = reader.text_list()
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
        reader.text_list()
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
    """The mutable overlay a later bundle folds over the base — EMPTY here (ADR-101).

    The seams are declared now so mutation can be added without touching any
    consumer, which already reads through :class:`Fold`:

    - ``tombstones`` — base docids whose file changed or vanished, masked from
      every fold (docs, postings, stats, edges, scope, live).
    - ``added_paths`` — the identity of docs the delta adds, so the fold's key-set
      stays exactly the live corpus set (the cache-key-set == entry-set invariant).
    - stat adjustments, added rows, and term deltas belong here too; they stay
      unpopulated until the freshness decision (ADR-102) that owns them.
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
        # needs the stat-adjustment seam (ADR-102). With the empty delta the base
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
        prefix range — the same value ``_corpus_stats`` derives by walking tokens,
        computed here from the sorted term dictionary's binary-searched range.
        """
        lo, hi = self.base.prefix_range(term)
        if lo >= hi:
            return 0
        count = 0
        for docid in self.live_docids():
            ids = self.base.forward_token_ids(docid)
            if any(lo <= tid < hi for name in FIELDS for tid in ids[name]):
                count += 1
        return count

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
