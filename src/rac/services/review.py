"""Repository review — `rac review` (v0.7.9).

``build_review`` aggregates RAC's existing repository intelligence into one
prioritized, actionable report (REQ-Repository-Review-Mode): what needs
attention in this repository, ordered by impact, with a deterministic
suggested action per finding.

The service composes ``build_portfolio_summary`` — it implements no analysis
of its own ("Review Mode shall not duplicate existing RAC command logic";
ADR-015: consumers render, never analyze). Duplicate-identifier detection
remains with ``rac relationships --validate``, which performs the repo-level
identifier index walk.

Priority order (REQ-Repository-Review-Mode, "Repository Health Summary"):

1. Invalid artifacts (validation errors)
2. Broken relationships (unresolved, ambiguous, or self references)
3. Missing required information (unrecognized artifacts — no schema matched)
4. Missing recommended information (recommended sections absent)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rac.core.corpus import CorpusCache

from .drift import CODE_SUSPECT_ARTIFACT, drift_problem, suspect_drift
from .portfolio import (
    ATTENTION_BROKEN_RELATIONSHIP,
    ATTENTION_INVALID,
    ATTENTION_MISSING_RECOMMENDED,
    PortfolioSummary,
    build_portfolio_summary,
)
from .recency import artifact_recency

# Stable priority levels and the unknown-artifact code (JSON contract, ADR-007).
PRIORITY_INVALID_ARTIFACT = 1
PRIORITY_BROKEN_RELATIONSHIP = 2
PRIORITY_UNKNOWN_ARTIFACT = 3
PRIORITY_MISSING_RECOMMENDED = 4
# Write-cadence nudge (v0.13.3): below every other finding, never fails review.
PRIORITY_STALE_CORPUS = 5
# Suspect-artifact drift (freshness-and-drift phase 1): a git-native advisory that
# sits beside the cadence nudge — advisory only, never fails review (REQ-002).
PRIORITY_SUSPECT_DRIFT = 6

REVIEW_UNKNOWN_ARTIFACT = "unknown-artifact"
REVIEW_STALE_CORPUS = "stale-corpus"
# The stable drift code is owned by `rac.services.drift`; re-exported here under
# the review namespace so both surfaces report the identical code (ADR-007).
REVIEW_SUSPECT_ARTIFACT = CODE_SUSPECT_ARTIFACT

# Default cadence window when `--stale-after` is given without a value: two
# weeks (v0.13.3).
DEFAULT_STALE_AFTER_DAYS = 14

# Attention code -> review priority for findings inherited from the portfolio.
_ATTENTION_PRIORITY = {
    ATTENTION_INVALID: PRIORITY_INVALID_ARTIFACT,
    ATTENTION_BROKEN_RELATIONSHIP: PRIORITY_BROKEN_RELATIONSHIP,
    ATTENTION_MISSING_RECOMMENDED: PRIORITY_MISSING_RECOMMENDED,
}

# "Why it matters" per finding code (v0.8.11) — Core owns the impact text so
# every consumer (JSON, CLI, Explorer) reads the same sentence. Moved here
# from the Explorer adapter; an unrecognized code gets the generic sentence,
# so the field is always present.
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
    REVIEW_SUSPECT_ARTIFACT: (
        "A referenced artifact changed after this one did, so the reference may be stale."
    ),
}


def impact_for(code: str) -> str:
    """The Core-owned impact sentence for a finding ``code``."""
    return _IMPACT.get(code, _GENERIC_IMPACT)


@dataclass
class ReviewIssue:
    """One prioritized finding with its deterministic next step."""

    priority: int  # 1 (highest impact) – 4
    severity: str  # "error" | "warning" | "info"
    path: str
    identifier: str  # artifact identifier or filename stem
    code: str
    message: str
    action: str  # a runnable command or concrete edit
    impact: str  # why it matters (v0.8.11; additive JSON field, ADR-007)

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
    """Repository review result (v0.7.9).

    ``to_dict`` is the stable JSON contract (ADR-007); fields are additive and
    schema_version-gated. The inventory/validation/relationship/health blocks
    mirror the ``rac portfolio`` contract so consumers can share parsing.
    """

    directory: str
    recursive: bool
    portfolio: PortfolioSummary
    issues: list[ReviewIssue]

    @property
    def ok(self) -> bool:
        """True when nothing demands attention before work continues.

        Priority 1–2 findings (invalid artifacts, broken relationships) fail
        the review; priority 3–4 findings are advisory.
        """
        return not any(i.priority <= PRIORITY_BROKEN_RELATIONSHIP for i in self.issues)

    @property
    def actions(self) -> list[str]:
        """Deduplicated suggested actions in priority order."""
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
            # Additive in v0.13.1 (ADR-007): a day-one empty-corpus marker.
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

    With ``stale_after_days`` set, an advisory write-cadence finding is added
    when the corpus has had no new or updated artifact within the window
    (v0.13.3). It is informational and never changes the review's exit status.
    ``now`` is injectable for deterministic tests.
    """
    portfolio = build_portfolio_summary(directory, recursive=recursive)
    report = review_from_portfolio(directory, portfolio, recursive=recursive)
    advisories: list[ReviewIssue] = list(_drift_findings(directory, recursive))
    if stale_after_days is not None:
        finding = _cadence_finding(directory, recursive, stale_after_days, now=now)
        if finding is not None:
            advisories.append(finding)
    if advisories:
        report.issues.extend(advisories)
        report.issues.sort(key=lambda i: (i.priority, i.path, i.code))
    return report


