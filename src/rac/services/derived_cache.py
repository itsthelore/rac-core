"""Content-addressed derived-index cache (ADR-099, `lore-at-team-scale` #264).

Every read rebuilds the same expensive derived structures from disk: the
repository index, the resolved relationship graph, and the tokenised field
vectors BM25 scores over. ADR-032 deliberately kept that rebuild on the serving
path and recorded its own review trigger — a real user reporting latency at
scale. That report has arrived, and ADR-099 answers it: a *disposable,
content-addressed* cache of those structures, byte-identical to the uncached
path, revising the "no persistent cache on the serving path" pin by decision.

The cache is a pure optimisation behind the corpus-snapshot seam:

- **Content-addressed** (ADR-002): keyed on :func:`corpus_content_hash`, so any
  byte change to any artifact — or any add, remove, or rename — changes the key
  and forces a rebuild. There is no time- or event-based invalidation.
- **Fresh per call** (ADR-032): the key is recomputed every call, so no call can
  observe stale state; derived structures are reused only under an unchanged key.
- **Disposable, never authoritative** (ADR-080): the files in git are the truth;
  this is a rebuildable index. Deleting the cache directory — or a corrupt or
  unreadable cache file — costs only latency, never correctness: the reader falls
  back to a fresh build. No daemon, no lockfile protocol, no datastore semantics.
- **Byte-parity is the coherency guarantee** (REQ-002): the structures are
  serialised and rehydrated losslessly, and every consumer produces identical
  output whether a structure came from cache or fresh compute.

This is a read-only cache service; it writes only to its own disposable cache
directory (default ``$XDG_CACHE_HOME/rac/derived``), never to the corpus.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rac.core.artifacts import spec_for
from rac.core.corpus import CorpusEntry, corpus_content_hash, walk_corpus
from rac.core.identity import artifact_identifier
from rac.core.models import SearchSection
from rac.services.agent_rules import artifact_status, is_live_decision
from rac.services.index import IndexEntry, index_from_corpus
from rac.services.portfolio import portfolio_from_corpus
from rac.services.references import SCOPE_SECTIONS, extract_relationships_full
from rac.services.relationships import (
    Relationship,
    inbound_counts_from_relationships,
    relationships_from_corpus,
    resolution_index_from_entries,
)
from rac.services.resolve import field_tokens_for_entries, live_decision_paths

# Byte-parity requires the identical scope matcher, and this bundle (ADR-103)
# does not open `services/scope.py`, so the two path-mode matchers are reused as
# imports rather than duplicated — duplicating the segment-aware glob compiler
# would be a parity liability. A future public seam on `scope` would remove the
# private reach; until then the coupling is one-directional (scope never imports
# this module) and deliberate.
from rac.services.scope import (  # noqa: PLC2701 - deliberate reuse; see note above
    GoverningDecision,
    ScopeLookupResult,
    _entry_covers,
    _normalize_query,
)
from rac.services.scope_paths import repository_root

# The bundle schema version — the *shape* of the derived structures. It gates
# both the small marker file and the store header (a mismatch on either is a
# miss, rebuilt fresh), so a shape change can never rehydrate a stale bundle
# (ADR-007). Bumped to "2" by ADR-103 (portfolio summary + scope rows). ADR-104
# changes the on-disk *encoding* (a memory-mapped segment directory, no longer a
# JSON blob) but not the bundle shape, so the version stays "2"; the encoding is
# versioned independently by the store's own segment-format and layout versions,
# and an old JSON blob is simply never opened as a store (a miss).
# Bumped to "3" by the tags tier (ADR-109): the store's bundle version, so a
# store built before the tags field fails the bundle-version gate and rebuilds.
SCHEMA_VERSION = "3"

_DECISION_TYPE = "decision"

CACHE_DIRNAME = "derived"
CACHE_DIR_ENV = "RAC_CACHE_DIR"


@dataclass(frozen=True)
class ScopeRow:
    """One live decision's declared ``## Applies To`` scope, precomputed (ADR-103).

    The path mode of ``find_decisions`` matches a queried code path against every
    live decision's declared scope entries. Carrying the identity plus the ordered
    declared entries per live decision lets that answer be served from the cached
    read-model instead of a fresh walk, byte-identically to ``decisions_for_path``.

    ``scope_entries`` are the declared entries in the exact order
    ``scope._governing`` scans them (``SCOPE_SECTIONS`` order, declared order
    within each), so the reported ``matching_entry`` — the first covering entry —
    is preserved.
    """

    id: str
    title: str
    status: str
    path: str
    scope_entries: tuple[str, ...]


@dataclass(frozen=True)
class DerivedIndex:
    """The expensive derived structures for one corpus snapshot (ADR-099/ADR-103).

    Each field is a pure function of the corpus bytes, so the whole bundle is
    content-addressable and losslessly serialisable:

    - ``index_entries`` — the repository index rows (identity, type, title, path,
      aliases, searchable sections, inbound edge count).
    - ``relationships`` — the resolved relationship graph.
    - ``field_tokens_by_path`` — the tokenised BM25 field vectors, keyed by path.
    - ``live_decision_paths`` — the Accepted, non-retired decision paths, so the
      ``find_decisions`` liveness filter needs no parsed products.
    - ``portfolio_summary`` — the ``get_summary`` portfolio dict (ADR-103),
      computed once through ``portfolio_from_corpus`` over the same snapshot, so
      the heaviest tool builds through this one composer instead of re-walking.
    - ``scope_rows`` — the per-live-decision ``## Applies To`` rows (ADR-103) the
      path mode of ``find_decisions`` matches against, so it needs no fresh walk.
    """

    index_entries: list[IndexEntry]
    relationships: list[Relationship]
    field_tokens_by_path: dict[str, dict[str, list[str]]]
    live_decision_paths: list[str]
    portfolio_summary: dict
    scope_rows: list[ScopeRow]

    @property
    def identity_entries(self) -> list[IndexEntry]:
        """The identity-only projection resolution reads (aliases + path).

        The read-model surface (:class:`CorpusReadModel`) is uniform across the
        fresh :class:`DerivedIndex` and the store-backed view: the store serves
        this from point-accessed identity rows without mapping the section/token
        pages, and the fresh build projects it here so ``get_artifact`` /
        ``get_related`` share one accessor. Byte-identical to reading the full
        rows — only the searchable sections and inbound count are elided, and
        resolution reads neither.
        """
        return [
            IndexEntry(id=e.id, type=e.type, title=e.title, path=e.path, aliases=list(e.aliases))
            for e in self.index_entries
        ]


class CorpusReadModel(Protocol):
    """The read-model surface every serving-path consumer reads (ADR-099/ADR-104).

    Both the fresh :class:`DerivedIndex` and the persistent store's lazily
    materialised view satisfy it, so ``mcp/server.py`` consumes either without a
    branch. The store maps only the pages a given member needs; the fresh build
    holds them all in memory. Output is byte-identical across the two.
    """

    @property
    def index_entries(self) -> list[IndexEntry]: ...
    @property
    def identity_entries(self) -> list[IndexEntry]: ...
    @property
    def relationships(self) -> list[Relationship]: ...
    @property
    def field_tokens_by_path(self) -> dict[str, dict[str, list[str]]]: ...
    @property
    def live_decision_paths(self) -> list[str]: ...
    @property
    def portfolio_summary(self) -> dict: ...
    @property
    def scope_rows(self) -> list[ScopeRow]: ...


def scope_row_from_entry(entry: CorpusEntry) -> ScopeRow | None:
    """The path-mode :class:`ScopeRow` for one entry, or None when it declares none.

    The per-document projection shared by the serial :func:`_scope_rows_from_corpus`
    and the parallel merge (ADR-108). Faithful to ``scope._governing``'s extraction:
    only a live decision that declares ``## Applies To`` (``SCOPE_SECTIONS``) entries
    yields a row; anything else returns None (a decision with no scope can never
    cover a query, so omitting it changes no answer).
    """
    product = entry.product
    if entry.artifact_type != _DECISION_TYPE or not is_live_decision(product):
        return None
    spec = spec_for(entry.artifact_type)
    if spec is None:  # the decision spec is always registered; narrow for typing
        return None
    relationships = extract_relationships_full(product, spec)
    declared: list[str] = []
    for section in SCOPE_SECTIONS:
        declared.extend(relationships.get(section.replace(" ", "_"), []))
    if not declared:
        return None
    return ScopeRow(
        id=artifact_identifier(product, spec, str(entry.path)),
        title=product.title or "",
        status=artifact_status(product),
        path=str(entry.path),
        scope_entries=tuple(declared),
    )


def _scope_rows_from_corpus(entries: list[CorpusEntry]) -> list[ScopeRow]:
    """Precompute the path-mode scope rows for every live decision that declares scope.

    Faithful to ``scope._governing``'s extraction: only live decisions, only the
    ``## Applies To`` (``SCOPE_SECTIONS``) entries, flattened in scan order. A
    decision that declares no scope can never cover a query, so it is omitted —
    dropping it changes no answer, exactly as ``_governing`` would return ``None``.
    """
    return [row for entry in entries if (row := scope_row_from_entry(entry)) is not None]


def governing_decisions(scope_rows: list[ScopeRow], directory: str, path: str) -> ScopeLookupResult:
    """The live decisions governing ``path``, matched over precomputed scope rows.

    Byte-identical to :func:`rac.services.scope.decisions_for_path` for the same
    corpus and path — the same repository-root discovery, query normalisation,
    segment-aware coverage test, and ``(id.casefold(), path)`` ordering — but over
    the read-model's precomputed rows (ADR-103), so no fresh walk is needed. The
    server always builds the rows recursively, matching the tool's ``recursive``.
    """
    root = repository_root(directory)
    query = _normalize_query(path, root)
    if query is None:
        return ScopeLookupResult(query=path.strip(), in_repository=False, decisions=[])
    matches: list[GoverningDecision] = []
    for row in scope_rows:
        for declared in row.scope_entries:
            if _entry_covers(declared, query):
                matches.append(
                    GoverningDecision(
                        id=row.id,
                        title=row.title,
                        status=row.status,
                        path=row.path,
                        matching_entry=declared,
                    )
                )
                break
    matches.sort(key=lambda d: (d.id.casefold(), d.path))
    return ScopeLookupResult(query=query, in_repository=True, decisions=matches)


def build_derived_index_from_entries(
    directory: str, entries: list[CorpusEntry], *, recursive: bool = True
) -> DerivedIndex:
    """Build the derived structures from an already-walked corpus snapshot.

    The from-parts seam :func:`build_derived_index` composes, factored out so an
    event-sourced serving tracker (ADR-105) that re-parses only the *changed*
    files can re-derive the whole read-model over its incrementally-maintained
    snapshot without a fresh walk — byte-identically to :func:`build_derived_index`
    for the same corpus state, because ``entries`` is the same sorted-path snapshot
    ``walk_corpus`` would yield. Every derived structure is a pure function of the
    snapshot, so identical entries in identical order give identical bytes.
    """
    # Resolve the reference graph once and share the index across every consumer
    # that would otherwise rebuild it (relationships, the portfolio's summary, and
    # its relationship validation) — byte-identical, since the index is a pure
    # function of the snapshot. The cold build resolved it three times before.
    resolution_index = resolution_index_from_entries(entries)
    rels = relationships_from_corpus(entries, resolution_index=resolution_index)
    inbound = inbound_counts_from_relationships(rels)
    index = index_from_corpus(directory, entries, recursive=recursive, inbound=inbound)
    return DerivedIndex(
        index_entries=index.artifacts,
        relationships=rels,
        field_tokens_by_path=field_tokens_for_entries(index.artifacts),
        live_decision_paths=live_decision_paths(entries),
        portfolio_summary=portfolio_from_corpus(
            directory, entries, recursive=recursive, resolution_index=resolution_index
        ).to_dict(),
        scope_rows=_scope_rows_from_corpus(entries),
    )


def build_derived_index(directory: str, *, recursive: bool = True) -> DerivedIndex:
    """Build the derived structures fresh from one corpus walk (the cache miss path).

    One walk feeds every structure, exactly as the uncached consumers build them
    individually, so a cache-populated call and a fresh call are byte-identical.
    The portfolio summary and scope rows (ADR-103) ride the same walk, so the two
    formerly cache-bypassing tools build through this one composer too.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    return build_derived_index_from_entries(directory, entries, recursive=recursive)


