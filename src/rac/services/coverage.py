"""Traceability coverage report — typed completeness gaps (v0.24, WS-F).

Coverage answers a different question from ``rac doctor``'s integrity checks: not
"is this artifact well-formed or reachable" but "does it carry the *specific*
traceability edge its type is expected to have". Three deterministic, advisory
gap classes are derived from the corpus relationship graph
(rac-traceability-coverage-report):

  - **unscheduled** — a requirement that no roadmap references (nothing schedules
    the capability),
  - **unapplied** — a decision that no requirement or roadmap references (recorded
    but not yet applied),
  - **unscoped** — a roadmap that references no requirement (a plan that scopes no
    capability).

Gaps are completeness signals for human judgement, never validation errors: a
roadmap may legitimately precede its requirements, a decision may be recorded
before anything applies it. The report stays out of the ``rac gate`` enforcement
path (ADR-049) and never fails a build. Deterministic and offline (ADR-002).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from rac.core.corpus import walk_corpus
from rac.services.index import index_from_corpus
from rac.services.relationships import relationships_from_corpus

GAP_UNSCHEDULED = "unscheduled"
GAP_UNAPPLIED = "unapplied"
GAP_UNSCOPED = "unscoped"

# Report order for the three classes (REQ-003): unscheduled, unapplied, unscoped.
_GAP_ORDER = (GAP_UNSCHEDULED, GAP_UNAPPLIED, GAP_UNSCOPED)

# The missing-coverage sentence per class. Each rule is one artifact type and one
# expected traceability direction, so a new type never silently inherits a rule
# (rac-traceability-coverage REQ-006).
_MISSING = {
    GAP_UNSCHEDULED: "no roadmap schedules this requirement",
    GAP_UNAPPLIED: "no requirement or roadmap applies this decision",
    GAP_UNSCOPED: "this roadmap references no requirement",
}


@dataclass(frozen=True)
class CoverageGap:
    """One typed traceability gap."""

    path: str
    id: str
    type: str
    gap: str  # one of GAP_*
    missing: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "id": self.id,
            "type": self.type,
            "gap": self.gap,
            "missing": self.missing,
        }


@dataclass(frozen=True)
class CoverageReport:
    """The coverage report for a directory (advisory; never a build failure)."""

    directory: str
    gaps: list[CoverageGap]

    @property
    def counts(self) -> dict[str, int]:
        out = {gap_class: 0 for gap_class in _GAP_ORDER}
        for gap in self.gaps:
            out[gap.gap] += 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "directory": self.directory,
            "gaps": [g.to_dict() for g in self.gaps],
            "summary": {**self.counts, "total": len(self.gaps)},
        }


def analyze_coverage(directory: str) -> CoverageReport:
    """Derive the typed coverage gaps for ``directory`` from its relationship graph."""
    entries = list(walk_corpus(directory, recursive=True))
    artifacts = index_from_corpus(directory, entries, recursive=True).artifacts
    type_by_path = {a.path: a.type for a in artifacts}

    # For each artifact, the set of resolved neighbour types on each side. A
    # requirement/decision cares about who points *at* it (incoming source types);
    # a roadmap cares about what *it* points at (outgoing target types).
    incoming: dict[str, set[str]] = {a.path: set() for a in artifacts}
    outgoing: dict[str, set[str]] = {a.path: set() for a in artifacts}
    for source_path, source_type, target_path, target_type in _resolved_edges(
        relationships_from_corpus(entries), type_by_path
    ):
        if target_path in incoming and source_type is not None:
            incoming[target_path].add(source_type)
        if source_path in outgoing and target_type is not None:
            outgoing[source_path].add(target_type)

    gaps: list[CoverageGap] = []
    for artifact in artifacts:
        gap_class = _classify(artifact.type, incoming[artifact.path], outgoing[artifact.path])
        if gap_class is not None:
            gaps.append(
                CoverageGap(
                    path=artifact.path,
                    id=artifact.id,
                    type=artifact.type,
                    gap=gap_class,
                    missing=_MISSING[gap_class],
                )
            )

    # Deterministic order: gap class, then ascending path (REQ-003).
    rank = {gap_class: i for i, gap_class in enumerate(_GAP_ORDER)}
    gaps.sort(key=lambda g: (rank[g.gap], g.path))
    return CoverageReport(directory=directory, gaps=gaps)


def _resolved_edges(
    relationships: Any, type_by_path: dict[str, str]
) -> Iterator[tuple[str, str | None, str, str | None]]:
    """Yield ``(source_path, source_type, target_path, target_type)`` for each
    resolved, non-self relationship edge."""
    for rel in relationships:
        if rel.resolved_path is None or rel.resolved_path == rel.source_path:
            continue
        yield (
            rel.source_path,
            type_by_path.get(rel.source_path),
            rel.resolved_path,
            type_by_path.get(rel.resolved_path),
        )


def _classify(artifact_type: str, incoming: set[str], outgoing: set[str]) -> str | None:
    """The gap class an artifact falls into, or ``None`` when its expected edge is
    present. The branches are mutually exclusive — one type, one direction each."""
    if artifact_type == "requirement" and "roadmap" not in incoming:
        return GAP_UNSCHEDULED
    if artifact_type == "decision" and not ({"requirement", "roadmap"} & incoming):
        return GAP_UNAPPLIED
    if artifact_type == "roadmap" and "requirement" not in outgoing:
        return GAP_UNSCOPED
    return None


def render_coverage_json(report: CoverageReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def render_coverage_human(report: CoverageReport) -> str:
    lines = [f"Traceability coverage — {report.directory}", ""]
    if not report.gaps:
        lines.append("✓ No coverage gaps — every artifact has its expected traceability edge.")
        return "\n".join(lines)

    headings = {
        GAP_UNSCHEDULED: "Unscheduled requirements (no roadmap schedules them)",
        GAP_UNAPPLIED: "Unapplied decisions (no requirement or roadmap applies them)",
        GAP_UNSCOPED: "Unscoped roadmaps (reference no requirement)",
    }
    for gap_class in _GAP_ORDER:
        members = [g for g in report.gaps if g.gap == gap_class]
        if not members:
            continue
        lines.append(f"{headings[gap_class]}: {len(members)}")
        lines.extend(f"  {gap.id}  {gap.path}" for gap in members)
        lines.append("")

    counts = report.counts
    total = len(report.gaps)
    lines.append(
        f"{total} coverage gap{'s' if total != 1 else ''} "
        f"({counts[GAP_UNSCHEDULED]} unscheduled, {counts[GAP_UNAPPLIED]} unapplied, "
        f"{counts[GAP_UNSCOPED]} unscoped) — advisory, not a build failure."
    )
    return "\n".join(lines)
