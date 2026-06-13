"""Watchkeeper — RAC's product knowledge review surface (v0.12.0).

``build_watchkeeper_report`` resolves the base and head of a comparison —
each either an existing directory or a git revision materialized through
:mod:`rac.services.revisions` — loads both states, and assembles the report
the ``rac watchkeeper`` command renders. Watchkeeper consumes Core
intelligence; it computes nothing the comparison services do not already
provide (ADR-015).

``WatchkeeperReport.to_dict`` is the stable JSON contract (ADR-007): fields
are additive across the v0.12.x series and schema_version-gated.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rac.core.models import Diff
from rac.services.compare import (
    ArtifactChange,
    RelationshipIssueRef,
    RepositoryComparison,
    compare_states,
    load_state,
)
from rac.services.intent import (
    ACCEPTANCE_CRITERIA_REMOVED,
    CONSTRAINT_REMOVED,
    CONSTRAINT_WEAKENED,
    SEVERITY_WARNING,
    SPECIFICITY_REGRESSION,
    SUCCESS_MEASURES_REMOVED,
    IntentFinding,
    analyze_intent,
)
from rac.services.relationships import RelationshipSummary
from rac.services.revisions import materialized_revision, repository_root

# Recommendation reason codes (part of the JSON contract, ADR-007). The
# delta-driven codes are watchkeeper's own; the finding-driven codes reuse
# the intent vocabulary verbatim.
REASON_VALIDATION_REGRESSION = "validation_regression"
REASON_BROKEN_RELATIONSHIP = "broken_relationship"

# Findings that recommend review on their own. Ambiguity, unlinked scope,
# and relationship impact inform but never recommend (v0.12.2 contract).
RECOMMENDING_FINDINGS = frozenset(
    {
        SPECIFICITY_REGRESSION,
        CONSTRAINT_WEAKENED,
        CONSTRAINT_REMOVED,
        ACCEPTANCE_CRITERIA_REMOVED,
        SUCCESS_MEASURES_REMOVED,
    }
)

# Core-owned reason sentences, one per code (mirrors review.py's impact
# phrasing): consumers render these, they do not compose their own.
_REASONS = {
    REASON_VALIDATION_REGRESSION: "One or more artifacts became invalid.",
    REASON_BROKEN_RELATIONSHIP: "One or more relationship references broke.",
    SPECIFICITY_REGRESSION: "A measurable requirement became vague.",
    CONSTRAINT_WEAKENED: "A mandatory requirement was weakened.",
    CONSTRAINT_REMOVED: "A requirement with mandatory wording was removed.",
    ACCEPTANCE_CRITERIA_REMOVED: "An acceptance criteria section was removed.",
    SUCCESS_MEASURES_REMOVED: "A success measures section was removed.",
}


@dataclass(frozen=True)
class ReviewRecommendation:
    """One deterministic reason human review is recommended."""

    code: str
    reason: str


@dataclass
class WatchkeeperReport:
    """One product knowledge review: base state, head state, what changed."""

    directory: str
    base: str  # base label: revision name or directory path
    head: str  # head label: revision name or directory path (working tree)
    comparison: RepositoryComparison
    findings: list[IntentFinding] = field(default_factory=list)  # v0.12.1, additive
    recommendations: list[ReviewRecommendation] = field(default_factory=list)  # v0.12.2

    @property
    def has_changes(self) -> bool:
        return bool(self.comparison.changes)

    @property
    def review_recommended(self) -> bool:
        return bool(self.recommendations)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == SEVERITY_WARNING for f in self.findings)

    def to_dict(self) -> dict:
        validation = self.comparison.validation
        relationships = self.comparison.relationships
        stats = self.comparison.stats
        return {
            "schema_version": "1",
            "directory": self.directory,
            "base": self.base,
            "head": self.head,
            "changes": [_change_dict(change) for change in self.comparison.changes],
            "validation": {
                "base": {"valid": validation.base_valid, "invalid": validation.base_invalid},
                "head": {"valid": validation.head_valid, "invalid": validation.head_invalid},
                "newly_invalid": list(validation.newly_invalid),
                "newly_valid": list(validation.newly_valid),
            },
            "relationships": {
                "base": _summary_dict(relationships.base),
                "head": _summary_dict(relationships.head),
                "new_issues": [_issue_dict(issue) for issue in relationships.new_issues],
                "resolved_issues": [_issue_dict(issue) for issue in relationships.resolved_issues],
            },
            "stats": {
                "total": {"base": stats.total[0], "head": stats.total[1]},
                "by_type": {
                    type_name: {"base": counts[0], "head": counts[1]}
                    for type_name, counts in stats.by_type.items()
                },
            },
            # Additive in v0.12.1 (ADR-007): deterministic intent findings.
            "findings": [_finding_dict(finding) for finding in self.findings],
            # Additive in v0.12.2 (ADR-007): the review verdict and reasons.
            "review": {
                "recommended": self.review_recommended,
                "reasons": [
                    {"code": rec.code, "reason": rec.reason} for rec in self.recommendations
                ],
            },
        }


def _change_dict(change: ArtifactChange) -> dict:
    payload: dict = {
        "change": change.change,
        "type": change.type,
        "id": change.id,
        "title": change.title,
        "path": change.path,
        "base_status": change.base_status,
        "head_status": change.head_status,
    }
    if change.diff is not None:
        payload["diff"] = _diff_dict(change.diff)
    return payload


def _diff_dict(diff: Diff) -> dict:
    # Mirrors the `rac diff` JSON fields so the requirement-level shape is
    # the same wherever a diff appears.
    return {
        "added_requirements": [asdict(r) for r in diff.added_requirements],
        "removed_requirements": [asdict(r) for r in diff.removed_requirements],
        "modified_requirements": [asdict(c) for c in diff.modified_requirements],
        "added_metrics": diff.added_metrics,
        "removed_metrics": diff.removed_metrics,
        "added_risks": diff.added_risks,
        "removed_risks": diff.removed_risks,
    }


def _summary_dict(summary: RelationshipSummary) -> dict:
    return {
        "total": summary.total,
        "valid": summary.valid,
        "broken": summary.broken,
        "orphaned": summary.orphaned,
        "coverage": summary.coverage,
    }


def _issue_dict(issue: RelationshipIssueRef) -> dict:
    return {
        "code": issue.code,
        "relationship": issue.relationship,
        "target": issue.target,
        "path": issue.path,
        "identifier": issue.identifier,
    }


def _finding_dict(finding: IntentFinding) -> dict:
    return {
        "code": finding.code,
        "severity": finding.severity,
        "path": finding.path,
        "identifier": finding.identifier,
        "detail": finding.detail,
        "evidence": list(finding.evidence),
    }


def derive_recommendations(
    comparison: RepositoryComparison, findings: list[IntentFinding]
) -> list[ReviewRecommendation]:
    """The deterministic finding/delta → reason mapping (v0.12.2).

    Reasons are deduplicated by code and ordered: validation regressions,
    broken relationships, then finding-driven reasons in finding order.
    """
    codes: list[str] = []
    if comparison.validation.newly_invalid:
        codes.append(REASON_VALIDATION_REGRESSION)
    if comparison.relationships.new_issues:
        codes.append(REASON_BROKEN_RELATIONSHIP)
    for finding in findings:
        if finding.code in RECOMMENDING_FINDINGS and finding.code not in codes:
            codes.append(finding.code)
    return [ReviewRecommendation(code=code, reason=_REASONS[code]) for code in codes]


def _resolve_side(stack: ExitStack, directory: str, ref: str) -> str:
    """A directory for one comparison side: ``ref`` itself, or a materialization."""
    if Path(ref).is_dir():
        return ref
    root = repository_root(directory)
    subpath = os.path.relpath(os.path.abspath(directory), root)
    return str(stack.enter_context(materialized_revision(root, ref, subpath)))


def build_watchkeeper_report(
    directory: str, *, base: str, head: str | None = None
) -> WatchkeeperReport:
    """Compare ``directory``'s corpus between ``base`` and ``head``.

    ``base`` and ``head`` each name an existing directory (used as-is) or a
    git revision of the repository containing ``directory``; ``head`` of
    ``None`` means the working tree at ``directory``.
    """
    head_label = head if head is not None else directory
    with ExitStack() as stack:
        base_dir = _resolve_side(stack, directory, base)
        head_dir = _resolve_side(stack, directory, head) if head is not None else directory
        base_state = load_state(base_dir, label=base)
        head_state = load_state(head_dir, label=head_label)
        comparison = compare_states(base_state, head_state)
        findings = analyze_intent(comparison)
    return WatchkeeperReport(
        directory=directory,
        base=base,
        head=head_label,
        comparison=comparison,
        findings=findings,
        recommendations=derive_recommendations(comparison, findings),
    )