def _index_entry_to_obj(entry: IndexEntry) -> dict:
    return {
        "id": entry.id,
        "type": entry.type,
        "title": entry.title,
        "path": entry.path,
        "aliases": list(entry.aliases),
        "search_sections": [
            {"heading": sec.heading, "lines": list(sec.lines)} for sec in entry.search_sections
        ],
        "inbound_count": entry.inbound_count,
    }


def _index_entry_from_obj(obj: dict) -> IndexEntry:
    return IndexEntry(
        id=obj["id"],
        type=obj["type"],
        title=obj["title"],
        path=obj["path"],
        aliases=list(obj["aliases"]),
        search_sections=[
            SearchSection(heading=sec["heading"], lines=list(sec["lines"]))
            for sec in obj["search_sections"]
        ],
        inbound_count=obj["inbound_count"],
    )


def _relationship_to_obj(rel: Relationship) -> dict:
    return {
        "source_path": rel.source_path,
        "relationship": rel.relationship,
        "target": rel.target,
        "resolved_path": rel.resolved_path,
        "issue": rel.issue,
    }


def _relationship_from_obj(obj: dict) -> Relationship:
    return Relationship(
        source_path=obj["source_path"],
        relationship=obj["relationship"],
        target=obj["target"],
        resolved_path=obj["resolved_path"],
        issue=obj["issue"],
    )