def _drift_findings(directory: str, recursive: bool) -> list[ReviewIssue]:
    """Suspect-artifact drift advisories, beside the cadence nudge (REQ-002).

    Surfaces the same git-native signal ``rac doctor`` reports, through review's
    advisory channel: one finding per referrer whose resolved target changed more
    recently. Advisory only (priority below every blocking finding), so it never
    changes the review verdict; empty outside git or with no drift (REQ-005).
    """
    entries = CorpusCache().collect(directory, recursive=recursive)
    issues: list[ReviewIssue] = []
    for record in suspect_drift(directory, entries):
        issues.append(
            ReviewIssue(
                priority=PRIORITY_SUSPECT_DRIFT,
                severity="warning",
                path=record.source_path,
                identifier=Path(record.source_path).stem,
                code=REVIEW_SUSPECT_ARTIFACT,
                message=drift_problem(record),
                action="Run: rac doctor " + directory,
                impact=impact_for(REVIEW_SUSPECT_ARTIFACT),
            )
        )
    return issues


def _cadence_finding(
    directory: str,
    recursive: bool,
    window_days: int,
    *,
    now: datetime | None = None,
) -> ReviewIssue | None:
    """The write-cadence nudge, or ``None`` when it should not fire.

    Fires only when recency is known (inside git, with committed artifacts)
    and the newest artifact is older than ``window_days``. An empty corpus or
    unknown recency is suppressed — the v0.13.1 empty-corpus hint covers the
    day-one case, and a nudge on missing data would be noise.
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


def review_from_portfolio(
    directory: str, portfolio: PortfolioSummary, recursive: bool = True
) -> ReviewReport:
    """Build the review from an already-computed portfolio (v0.8.3).

    Same result as :func:`build_review`; the seam lets a consumer holding a
    loaded repository model (Explorer) reuse Core's review logic without a
    second walk (ADR-015: the recommendation logic stays here, not in Explorer).
    """
    issues: list[ReviewIssue] = []

    # Findings the portfolio already computed, re-ranked by review priority
    # and paired with a deterministic next step.
    for item in portfolio.attention:
        priority = _ATTENTION_PRIORITY.get(item.code)
        if priority is None:  # future attention codes: surface, lowest priority
            priority = PRIORITY_MISSING_RECOMMENDED
        if item.code == ATTENTION_INVALID:
            action = f"Run: rac validate {item.path}"
        elif item.code == ATTENTION_BROKEN_RELATIONSHIP:
            action = f"Run: rac relationships {directory} --validate"
        else:
            action = f"Run: rac improve {item.path} --template"
        issues.append(
            ReviewIssue(
                priority=priority,
                severity=item.severity,
                path=item.path,
                identifier=item.identifier,
                code=item.code,
                message=item.message,
                action=action,
                impact=impact_for(item.code),
            )
        )

    # Unrecognized artifacts: no schema matched, so required information is
    # missing by definition (priority 3). Advisory — Unknown is a valid outcome.
    for path in portfolio.unknown_paths:
        issues.append(
            ReviewIssue(
                priority=PRIORITY_UNKNOWN_ARTIFACT,
                severity="info",
                path=path,
                identifier=Path(path).stem,
                code=REVIEW_UNKNOWN_ARTIFACT,
                message="No artifact schema matched this document.",
                action=f"Run: rac inspect {path} (see rac schema --list)",
                impact=impact_for(REVIEW_UNKNOWN_ARTIFACT),
            )
        )

    # Deterministic order: impact first, then path, then code.
    issues.sort(key=lambda i: (i.priority, i.path, i.code))

    return ReviewReport(
        directory=directory,
        recursive=recursive,
        portfolio=portfolio,
        issues=issues,
    )
