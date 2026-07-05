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

from rac.core.artifacts import spec_for
from rac.core.corpus import CorpusEntry, corpus_content_hash, walk_corpus
from rac.core.identity import artifact_identifier
from rac.core.models import SearchSection
from rac.services.agent_rules import artifact_status, is_live_decision
from rac.services.index import IndexEntry, index_from_corpus
from rac.services.portfolio import portfolio_from_corpus
from rac.services.references import SCOPE_SECTIONS, extract_relationships_full
from rac.services.relationships import Relationship, relationships_from_corpus
from rac.services.resolve import field_tokens_for_entries, live_decision_paths

# Byte-parity requires the identical scope matcher, and this bundle (ADR-100)
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

# Bumping this discards every existing cache file (they carry it and a mismatch
# is treated as a miss), so a serialisation change can never rehydrate stale
# shapes. A recorded decision, like any pinned schema (ADR-007). Bumped to "2"
# by ADR-100, which extends the cached bundle with the portfolio summary and the
# per-decision scope rows — an old-shape "1" file fails the gate and rebuilds.
SCHEMA_VERSION = "2"

_DECISION_TYPE = "decision"

CACHE_DIRNAME = "derived"
CACHE_DIR_ENV = "RAC_CACHE_DIR"


@dataclass(frozen=True)
class ScopeRow:
    """One live decision's declared ``## Applies To`` scope, precomputed (ADR-100).

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
    """The expensive derived structures for one corpus snapshot (ADR-099/ADR-100).

    Each field is a pure function of the corpus bytes, so the whole bundle is
    content-addressable and losslessly serialisable:

    - ``index_entries`` — the repository index rows (identity, type, title, path,
      aliases, searchable sections, inbound edge count).
    - ``relationships`` — the resolved relationship graph.
    - ``field_tokens_by_path`` — the tokenised BM25 field vectors, keyed by path.
    - ``live_decision_paths`` — the Accepted, non-retired decision paths, so the
      ``find_decisions`` liveness filter needs no parsed products.
    - ``portfolio_summary`` — the ``get_summary`` portfolio dict (ADR-100),
      computed once through ``portfolio_from_corpus`` over the same snapshot, so
      the heaviest tool builds through this one composer instead of re-walking.
    - ``scope_rows`` — the per-live-decision ``## Applies To`` rows (ADR-100) the
      path mode of ``find_decisions`` matches against, so it needs no fresh walk.
    """

    index_entries: list[IndexEntry]
    relationships: list[Relationship]
    field_tokens_by_path: dict[str, dict[str, list[str]]]
    live_decision_paths: list[str]
    portfolio_summary: dict
    scope_rows: list[ScopeRow]


def _scope_rows_from_corpus(entries: list[CorpusEntry]) -> list[ScopeRow]:
    """Precompute the path-mode scope rows for every live decision that declares scope.

    Faithful to ``scope._governing``'s extraction: only live decisions, only the
    ``## Applies To`` (``SCOPE_SECTIONS``) entries, flattened in scan order. A
    decision that declares no scope can never cover a query, so it is omitted —
    dropping it changes no answer, exactly as ``_governing`` would return ``None``.
    """
    rows: list[ScopeRow] = []
    for entry in entries:
        product = entry.product
        if entry.artifact_type != _DECISION_TYPE or not is_live_decision(product):
            continue
        spec = spec_for(entry.artifact_type)
        if spec is None:  # the decision spec is always registered; narrow for typing
            continue
        relationships = extract_relationships_full(product, spec)
        declared: list[str] = []
        for section in SCOPE_SECTIONS:
            declared.extend(relationships.get(section.replace(" ", "_"), []))
        if not declared:
            continue
        rows.append(
            ScopeRow(
                id=artifact_identifier(product, spec, str(entry.path)),
                title=product.title or "",
                status=artifact_status(product),
                path=str(entry.path),
                scope_entries=tuple(declared),
            )
        )
    return rows


def governing_decisions(scope_rows: list[ScopeRow], directory: str, path: str) -> ScopeLookupResult:
    """The live decisions governing ``path``, matched over precomputed scope rows.

    Byte-identical to :func:`rac.services.scope.decisions_for_path` for the same
    corpus and path — the same repository-root discovery, query normalisation,
    segment-aware coverage test, and ``(id.casefold(), path)`` ordering — but over
    the read-model's precomputed rows (ADR-100), so no fresh walk is needed. The
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


def build_derived_index(directory: str, *, recursive: bool = True) -> DerivedIndex:
    """Build the derived structures fresh from one corpus walk (the cache miss path).

    One walk feeds every structure, exactly as the uncached consumers build them
    individually, so a cache-populated call and a fresh call are byte-identical.
    The portfolio summary and scope rows (ADR-100) ride the same walk, so the two
    formerly cache-bypassing tools build through this one composer too.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    index = index_from_corpus(directory, entries, recursive=recursive)
    return DerivedIndex(
        index_entries=index.artifacts,
        relationships=relationships_from_corpus(entries),
        field_tokens_by_path=field_tokens_for_entries(index.artifacts),
        live_decision_paths=live_decision_paths(entries),
        portfolio_summary=portfolio_from_corpus(directory, entries, recursive=recursive).to_dict(),
        scope_rows=_scope_rows_from_corpus(entries),
    )


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
        # ADR-100: the portfolio dict is already the JSON get_summary serves, so it
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
    """Disposable, content-addressed persistence of the derived structures (ADR-099).

    :meth:`load_or_build` is the whole surface: it hashes the corpus, returns the
    cached structures under an unchanged key, and otherwise rebuilds and persists
    them. Every failure mode degrades to a fresh build — an unwritable directory,
    a corrupt file, a schema mismatch — so enabling the cache can never change an
    answer or fail a call, only its latency.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir if cache_dir is not None else default_cache_dir()

    def _path_for(self, corpus_hash: str) -> Path:
        return self.cache_dir / f"{corpus_hash}.json"

    def load_or_build(self, directory: str, *, recursive: bool = True) -> DerivedIndex:
        # Freshness (REQ-006): the key is recomputed every call, so any corpus
        # change since the previous call is observed before anything is reused.
        corpus_hash = corpus_content_hash(directory, recursive=recursive)
        cached = self._read(corpus_hash)
        if cached is not None:
            return cached
        derived = build_derived_index(directory, recursive=recursive)
        self._write(corpus_hash, derived)
        return derived

    def _read(self, corpus_hash: str) -> DerivedIndex | None:
        path = self._path_for(corpus_hash)
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            return from_json_obj(obj)
        except (OSError, ValueError, KeyError, TypeError):
            # Missing, unreadable, corrupt, or wrong-shaped: a miss, never fatal.
            return None

    def _write(self, corpus_hash: str, derived: DerivedIndex) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(to_json_obj(derived), ensure_ascii=False)
            # Atomic replace so a concurrent reader never sees a half-written file
            # (two shared-server requests may build the same key at once; the
            # content is identical, so last-writer-wins is safe).
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
                os.replace(handle.name, self._path_for(corpus_hash))
            except OSError:
                _silent_unlink(handle.name)
                raise
        except OSError:
            # The cache is a nicety, not a requirement: if it cannot be written,
            # the freshly built structures are already being returned (ADR-080).
            pass


def _silent_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
