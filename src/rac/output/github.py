"""GitHub-oriented rendering for `rac watchkeeper --format github` (v0.12.2).

Two surfaces, one invocation, no GitHub API:

- :func:`render_watchkeeper_github` returns a GitHub-flavored Markdown
  report intended for ``$GITHUB_STEP_SUMMARY``.
- :func:`watchkeeper_annotations` returns workflow-command lines
  (``::warning`` / ``::error`` / ``::notice``) intended for the step log,
  where the runner turns them into inline annotations.

Annotation file paths are repository-relative (the corpus directory joined
to each finding's corpus-relative path) so GitHub can map them onto pull
request files.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from rac.services.compare import CHANGE_ADDED, CHANGE_MODIFIED, CHANGE_REMOVED
from rac.services.intent import SEVERITY_WARNING
from rac.services.watchkeeper import (
    REASON_BROKEN_RELATIONSHIP,
    REASON_VALIDATION_REGRESSION,
    RECOMMENDING_FINDINGS,
    WatchkeeperReport,
)

_CHANGE_LABELS = {CHANGE_ADDED: "Added", CHANGE_MODIFIED: "Modified", CHANGE_REMOVED: "Removed"}


def _repo_path(report: WatchkeeperReport, corpus_relative: str) -> str:
    return str(PurePosixPath(report.directory) / corpus_relative)


def render_watchkeeper_github(report: WatchkeeperReport) -> str:
    """The Markdown step-summary report."""
    comparison = report.comparison
    validation = comparison.validation
    relationships = comparison.relationships
    stats = comparison.stats

    lines = [
        "# RAC Watchkeeper",
        "",
        f"Comparing `{report.base}` → `{report.head}` in `{report.directory}`.",
        "",
        "## Changed artifacts",
        "",
    ]
    if comparison.changes:
        lines += ["| Change | Artifact | Type |", "| --- | --- | --- |"]
        lines += [
            f"| {_CHANGE_LABELS[change.change]} | `{change.path}` | {change.type} |"
            for change in comparison.changes
        ]
    else:
        lines.append("No product artifact changes detected.")

    lines += [
        "",
        "## Repository deltas",
        "",
        "| Measure | Base | Head |",
        "| --- | --- | --- |",
        f"| Valid artifacts | {validation.base_valid} | {validation.head_valid} |",
        f"| Invalid artifacts | {validation.base_invalid} | {validation.head_invalid} |",
        f"| Relationships | {relationships.base.total} | {relationships.head.total} |",
        f"| Broken relationships | {relationships.base.broken} | {relationships.head.broken} |",
        f"| Artifacts | {stats.total[0]} | {stats.total[1]} |",
    ]
    if validation.newly_invalid:
        lines += ["", "Newly invalid:", ""]
        lines += [f"- `{path}`" for path in validation.newly_invalid]
    if relationships.new_issues:
        lines += ["", "New relationship issues:", ""]
        lines += [
            f"- `{issue.path}` — `{issue.target}` ({issue.code})"
            for issue in relationships.new_issues
        ]

    if report.findings:
        lines += ["", f"## Findings ({len(report.findings)})", ""]
        for finding in report.findings:
            marker = "⚠️" if finding.severity == SEVERITY_WARNING else "ℹ️"
            lines.append(f"- {marker} **{finding.code}** — `{finding.path}`: {finding.detail}")

    lines += ["", "## Verdict", ""]
    if report.review_recommended:
        lines += ["**Review recommended.**", "", "Reasons:", ""]
        lines += [f"- {rec.reason} (`{rec.code}`)" for rec in report.recommendations]
    else:
        lines.append("✅ Nothing requiring attention.")

    return "\n".join(lines)


def watchkeeper_annotations(report: WatchkeeperReport) -> list[str]:
    """Workflow-command lines for the step log, one annotation per line.

    Recommendation triggers annotate as errors; other warnings as warnings;
    informational findings as notices. Deterministic order: delta-driven
    errors first, then findings in report order.
    """
    lines: list[str] = []
    for path in report.comparison.validation.newly_invalid:
        lines.append(
            f"::error file={_repo_path(report, path)}::"
            f"{REASON_VALIDATION_REGRESSION}: Artifact became invalid."
        )
    for issue in report.comparison.relationships.new_issues:
        # Duplicate-identifier findings can span files; annotate the first.
        file_path = issue.path.split(", ")[0]
        lines.append(
            f"::error file={_repo_path(report, file_path)}::"
            f"{REASON_BROKEN_RELATIONSHIP}: reference '{issue.target}' ({issue.code})"
        )
    for finding in report.findings:
        if finding.code in RECOMMENDING_FINDINGS:
            command = "error"
        elif finding.severity == SEVERITY_WARNING:
            command = "warning"
        else:
            command = "notice"
        lines.append(
            f"::{command} file={_repo_path(report, finding.path)}::{finding.code}: {finding.detail}"
        )
    return lines
