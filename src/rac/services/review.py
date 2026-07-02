"""Prioritized repository review — the engine behind ``rac review``.

:func:`build_review` folds RAC's existing repository intelligence into one
impact-ordered, actionable report (REQ-Repository-Review-Mode): what needs
attention here, worst first, each finding paired with a deterministic next
step and a "why it matters" sentence.

The service performs no analysis of its own — it composes
``build_portfolio_summary`` and re-ranks its findings (ADR-015: consumers
render existing signals, they do not recompute them). Duplicate-identifier and
relationship resolution stay with ``rac relationships --validate``.

Priority order (highest impact first):

1. Invalid artifacts (structural validation errors)
2. Broken relationships (unresolved, ambiguous, or self references)
3. Unrecognized artifacts (no schema matched — required structure unknowable)
4. Missing recommended information (recommended sections empty)
5. Stale corpus (write-cadence nudge; advisory, never fails a review)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .portfolio import (
    ATTENTION_BROKEN_RELATIONSHIP,
    ATTENTION_INVALID,
    ATTENTION_MISSING_RECOMMENDED,
    AttentionItem,
    PortfolioSummary,
    build_portfolio_summary,
)
from .recency import artifact_recency

# Stable priority levels and finding codes (JSON contract, ADR-007).
PRIORITY_INVALID_ARTIFACT = 1
PRIORITY_BROKEN_RELATIONSHIP = 2
PRIORITY_UNKNOWN_ARTIFACT = 3
PRIORITY_MISSING_RECOMMENDED = 4
# Write-cadence nudge: sits below every other finding and never fails a review.
PRIORITY_STALE_CORPUS = 5

REVIEW_UNKNOWN_ARTIFACT = "unknown-artifact"
REVIEW_STALE_CORPUS = "stale-corpus"

# Default cadence window when ``--stale-after`` is given without a value.
DEFAULT_STALE_AFTER_DAYS = 14

# Portfolio attention code -> review priority. A future attention code with no
# mapping surfaces at the lowest actionable priority rather than vanishing.
_ATTENTION_PRIORITY = {
    ATTENTION_INVALID: PRIORITY_INVALID_ARTIFACT,
    ATTENTION_BROKEN_RELATIONSHIP: PRIORITY_BROKEN_RELATIONSHIP,
    ATTENTION_MISSING_RECOMMENDED: PRIORITY_MISSING_RECOMMENDED,
}

# "Why it matters" per finding code — Core owns the impact text so every
# consumer (JSON, CLI, Explorer) reads the same sentence. An unrecognized code
# falls back to the generic sentence, so the field is always present.
_GENERIC_IMPACT = "This finding affects repository quality."
_IMPACT = {
    ATTENTION_INVALID: "The artifact fails its schema, so tooling and validation cannot trust it.",
    ATTENTION_BROKEN_RELATIONSHIP: (
        "A declared reference does not resolve, leaving traceability incomplete."
    ),
    ATTENTION_MISSING_RECOMMENDED: (
        "Recommended sections are empty, weakening the artifact's completeness."
    ),
    REVIEW_UNKNOWN_ARTIFACT: "No schema matched, so required structure cannot be checked.",
    REVIEW_STALE_CORPUS: (
        "The write habit has stalled; product knowledge stops reflecting the work."
    ),
}


def impact_for(code: str) -> str:
    """The Core-owned impact sentence for a finding ``code``."""
    return _IMPACT.get(code, _GENERIC_IMPACT)


def _impact_order(issue: ReviewIssue) -> tuple[int, str, str]:
    """Deterministic issue ordering: impact first, then path, then code."""
    return (issue.priority, issue.path, issue.code)


@dataclass
class ReviewIssue:
    """One prioritized finding with its deterministic next step."""

    priority: int  # 1 (highest impact) .. 5
    severity: str  # "error" | "warning" | "info"
    path: str
    identifier: str  # artifact identifier or filename stem
    code: str
    message: str
    action: str  # a runnable command or concrete edit
    impact: str  # why it matters (additive JSON field, ADR-007)

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "severity": self.severity,
            "path": self.path,
            "identifier": self.identifier,
            "code": self.code,
            "message": self.message,
            "action": self.action,
            "impact": self.impact,
        }


@dataclass
class ReviewReport:
    """Repository review result.

    ``to_dict`` is the stable, schema_version-gated JSON contract (ADR-007). The
    inventory / validation / relationship / health blocks mirror the
    ``rac portfolio`` contract so consumers can share parsing.
    """

    directory: str
    recursive: bool
    portfolio: PortfolioSummary
    issues: list[ReviewIssue]

    @property
    def ok(self) -> bool:
        """True when nothing blocks continued work.

        Priority 1-2 findings (invalid artifacts, broken relationships) fail the
        review; priority 3+ findings are advisory.
        """
        return not any(i.priority <= PRIORITY_BROKEN_RELATIONSHIP for i in self.issues)

    @property
    def actions(self) -> list[str]:
        """Deduplicated suggested actions in issue (priority) order."""
        seen: set[str] = set()
        ordered: list[str] = []
        for issue in self.issues:
            if issue.action not in seen:
                seen.add(issue.action)
                ordered.append(issue.action)
        return ordered

    def to_dict(self) -> dict:
        p = self.portfolio
        return {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            "ok": self.ok,
            # Additive (ADR-007): a day-one empty-corpus marker.
            "empty": p.total_artifacts == 0,
            "artifacts": {
                "total": p.total_artifacts,
                "by_type": p.by_type,
                "unknown_paths": p.unknown_paths,
            },
            "validation": {
                "valid": p.valid_artifacts,
                "invalid": p.invalid_artifacts,
            },
            "relationships": {
                "total": p.relationships.total,
                "valid": p.relationships.valid,
                "broken": p.relationships.broken,
                "orphaned": p.relationships.orphaned,
                "coverage": p.relationships.coverage,
            },
            "health": {
                "score": p.health_score,
            },
            "issues": [i.to_dict() for i in self.issues],
            "actions": self.actions,
        }


def build_review(
    directory: str,
    recursive: bool = True,
    *,
    stale_after_days: int | None = None,
    now: datetime | None = None,
) -> ReviewReport:
    """Review ``directory`` and return the prioritized repository report.

    With ``stale_after_days`` set, an advisory write-cadence finding is appended
    when the corpus has had no new or updated artifact within the window. It is
    informational and never changes the review's exit status. ``now`` is
    injectable for deterministic tests.
    """
    portfolio = build_portfolio_summary(directory, recursive=recursive)
    report = review_from_portfolio(directory, portfolio, recursive=recursive)
    if stale_after_days is not None:
        finding = _cadence_finding(directory, recursive, stale_after_days, now=now)
        if finding is not None:
            report.issues.append(finding)
            report.issues.sort(key=_impact_order)
    return report


def review_from_portfolio(
    directory: str, portfolio: PortfolioSummary, recursive: bool = True
) -> ReviewReport:
    """Build the review from an already-computed portfolio.

    Same result as :func:`build_review` without the cadence nudge; the seam lets
    a consumer holding a loaded repository model (Explorer, gate) reuse this
    recommendation logic without a second walk (ADR-015).
    """
    issues = [_attention_issue(item, directory) for item in portfolio.attention]

    # Unrecognized artifacts: no schema matched, so required information is
    # missing by definition (priority 3, advisory — Unknown is a valid outcome).
    issues.extend(_unknown_issue(path) for path in portfolio.unknown_paths)

    issues.sort(key=_impact_order)
    return ReviewReport(
        directory=directory,
        recursive=recursive,
        portfolio=portfolio,
        issues=issues,
    )


def _attention_issue(item: AttentionItem, directory: str) -> ReviewIssue:
    """Re-rank one portfolio attention item into a prioritized review finding."""
    priority = _ATTENTION_PRIORITY.get(item.code, PRIORITY_MISSING_RECOMMENDED)
    return ReviewIssue(
        priority=priority,
        severity=item.severity,
        path=item.path,
        identifier=item.identifier,
        code=item.code,
        message=item.message,
        action=_attention_action(item, directory),
        impact=impact_for(item.code),
    )


def _attention_action(item: AttentionItem, directory: str) -> str:
    """The runnable next step for an attention finding.

    Invalid artifacts and broken relationships have targeted commands; every
    other finding falls back to the template-improvement suggestion.
    """
    if item.code == ATTENTION_INVALID:
        return f"Run: rac validate {item.path}"
    if item.code == ATTENTION_BROKEN_RELATIONSHIP:
        return f"Run: rac relationships {directory} --validate"
    return f"Run: rac improve {item.path} --template"


def _unknown_issue(path: str) -> ReviewIssue:
    """The advisory finding for a document no artifact schema recognized."""
    return ReviewIssue(
        priority=PRIORITY_UNKNOWN_ARTIFACT,
        severity="info",
        path=path,
        identifier=Path(path).stem,
        code=REVIEW_UNKNOWN_ARTIFACT,
        message="No artifact schema matched this document.",
        action=f"Run: rac inspect {path} (see rac schema --list)",
        impact=impact_for(REVIEW_UNKNOWN_ARTIFACT),
    )


def _cadence_finding(
    directory: str,
    recursive: bool,
    window_days: int,
    *,
    now: datetime | None = None,
) -> ReviewIssue | None:
    """The write-cadence nudge, or ``None`` when it should not fire.

    Fires only when git-derived recency is known and the newest artifact is
    strictly older than ``window_days`` (exactly at the window is not stale). An
    empty corpus or unknown recency is suppressed — the empty-corpus hint covers
    the day-one case, and a nudge on missing data would be noise.
    """
    recency = artifact_recency(directory, recursive=recursive)
    most_recent = recency.most_recent
    if most_recent is None:
        return None
    moment = now or datetime.now(UTC)
    age = moment - most_recent
    if age <= timedelta(days=window_days):
        return None
    return ReviewIssue(
        priority=PRIORITY_STALE_CORPUS,
        severity="info",
        path=directory,
        identifier="corpus",
        code=REVIEW_STALE_CORPUS,
        message=(
            f"No product knowledge recorded in the last {window_days} days "
            f"(newest artifact is {age.days} days old)."
        ),
        action="Run: rac new decision rac/decisions/<name>.md",
        impact=impact_for(REVIEW_STALE_CORPUS),
    )
