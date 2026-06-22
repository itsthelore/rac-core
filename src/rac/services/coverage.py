"""Traceability coverage report — typed completeness gaps (v0.24, WS-F).

Coverage answers a different question from `rac doctor`'s integrity checks: not
"is this artifact reachable or well-formed" but "does it have the *specific*
traceability edge its type expects". Three deterministic, advisory gap classes
are derived from the corpus relationship graph (rac-traceability-coverage-report):

  - **unscheduled** — a requirement that no roadmap references (nothing schedules
    the capability),
  - **unapplied** — a decision that no requirement or roadmap references (the
    decision is recorded but nothing applies it),
  - **unscoped** — a roadmap that references no requirement (the plan scopes no
    capability).

Gaps are completeness signals for human judgement, never validation errors: a
roadmap may legitimately precede its requirements, a decision may be recorded
before anything applies it. The report stays out of the `rac gate` enforcement
path (ADR-049) and never fails a build. Deterministic and offline (ADR-002).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from rac.core.corpus import walk_corpus
from rac.services.index import index_from_corpus
from rac.services.relationships import relationships_from_corpus

# Gap class -> (artifact type it applies to, the missing-coverage description).
# Derived from the relationship semantics rather than a per-artifact table, so a
# new type does not silently inherit a coverage rule (rac-traceability-coverage
# REQ-006): each rule is one type and one expected traceability direction.
GAP_UNSCHEDULED = "unscheduled"
GAP_UNAPPLIED = "unapplied"
GAP_UNSCOPED = "unscoped"

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
    gap: str  # GAP_* class
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
        out = {GAP_UNSCHEDULED: 0, GAP_UNAPPLIED: 0, GAP_UNSCOPED: 0}
        for gap in self.gaps:
            out[gap.gap] += 1
        return out

    def to_dict(self) -> dict[str, Any]:
        counts = self.counts
        return {
            "schema_version": "1",
            "directory": self.directory,
            "gaps": [g.to_dict() for g in self.gaps],
            "summary": {**counts, "total": len(self.gaps)},
        }


def analyze_coverage(directory: str) -> CoverageReport:
    """Derive the typed coverage gaps for ``directory`` from its relationship graph."""
    entries = list(walk_corpus(directory, recursive=True))
    index = index_from_corpus(directory, entries, recursive=True).artifacts
    type_by_path = {a.path: a.type for a in index}
    identity = {a.path: (a.id, a.type) for a in index}
    relationships = relationships_from_corpus(entries)

    # Resolved incoming source types and resolved outgoing target types per path.
    incoming_types: dict[str, set[str]] = {a.path: set() for a in index}
    outgoing_types: dict[str, set[str]] = {a.path: set() for a in index}
    for rel in relationships:
        if rel.resolved_path is None or rel.resolved_path == rel.source_path:
            continue
        source_type = type_by_path.get(rel.source_path)
        target_type = type_by_path.get(rel.resolved_path)
        if rel.resolved_path in incoming_types and source_type is not None:
            incoming_types[rel.resolved_path].add(source_type)
        if rel.source_path in outgoing_types and target_type is not None:
            outgoing_types[rel.source_path].add(target_type)

    gaps: list[CoverageGap] = []
    for artifact in index:
        artifact_id, artifact_type = identity[artifact.path]
        gap: str | None = None
        if artifact_type == "requirement" and "roadmap" not in incoming_types[artifact.path]:
            gap = GAP_UNSCHEDULED
        elif artifact_type == "decision" and not (
            {"requirement", "roadmap"} & incoming_types[artifact.path]
        ):
            gap = GAP_UNAPPLIED
        elif artifact_type == "roadmap" and "requirement" not in outgoing_types[artifact.path]:
            gap = GAP_UNSCOPED
        if gap is not None:
            gaps.append(
                CoverageGap(
                    path=artifact.path,
                    id=artifact_id,
                    type=artifact_type,
                    gap=gap,
                    missing=_MISSING[gap],
                )
            )

    # Deterministic order: gap class, then ascending path (REQ-003).
    order = {GAP_UNSCHEDULED: 0, GAP_UNAPPLIED: 1, GAP_UNSCOPED: 2}
    gaps.sort(key=lambda g: (order[g.gap], g.path))
    return CoverageReport(directory=directory, gaps=gaps)


def render_coverage_json(report: CoverageReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def render_coverage_human(report: CoverageReport) -> str:
    counts = report.counts
    lines = [f"Traceability coverage — {report.directory}", ""]
    if not report.gaps:
        lines.append("✓ No coverage gaps — every artifact has its expected traceability edge.")
        return "\n".join(lines)
    headings = {
        GAP_UNSCHEDULED: "Unscheduled requirements (no roadmap schedules them)",
        GAP_UNAPPLIED: "Unapplied decisions (no requirement or roadmap applies them)",
        GAP_UNSCOPED: "Unscoped roadmaps (reference no requirement)",
    }
    for gap_class, heading in headings.items():
        members = [g for g in report.gaps if g.gap == gap_class]
        if not members:
            continue
        lines.append(f"{heading}: {len(members)}")
        for gap in members:
            lines.append(f"  {gap.id}  {gap.path}")
        lines.append("")
    total = len(report.gaps)
    lines.append(
        f"{total} coverage gap{'s' if total != 1 else ''} "
        f"({counts[GAP_UNSCHEDULED]} unscheduled, {counts[GAP_UNAPPLIED]} unapplied, "
        f"{counts[GAP_UNSCOPED]} unscoped) — advisory, not a build failure."
    )
    return "\n".join(lines)