def _scope_row_to_obj(row: ScopeRow) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "path": row.path,
        "scope_entries": list(row.scope_entries),
    }


def _scope_row_from_obj(obj: dict) -> ScopeRow:
    return ScopeRow(
        id=obj["id"],
        title=obj["title"],
        status=obj["status"],
        path=obj["path"],
        scope_entries=tuple(obj["scope_entries"]),
    )


def to_json_obj(derived: DerivedIndex) -> dict:
    """Serialise a :class:`DerivedIndex` to a JSON-ready object (lossless)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "index_entries": [_index_entry_to_obj(e) for e in derived.index_entries],
        "relationships": [_relationship_to_obj(r) for r in derived.relationships],
        "field_tokens_by_path": derived.field_tokens_by_path,
        "live_decision_paths": list(derived.live_decision_paths),
        # ADR-103: the portfolio dict is already the JSON get_summary serves, so it
        # embeds directly; the scope rows are plain strings.
        "portfolio_summary": derived.portfolio_summary,
        "scope_rows": [_scope_row_to_obj(r) for r in derived.scope_rows],
    }


def from_json_obj(obj: dict) -> DerivedIndex:
    """Rehydrate a :class:`DerivedIndex` from :func:`to_json_obj` output.

    Raises on a shape or version mismatch; the cache treats any raise as a miss
    and rebuilds, so a bad file is never fatal.
    """
    if obj.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"derived-cache schema mismatch: {obj.get('schema_version')!r}")
    return DerivedIndex(
        index_entries=[_index_entry_from_obj(e) for e in obj["index_entries"]],
        relationships=[_relationship_from_obj(r) for r in obj["relationships"]],
        field_tokens_by_path={
            path: {field: list(tokens) for field, tokens in fields.items()}
            for path, fields in obj["field_tokens_by_path"].items()
        },
        live_decision_paths=list(obj["live_decision_paths"]),
        portfolio_summary=obj["portfolio_summary"],
        scope_rows=[_scope_row_from_obj(r) for r in obj["scope_rows"]],
    )


def default_cache_dir() -> Path:
    """The derived-cache directory: ``RAC_CACHE_DIR`` > ``$XDG_CACHE_HOME/rac/derived``.

    A cache location, not a state location — deleting it is always safe (ADR-080).
    """
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "rac" / CACHE_DIRNAME


class DerivedIndexCache:
    """Disposable, content-addressed persistence of the derived structures (ADR-099/ADR-104).

    :meth:`load_or_build` is the whole surface: it hashes the corpus and, under an
    unchanged key, returns a read-model *view* backed by the memory-mapped index
    store (ADR-104) instead of rehydrating a JSON blob — point access, no per-call
    peak-allocation spike. Otherwise it rebuilds through :func:`build_derived_index`,
    writes the store, and returns a view over it. Every failure mode degrades to a
    fresh build — an unwritable directory, a corrupt or truncated segment, a schema
    or scoring-constant mismatch — so enabling the cache can never change an answer
    or fail a call, only its latency.

    On disk the cache dir holds a small ``{hash}.json`` marker (the fail-closed
    schema gate) beside a ``store/`` subdirectory of the mapped segment files. A
    marker present implies its store is present (the store is written first). An
    old ADR-099/ADR-103 JSON blob under the same ``{hash}.json`` name has no store
    beside it, so it opens as a miss and is rebuilt — old JSON files are ignored.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir if cache_dir is not None else default_cache_dir()

    def _marker_path(self, corpus_hash: str) -> Path:
        return self.cache_dir / f"{corpus_hash}.json"

    def load_or_build(self, directory: str, *, recursive: bool = True) -> CorpusReadModel:
        # Freshness (REQ-006): the key is recomputed every call, so any corpus
        # change since the previous call is observed before anything is reused.
        from rac.services.index_store import open_read_model, remove_store

        corpus_hash = corpus_content_hash(directory, recursive=recursive)
        if self._marker_valid(corpus_hash):
            view = open_read_model(self.cache_dir, corpus_hash, SCHEMA_VERSION)
            if view is not None:
                return view
            # The marker claimed a store but it is corrupt, truncated, or written
            # under a stale format/scoring constant: clear it so the rebuild below
            # writes a fresh store rather than skipping the unusable directory. The
            # answer is still fresh either way — this only restores the cache.
            remove_store(self.cache_dir, corpus_hash)
        # Cold miss: build the store from nothing with a parallel parse (ADR-107).
        # Byte-identical to the serial build — the parse is fanned across processes
        # but produces the same sorted-path snapshot the serial derive consumes — so
        # the store written here equals a single-process build's, only faster to
        # produce. The default no-cache CLI paths keep calling build_derived_index
        # directly (single-process, one-shot); parallelism lives on this cached path
        # where the up-front fork cost is amortised into a persisted store.
        import time

        from rac.services.parallel_build import build_derived_index_parallel, emit_build_timing

        derived, stats = build_derived_index_parallel(directory, recursive=recursive)
        write_start = time.perf_counter()
        store_written = self._write_store(corpus_hash, derived)
        stats.write_ms = (time.perf_counter() - write_start) * 1000.0
        emit_build_timing(stats)
        if self._write_marker(corpus_hash, store_written):
            view = open_read_model(self.cache_dir, corpus_hash, SCHEMA_VERSION)
            if view is not None:
                return view
        # The store could not be written or reopened (unwritable dir, race); the
        # freshly built bundle is a valid read-model in its own right (ADR-080).
        return derived

    def _marker_valid(self, corpus_hash: str) -> bool:
        try:
            obj = json.loads(self._marker_path(corpus_hash).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        # Only the schema version gates the marker; a wrong-version marker (an old
        # JSON blob, or a hand-bumped file) fails closed to a miss. from_json_obj
        # raises on that same version check, which the corrupt/schema tests assert.
        return isinstance(obj, dict) and obj.get("schema_version") == SCHEMA_VERSION

    def _write_store(self, corpus_hash: str, derived: DerivedIndex) -> bool:
        from rac.services.index_store import write_store

        return write_store(self.cache_dir, corpus_hash, SCHEMA_VERSION, derived)

    def _write_marker(self, corpus_hash: str, store_written: bool) -> bool:
        """Write the schema-gate marker after the store landed; return success.

        The store is the data and is written first, so a present marker always has
        a present store beside it. Marker write is atomic (temp + ``os.replace``)
        so a concurrent reader never sees a half-written gate.
        """
        if not store_written:
            return False
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps({"schema_version": SCHEMA_VERSION, "corpus_hash": corpus_hash})
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_dir,
                prefix=f".{corpus_hash}.",
                suffix=".tmp",
                delete=False,
            )
            try:
                with handle:
                    handle.write(payload)
                os.replace(handle.name, self._marker_path(corpus_hash))
            except OSError:
                _silent_unlink(handle.name)
                raise
        except OSError:
            return False
        return True


def _silent_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
