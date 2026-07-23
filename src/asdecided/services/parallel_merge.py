"""Term-range-partitioned parallel merge of the derived read-model (ADR-108).

ADR-107 fanned the cold build's *parse* across processes but left the whole
*derive* serial: workers shipped parsed :class:`~asdecided.core.corpus.CorpusEntry`
objects and the parent ran :func:`build_derived_index_from_entries` alone.
ADR-108 finishes the fan-out — workers emit compact per-document *derived
fragments* and the parent reproduces the read-model from them, so the
per-document derivations (validation, tokenisation, scope/live projection) run in
the workers too and only compact rows cross the process boundary.

**A fragment is the whole per-document projection each derivation reads, with the
``Product`` dropped.** :class:`DocFragment` carries the index row, the six BM25
field-token vectors, the portfolio row (its validation projection and per-document
findings), the live-decision flag, and the scope row — every field a pure function
of one parsed document. :func:`fragment_from_entry` builds one in the parent (from
a parsed entry); the worker builds the same fragment from the same parse, so the
two are identical.

**The merge is the cross-document step, and only the cross-document step.**
:func:`reproduce` resolves the reference graph over the fragments' identifier and
edge rows (in sorted-path order, so the docids and every derived byte are
worker-count-invariant), fills each index row's inbound count from that graph,
and reads every other field straight off the fragments. It routes through the
same compact-row seams the serial build uses — :func:`resolution_index_from_rows`,
:func:`relationships_from_rows`, :func:`portfolio_from_rows` — so the reproduced
:class:`DerivedIndex` is byte-identical to :func:`build_derived_index_from_entries`
over the same snapshot by construction, not by coincidence. That equality is the
ADR-108 gate the tests pin.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from asdecided.core.corpus import CorpusEntry
from asdecided.services.agent_rules import is_live_decision
from asdecided.services.derived_cache import DerivedIndex, ScopeRow, scope_row_from_entry
from asdecided.services.index import IndexEntry, index_entry_from_corpus_entry
from asdecided.services.portfolio import PortfolioRow, portfolio_from_rows, portfolio_row
from asdecided.services.relationships import (
    Relationship,
    ValidationRow,
    inbound_counts_from_relationships,
    relationships_from_rows,
    resolution_index_from_rows,
)
from asdecided.services.resolve import field_tokens_for_entries

# Decisions are the only type with a live/scope projection; the same constant the
# read-model derivations scope to, named locally so the predicate reuse reads
# cleanly. Liveness itself is delegated to ``is_live_decision`` (one source of
# truth) rather than re-derived here.
_DECISION_TYPE = "decision"


@dataclass(frozen=True)
class DocFragment:
    """One document's compact derived projection — the unit workers emit (ADR-108).

    Every field is a pure function of a single parsed document, so a fragment
    built in the parent and a fragment shipped from a worker over the same file
    are identical:

    - ``index_entry`` — the repository index row (identity, type, title, path,
      aliases, searchable sections, tags). ``inbound_count`` is a cross-document
      signal, so it stays 0 here and the merge fills it from the resolved graph.
    - ``field_tokens`` — the six BM25 field-token vectors, tokenised once.
    - ``portfolio`` — the portfolio row: its :class:`ValidationRow` (identity,
      retired flag, declared edges, unsupported sections) for the relationship
      summary and gate, plus the per-document ``validate`` findings and
      recommended-slot projection.
    - ``is_live_decision`` — whether this is a live (Accepted, non-retired)
      decision, so the merge builds ``live_decision_paths`` without re-deriving it.
    - ``scope_row`` — the path-mode scope row for a live decision that declares
      ``## Applies To`` scope, else None.
    """

    index_entry: IndexEntry
    field_tokens: dict[str, list[str]]
    portfolio: PortfolioRow
    is_live_decision: bool
    scope_row: ScopeRow | None


def fragment_from_entry(entry: CorpusEntry) -> DocFragment:
    """Build the compact :class:`DocFragment` for one parsed corpus entry.

    Pure and deterministic: it runs each per-document derivation over the parsed
    product and keeps only the projection the merge reads. The parent uses it to
    reproduce the merge in-process (the byte-parity test); the worker calls the
    same builder over its own parse, so the fan-out ships exactly these fragments.
    """
    index_entry = index_entry_from_corpus_entry(entry)  # inbound filled at merge
    field_tokens = field_tokens_for_entries([index_entry])[index_entry.path]
    live = entry.artifact_type == _DECISION_TYPE and is_live_decision(entry.product)
    return DocFragment(
        index_entry=index_entry,
        field_tokens=field_tokens,
        portfolio=portfolio_row(entry),
        is_live_decision=live,
        scope_row=scope_row_from_entry(entry),
    )


def reproduce(
    fragments: list[DocFragment], directory: str, *, recursive: bool = True
) -> DerivedIndex:
    """Reproduce the derived read-model from per-document fragments (ADR-108).

    Byte-identical to :func:`build_derived_index_from_entries` over the same
    snapshot: ``fragments`` must be in sorted-path order (the merge assigns no
    order of its own), and every cross-document structure — the resolution index,
    the resolved graph, the inbound counts, and the portfolio summary — is built
    through the same compact-row seams the serial derive uses. The only work the
    merge does that a worker cannot is the cross-document resolution; everything
    else is read straight off the fragments.
    """
    validation_rows: list[ValidationRow] = [f.portfolio.validation for f in fragments]
    resolution_index = resolution_index_from_rows(validation_rows)
    rels: list[Relationship] = relationships_from_rows(
        validation_rows, resolution_index=resolution_index
    )
    inbound = inbound_counts_from_relationships(rels)
    index_entries = [
        replace(f.index_entry, inbound_count=inbound.get(f.index_entry.path, 0)) for f in fragments
    ]
    return DerivedIndex(
        index_entries=index_entries,
        relationships=rels,
        field_tokens_by_path={f.index_entry.path: f.field_tokens for f in fragments},
        live_decision_paths=[f.index_entry.path for f in fragments if f.is_live_decision],
        portfolio_summary=portfolio_from_rows(
            directory,
            [f.portfolio for f in fragments],
            recursive=recursive,
            resolution_index=resolution_index,
        ).to_dict(),
        scope_rows=[f.scope_row for f in fragments if f.scope_row is not None],
    )
