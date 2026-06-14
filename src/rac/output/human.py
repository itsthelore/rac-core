"""Human-readable rendering for RAC command results.

Keeping rendering out of :mod:`rac.cli` lets the CLI stay thin and makes the
output formats easy to test directly. JSON lives in :mod:`rac.output.json` and
Markdown templates in :mod:`rac.output.templates`.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rac.core.artifacts import ARTIFACT_SPECS, spec_for
from rac.core.classification import CONFIDENCE_THRESHOLD, TypeScore
from rac.core.hooks import HookSpec
from rac.core.models import Diff, Issue, Product
from rac.core.schema import SchemaReference
from rac.core.skills import SkillSpec
from rac.services.compare import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    RelationshipIssueRef,
)
from rac.services.create import CreatedArtifact
from rac.services.hook import InstalledHook
from rac.services.improve import ImprovementResult
from rac.services.index import RepositoryIndex
from rac.services.init import InitResult
from rac.services.inspect import DirectoryInspection, InspectionResult
from rac.services.migrate import (
    STATUS_MIGRATED,
    STATUS_SKIPPED_UNKNOWN,
    MigrationReport,
)
from rac.services.portfolio import PortfolioSummary
from rac.services.quickstart import QuickstartResult
from rac.services.relationships import (
    ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_EDGE_UNSUPPORTED,
    ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS,
    ISSUE_TARGET_NOT_FOUND,
    ISSUE_TARGET_SUPERSEDED,
    RelationshipReport,
    RelationshipValidation,
)
from rac.services.resolve import ResolutionResult, SearchResult
from rac.services.review import (
    PRIORITY_BROKEN_RELATIONSHIP,
    PRIORITY_INVALID_ARTIFACT,
    PRIORITY_MISSING_RECOMMENDED,
    PRIORITY_STALE_CORPUS,
    PRIORITY_UNKNOWN_ARTIFACT,
    ReviewReport,
)
from rac.services.skill import SkillInstallation
from rac.services.stats import PortfolioStats
from rac.services.validate import STATUS_INVALID, DirectoryValidation
from rac.services.watchkeeper import WatchkeeperReport

from ._shared import _UNKNOWN_MESSAGE, _unsupported_message

if TYPE_CHECKING:
    from rac.mcp.telemetry import TelemetrySummary as MCPTelemetrySummary

# --- Minimal color (auto-disabled when not writing to a TTY) ----------------

_USE_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _green(t: str) -> str:
    return _c(t, "32")


def _red(t: str) -> str:
    return _c(t, "31")


def _yellow(t: str) -> str:
    return _c(t, "33")


def _bold(t: str) -> str:
    return _c(t, "1")


def _loc(file: str, line: int | None) -> str:
    return f"{file}:{line}" if line is not None else file


# Day-one next step shown when a corpus has no recognized artifacts yet
# (v0.13.1): turn "nothing here" into "here is how to start".
EMPTY_CORPUS_HINT = "No artifacts yet — create your first with: rac quickstart"


# --- validate ---------------------------------------------------------------


def render_validation_human(product: Product, issues: list[Issue]) -> str:
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    file = product.source_path or "<input>"

    lines: list[str] = []
    if errors:
        lines.append(_red(_bold(f"FAIL  {file}")))
    else:
        lines.append(_green(_bold(f"PASS  {file}")))

    for issue in errors:
        lines.append(f"  {_red('error')}   [{issue.code}] {_loc(file, issue.line)}")
        lines.append(f"          {issue.message}")
    for issue in warnings:
        lines.append(f"  {_yellow('warning')} [{issue.code}] {_loc(file, issue.line)}")
        lines.append(f"          {issue.message}")

    lines.append("")
    lines.append(f"{len(errors)} error(s), {len(warnings)} warning(s).")
    return "\n".join(lines)


def render_validate_dir_human(result: DirectoryValidation) -> str:
    """Human-readable directory `rac validate` output (v0.7.9).

    Lists each invalid artifact with its errors; valid and skipped files are
    only counted, keeping the output a usable CI gate. Warnings stay in the
    JSON contract and in single-file validation.
    """
    lines: list[str] = []
    for f in result.files:
        if f.status != STATUS_INVALID:
            continue
        spec = spec_for(f.artifact_type)
        display = spec.display if spec else f.artifact_type
        lines.append(_red(_bold(f"FAIL  {f.path}")) + f"  ({display})")
        for issue in f.issues:
            if issue.severity != "error":
                continue
            lines.append(f"  {_red('error')}   [{issue.code}] {_loc(f.path, issue.line)}")
            lines.append(f"          {issue.message}")
        lines.append("")

    # OKF v0.1 conformance findings (ADR-048): listed like invalid artifacts so a
    # conformance-only failure is just as actionable as a per-file one.
    okf = result.okf
    if okf is not None and okf.findings:
        for finding in okf.findings:
            lines.append(_red(_bold(f"FAIL  {finding.path}")) + "  (OKF conformance)")
            lines.append(f"  {_red('error')}   [{finding.code}] {finding.path}")
            lines.append(f"          {finding.message}")
            lines.append("")

    skipped = f", {result.skipped} skipped (unknown type)" if result.skipped else ""
    verdict = _green("PASS") if result.ok else _red("FAIL")
    summary = (
        f"{verdict}  {result.directory} — "
        f"{result.checked} artifact(s) checked: "
        f"{result.valid} valid, {result.invalid} invalid{skipped}."
    )
    if okf is not None:
        summary += (
            " OKF v0.1: conformant."
            if okf.ok
            else f" OKF v0.1: {len(okf.findings)} conformance issue(s)."
        )
    lines.append(summary)
    if result.checked == 0 and result.skipped == 0:
        lines += ["", EMPTY_CORPUS_HINT]
    return "\n".join(lines)


# --- diff -------------------------------------------------------------------


def render_diff_human(d: Diff, old_path: str, new_path: str) -> str:
    if d.is_empty():
        return "No changes."

    blocks: list[str] = []

    def list_block(title: str, items: list[str], sign: str) -> None:
        """A titled block of single-line +/- entries (added/removed)."""
        if not items:
            return
        color = _green if sign == "+" else _red
        lines = [_bold(title), ""]
        lines.extend(color(f"{sign} {item}") for item in items)
        blocks.append("\n".join(lines))

    list_block(
        "Added Requirements",
        [f"{r.id} {r.text}" for r in d.added_requirements],
        "+",
    )
    list_block(
        "Removed Requirements",
        [f"{r.id} {r.text}" for r in d.removed_requirements],
        "-",
    )

    if d.modified_requirements:
        lines = [_bold("Modified Requirements"), ""]
        for i, c in enumerate(d.modified_requirements):
            if i:
                lines.append("")
            lines.append(f"~ {c.id}")
            lines.append("")
            lines.append("Before:")
            lines.append(_red(c.old_text))
            lines.append("")
            lines.append("After:")
            lines.append(_green(c.new_text))
        blocks.append("\n".join(lines))

    list_block("Added Metrics", d.added_metrics, "+")
    list_block("Removed Metrics", d.removed_metrics, "-")
    list_block("Added Risks", d.added_risks, "+")
    list_block("Removed Risks", d.removed_risks, "-")

    # Blank line between blocks.
    return "\n\n".join(blocks)


# --- stats -------------------------------------------------------------------


def render_stats_human(s: PortfolioStats) -> str:
    lines = [
        _bold("Portfolio Overview"),
        "==================",
        "",
        f"Features: {s.files_found}",
        f"Requirements: {s.total_requirements}",
        f"Metrics: {s.total_metrics}",
        f"Risks: {s.total_risks}",
        "",
        _bold("Quality"),
        "=======",
        "",
    ]

    def missing_block(label: str, names: list[str]) -> None:
        lines.append(f"{label}: {len(names)}")
        for name in names:
            lines.append(f"  - {name}")

    missing_block("Features Missing Metrics", s.missing_metrics)
    missing_block("Features Missing Risks", s.missing_risks)
    lines.append(f"Average Requirements Per Feature: {s.average_requirements:.1f}")

    largest = s.largest_feature
    if largest is not None:
        lines.append(f"Largest Feature: {largest.name} ({largest.requirements} requirements)")
    else:
        lines.append("Largest Feature: (none)")

    lines += ["", _bold("Requirements by Feature"), "=======================", ""]
    by_feature = s.requirements_by_feature
    if by_feature:
        width = max(len(f.name) for f in by_feature) + 4
        for f in by_feature:
            lines.append(f"{f.name:<{width}}{f.requirements}")
    else:
        lines.append("(none)")

    if s.invalid:
        lines += ["", _bold(f"Invalid Features ({len(s.invalid)})")]
        for f in s.invalid:
            reasons = ", ".join(f.error_codes) or "unknown"
            lines.append(f"  {_red(f.path)} — {reasons}")

    # Decisions are reported separately; omit the section entirely when there are
    # none so requirement-only portfolios render exactly as before.
    if s.decisions:
        lines += ["", _bold("Decisions"), "=========", "", f"Total: {s.decision_count}"]

        def breakdown(label: str, counts: dict[str, int]) -> None:
            lines.extend(["", _bold(label)])
            if counts:
                for name, count in counts.items():
                    lines.append(f"  - {name}: {count}")
            else:
                lines.append("  (none recorded)")

        breakdown("Status", s.decision_status_counts)
        breakdown("Category", s.decision_category_counts)

    # Roadmaps are reported separately and lightly (count + invalid only); the
    # section is omitted entirely when there are none.
    if s.roadmaps:
        lines += [
            "",
            _bold("Roadmaps"),
            "========",
            "",
            f"Total: {s.roadmap_count}",
            f"Valid: {s.valid_roadmaps}",
        ]
        invalid_roadmaps = s.invalid_roadmaps
        if invalid_roadmaps:
            lines += ["", _bold(f"Invalid Roadmaps ({len(invalid_roadmaps)})")]
            for r in invalid_roadmaps:
                reasons = ", ".join(r.error_codes) or "unknown"
                lines.append(f"  {_red(r.path)} — {reasons}")

    # Prompts are reported separately and lightly (count + invalid only); the
    # section is omitted entirely when there are none.
    if s.prompts:
        lines += [
            "",
            _bold("Prompts"),
            "=======",
            "",
            f"Total: {s.prompt_count}",
            f"Valid: {s.valid_prompts}",
        ]
        invalid_prompts = s.invalid_prompts
        if invalid_prompts:
            lines += ["", _bold(f"Invalid Prompts ({len(invalid_prompts)})")]
            for p in invalid_prompts:
                reasons = ", ".join(p.error_codes) or "unknown"
                lines.append(f"  {_red(p.path)} — {reasons}")

    # Designs are reported separately and lightly (count + invalid only); the
    # section is omitted entirely when there are none.
    if s.designs:
        lines += [
            "",
            _bold("Designs"),
            "=======",
            "",
            f"Total: {s.design_count}",
            f"Valid: {s.valid_designs}",
        ]
        invalid_designs = s.invalid_designs
        if invalid_designs:
            lines += ["", _bold(f"Invalid Designs ({len(invalid_designs)})")]
            for d in invalid_designs:
                reasons = ", ".join(d.error_codes) or "unknown"
                lines.append(f"  {_red(d.path)} — {reasons}")

    # Unrecognized documents (ADR-010): files that matched no known artifact
    # schema. Surfaced but rendered neutrally — they are not validation errors.
    # Omitted entirely when there are none, so portfolios of only known artifacts
    # render exactly as before.
    if s.unrecognized:
        count = s.unrecognized_count
        noun = "document" if count == 1 else "documents"
        lines += [
            "",
            _bold("Unrecognized"),
            "============",
            "",
            f"{count} {noun} matched no known artifact schema (not errors — see ADR-010):",
        ]
        for u in s.unrecognized:
            lines.append(f"  {u.path}")

    # Declared relationship-presence counts (v0.7.0). Omitted entirely when no
    # artifact declares a relationship section, so existing portfolios are
    # unchanged. These are presence counts, not resolved/edge counts.
    if s.relationship_counts:
        lines += ["", _bold("Relationships"), "=============", ""]
        for section, count in s.relationship_counts.items():
            lines.append(f"Artifacts with {section.title()}: {count}")

    if s.is_empty:
        lines += ["", EMPTY_CORPUS_HINT]

    return "\n".join(lines)


# --- inspect -----------------------------------------------------------------


def render_inspect_human(result: InspectionResult) -> str:
    lines = [
        _bold(f"Artifact Type: {result.type.title()}"),
        f"Confidence: {result.confidence:.0%}",
        "",
        _bold("Present Sections:"),
    ]
    if result.present_sections:
        lines.extend(_green(f"  ✓ {s.title()}") for s in result.present_sections)
    else:
        lines.append("  (none)")
    if result.missing_sections:
        lines += ["", _bold("Missing Sections:")]
        lines.extend(_red(f"  ✗ {s.title()}") for s in result.missing_sections)
    _append_decision_metadata(lines, result)
    _append_relationships(lines, result)
    return "\n".join(lines)


def _append_relationships(lines: list[str], result: InspectionResult) -> None:
    """Add a Relationships block when the artifact declares related artifacts."""
    if not result.relationships:
        return
    lines += ["", _bold("Relationships:")]
    for section, refs in result.relationships.items():
        lines.append(f"  {section.replace('_', ' ').title()}:")
        lines.extend(f"    - {ref}" for ref in refs)


def _append_decision_metadata(lines: list[str], result: InspectionResult) -> None:
    """Add Status / Category / Supersedes lines when a decision declares them."""
    pairs = [
        ("Status", result.status),
        ("Category", result.category),
        ("Supersedes", result.supersedes),
    ]
    shown = [(label, value) for label, value in pairs if value]
    if shown:
        lines += ["", _bold("Decision Metadata:")]
        lines.extend(f"  {label}: {value}" for label, value in shown)


def render_inspect_verbose(result: InspectionResult, scores: list[TypeScore]) -> str:
    """Explainable single-file output: matches, misses, and the score math."""
    chosen = next((s for s in scores if s.name == result.type), None)
    if chosen is None:  # Unknown — explain via the closest candidate
        chosen = scores[0] if scores else None

    lines = [
        _bold(f"Artifact Type: {result.type.title()}"),
        f"Confidence: {result.confidence:.0%}",
    ]
    if chosen is None:
        return "\n".join(lines)
    if result.type == "unknown":
        lines.append(f"Closest match: {chosen.display}")

    def block(title: str, names: list[str]) -> None:
        lines.extend(["", _bold(title)])
        if names:
            lines.extend(_green(f"  ✓ {s.title()}") for s in names)
        else:
            lines.append("  (none)")

    block("Required Matches:", chosen.matched_required)
    block("Recommended Matches:", chosen.matched_recommended)
    if chosen.missing:
        lines.extend(["", _bold("Missing:")])
        lines.extend(_red(f"  ✗ {s.title()}") for s in chosen.missing)

    req, rec = len(chosen.matched_required), len(chosen.matched_recommended)
    lines.extend(
        [
            "",
            _bold("Score:")
            + f" {req} + 0.5 × {rec} = {chosen.points:g} / {chosen.ceiling:g}"
            + f" = {round(chosen.fit, 2)}",
        ]
    )
    if result.type == "unknown":
        lines.append(f"(below the {CONFIDENCE_THRESHOLD:.0%} threshold → Unknown)")
    return "\n".join(lines)


def render_dir_inspect_human(d: DirectoryInspection) -> str:
    counts = d.counts
    lines = [_bold(f"Files Inspected: {d.total_files}"), ""]
    for spec in ARTIFACT_SPECS:
        lines.append(f"{spec.display}s: {counts.get(spec.name, 0)}")
    lines.append(f"Unknown: {counts.get('unknown', 0)}")
    return "\n".join(lines)


# --- improve -----------------------------------------------------------------


def render_improve_human(result: ImprovementResult) -> str:
    if result.type == "unknown":
        return _UNKNOWN_MESSAGE
    if not result.supported:
        return _unsupported_message(result)

    lines = [_bold(f"Artifact Type: {result.type.title()}"), ""]
    if not result.missing_required and not result.missing_recommended:
        lines.append("Nothing to improve — all expected sections present.")
        return "\n".join(lines)

    def block(title: str, names: list[str]) -> None:
        lines.append(_bold(title))
        if names:
            for s in names:
                lines.append(f"  - {s.title()}")
                lines.extend(f"      • {q}" for q in result.guidance.get(s, []))
        else:
            lines.append("  (none)")
        lines.append("")

    block("Missing Required:", result.missing_required)
    block("Missing Recommended:", result.missing_recommended)
    return "\n".join(lines).rstrip()


# --- schema ------------------------------------------------------------------


def render_schema_list_human(names: list[str]) -> str:
    lines = [_bold("Available Schemas:")]
    lines.extend(f"- {name}" for name in names)
    return "\n".join(lines)


def render_unknown_schema(name: str, available: list[str]) -> str:
    lines = [f"Unknown schema: {name}", "", "Available schemas:"]
    lines.extend(f"- {schema}" for schema in available)
    return "\n".join(lines)


def render_schema_human(ref: SchemaReference) -> str:
    lines = [_bold(f"Artifact Type: {ref.display}"), ""]

    def section_block(title: str, names: list[str]) -> None:
        lines.extend([_bold(title)])
        if not names:
            lines.append("  (none)")
            lines.append("")
            return
        for name in names:
            lines.append(f"  - {name.title()}")
            description = ref.descriptions.get(name)
            if description:
                lines.append(f"      Description: {description}")
            guidance = ref.guidance.get(name, [])
            if guidance:
                lines.append("      Guidance:")
                lines.extend(f"        - {item}" for item in guidance)
        lines.append("")

    section_block("Required Sections:", ref.required)
    section_block("Recommended Sections:", ref.recommended)
    section_block("Optional Sections:", ref.optional)

    if ref.metadata:
        lines.append(_bold("Metadata Fields:"))
        for name, values in ref.metadata.items():
            lines.append(f"  - {name.title()}: {' | '.join(values)}")
    return "\n".join(lines).rstrip()


# --- relationships -----------------------------------------------------------


def _relationship_label(snake_section: str) -> str:
    """``related_decisions`` -> ``Related Decisions``; ``supersedes`` -> ``Supersedes``."""
    return snake_section.replace("_", " ").title()


def render_relationships_human(report: RelationshipReport) -> str:
    lines = [
        _bold("Relationships"),
        "",
        f"Files Inspected: {report.total_files}",
        f"Artifacts With Relationships: {report.artifacts_with_relationships}",
        f"Relationships Found: {report.relationship_count}",
    ]

    counts = report.counts
    if counts:
        lines += ["", _bold("By Type:")]
        lines.extend(
            f"- {_relationship_label(section)}: {count}" for section, count in counts.items()
        )

    # Per-artifact detail (REQ-005), only for artifacts that declare relationships.
    # References that resolve uniquely show their human-friendly label
    # (v0.7.12): the stored reference stays first — it is the source of truth.
    for artifact in report.artifacts:
        lines += ["", artifact.path]
        for section, refs in artifact.relationships.items():
            lines.append(f"  {_relationship_label(section)}:")
            for ref in refs:
                resolved = report.labels.get(ref.casefold())
                lines.append(f"  - {ref} — {resolved}" if resolved else f"  - {ref}")

    return "\n".join(lines)


# --- relationship validation -------------------------------------------------

# Suffix shown after a flagged reference, per issue code.
_REF_ISSUE_SUFFIX = {
    ISSUE_TARGET_NOT_FOUND: "not found",
    ISSUE_TARGET_AMBIGUOUS: "ambiguous",
    ISSUE_SELF_REFERENCE: "self-reference",
    ISSUE_TARGET_SUPERSEDED: "superseded",
}


def render_relationship_validation_human(report: RelationshipValidation) -> str:
    lines = [
        _bold("Relationship Validation"),
        "",
        f"Relationships Checked: {report.relationships_checked}",
        f"Validation Issues: {report.validation_issues}",
    ]

    duplicates = [i for i in report.issues if i.code == ISSUE_DUPLICATE_IDENTIFIER]
    unsupported = [i for i in report.issues if i.code == ISSUE_EDGE_UNSUPPORTED]
    references = [
        i
        for i in report.issues
        if i.code not in (ISSUE_DUPLICATE_IDENTIFIER, ISSUE_EDGE_UNSUPPORTED)
    ]

    if duplicates:
        lines += ["", _bold("Duplicate Identifiers")]
        for issue in duplicates:
            count = len(issue.paths or [])
            lines.append(_red(f"✗ {issue.identifier} ({count} files)"))
            lines.extend(f"  - {p}" for p in issue.paths or [])

    if unsupported:
        lines += ["", _bold("Unsupported Relationships")]
        current_source = None
        for issue in unsupported:
            if issue.source_path != current_source:
                current_source = issue.source_path
                lines += ["", issue.source_path or "<input>"]
            label = _relationship_label(issue.relationship or "")
            lines.append(_red(f"  ✗ {label} not supported for this artifact type"))

    if references:
        lines += ["", _bold("Broken Relationships")]
        current_source = None
        current_section = None
        for issue in references:
            if issue.source_path != current_source:
                current_source = issue.source_path
                current_section = None
                lines += ["", issue.source_path or "<input>"]
            if issue.relationship != current_section:
                current_section = issue.relationship
                lines.append(f"  {_relationship_label(issue.relationship or '')}:")
            suffix = _REF_ISSUE_SUFFIX.get(issue.code, issue.code)
            lines.append(_red(f"  ✗ {issue.target} {suffix}"))

    return "\n".join(lines)


# --- portfolio ---------------------------------------------------------------


def render_portfolio_human(s: PortfolioSummary) -> str:
    """Human-readable `rac portfolio` output."""
    lines = [
        _bold("Repository Summary"),
        "==================",
        "",
        f"Directory:  {s.directory}",
        f"Artifacts:  {s.total_artifacts}",
        "",
        _bold("By Type"),
        "-------",
        "",
    ]
    for type_name, count in s.by_type.items():
        if count > 0:
            lines.append(f"  {type_name.title():<14} {count}")

    lines += [
        "",
        _bold("Validation"),
        "----------",
        "",
        f"  Valid:    {s.valid_artifacts}",
        f"  Invalid:  {s.invalid_artifacts}",
        "",
        _bold("Completeness"),
        "------------",
        "",
        f"  {s.completeness:.0%} "
        f"({s.filled_slots} / {s.recommended_slots} recommended slots filled)",
        "",
        _bold("Relationships"),
        "-------------",
        "",
        f"  Total:    {s.relationships.total}",
        f"  Valid:    {s.relationships.valid}",
        f"  Broken:   {s.relationships.broken}",
        f"  Orphaned: {s.relationships.orphaned}",
        f"  Coverage: {s.relationships.coverage:.0%}",
    ]

    if s.attention:
        lines += ["", _bold(f"Attention ({len(s.attention)} items)"), "----------", ""]
        for item in s.attention:
            icon = _red("✗") if item.severity == "error" else _yellow("!")
            lines.append(f"  {icon} {item.identifier}")
            lines.append(f"      {item.message}")
    else:
        lines += ["", _green("✓ No attention items.")]

    score = s.health_score
    score_color = _green if score >= 80 else _yellow if score >= 60 else _red
    lines += [
        "",
        _bold("Health Score"),
        "------------",
        "",
        f"  {score_color(str(score))} / 100",
    ]

    if s.total_artifacts == 0:
        lines += ["", EMPTY_CORPUS_HINT]

    return "\n".join(lines)


# --- review ------------------------------------------------------------------

_PRIORITY_LABELS = {
    PRIORITY_INVALID_ARTIFACT: "Invalid artifacts",
    PRIORITY_BROKEN_RELATIONSHIP: "Broken relationships",
    PRIORITY_UNKNOWN_ARTIFACT: "Unrecognized artifacts",
    PRIORITY_MISSING_RECOMMENDED: "Missing recommended information",
    PRIORITY_STALE_CORPUS: "Write cadence",
}


def render_review_human(r: ReviewReport) -> str:
    """Human-readable `rac review` output (v0.7.9).

    One report answering "what needs attention?": inventory, validation and
    relationship summaries, issues grouped by priority, deduplicated suggested
    actions, and the health score.
    """
    p = r.portfolio
    lines = [
        _bold("Repository Review"),
        "=================",
        "",
        f"Directory:  {r.directory}",
        f"Artifacts:  {p.total_artifacts}",
        "",
    ]
    for type_name, count in p.by_type.items():
        if count > 0:
            lines.append(f"  {type_name.title():<14} {count}")

    lines += [
        "",
        _bold("Validation"),
        "----------",
        "",
        f"  Valid:    {p.valid_artifacts}",
        f"  Invalid:  {p.invalid_artifacts}",
        "",
        _bold("Relationships"),
        "-------------",
        "",
        f"  Total:    {p.relationships.total}",
        f"  Valid:    {p.relationships.valid}",
        f"  Broken:   {p.relationships.broken}",
    ]

    if r.issues:
        lines += ["", _bold(f"Issues ({len(r.issues)})"), "------"]
        for priority, label in _PRIORITY_LABELS.items():
            group = [i for i in r.issues if i.priority == priority]
            if not group:
                continue
            lines += ["", f"  Priority {priority} — {label}:"]
            for issue in group:
                icon = (
                    _red("✗")
                    if issue.severity == "error"
                    else _yellow("!")
                    if issue.severity == "warning"
                    else "·"
                )
                lines.append(f"    {icon} {issue.identifier}")
                lines.append(f"        {issue.message}")
        lines += ["", _bold("Suggested Actions"), "-----------------", ""]
        for n, action in enumerate(r.actions, start=1):
            lines.append(f"  {n}. {action}")
    else:
        lines += ["", _green("✓ Nothing needs attention.")]

    score = p.health_score
    score_color = _green if score >= 80 else _yellow if score >= 60 else _red
    lines += [
        "",
        _bold("Health Score"),
        "------------",
        "",
        f"  {score_color(str(score))} / 100",
    ]
    if p.total_artifacts == 0:
        lines += ["", EMPTY_CORPUS_HINT]
    return "\n".join(lines)


# --- index -------------------------------------------------------------------


def render_index_human(index: RepositoryIndex) -> str:
    """Human-readable `rac index` output: a repository manifest."""
    lines = [
        _bold("Repository Index"),
        "================",
        "",
        f"Directory:  {index.directory}",
        f"Artifacts:  {index.artifact_count}",
        "",
    ]
    if not index.artifacts:
        lines.append("(none)")
        return "\n".join(lines)

    # Aligned columns: ID, type, title (— when absent), path last.
    id_w = max(len(e.id) for e in index.artifacts)
    type_w = max(len(e.type) for e in index.artifacts)
    title_w = max(len(e.title or "—") for e in index.artifacts)
    for e in index.artifacts:
        title = e.title or "—"
        lines.append(f"  {e.id:<{id_w}}  {e.type:<{type_w}}  {title:<{title_w}}  {e.path}")
    return "\n".join(lines)


# --- create (rac new / rac templates, v0.7.10) -------------------------------


def render_templates_human(names: list[str]) -> str:
    """Human `rac templates` output: the canonical template set."""
    lines = [_bold("Available artifact templates:"), ""]
    lines.extend(f"- {name}" for name in names)
    return "\n".join(lines)


def render_new_human(created: CreatedArtifact) -> str:
    """Human `rac new` output: what was created, its identity, and where."""
    return (
        f"Created {created.artifact_type} artifact: {created.path}\n"
        f"ID: {created.id}\n"
        f"\n"
        f"Edit the TODO placeholders, then check it with: rac validate {created.path}"
    )


def render_init_human(result: InitResult) -> str:
    """Human `rac init` output: the established identity namespace."""
    verb = "Initialized" if result.created else "Already initialized:"
    return f"{verb} repository key {result.repository_key}\nConfig: {result.config_path}"


def render_quickstart_human(result: QuickstartResult) -> str:
    """Human `rac quickstart` output: identity, first artifact, next step."""
    verb = "Initialized" if result.created else "Using"
    artifact = result.artifact
    return (
        f"{verb} repository key {result.repository_key}\n"
        f"Created {artifact.artifact_type} artifact: {artifact.path}\n"
        f"ID: {artifact.id}\n"
        f"\n"
        f"Next: edit the TODO placeholders, then run: rac validate {artifact.path}"
    )


# --- resolve / find (v0.7.12) -------------------------------------------------


def render_resolve_human(result: ResolutionResult) -> str:
    """Human `rac resolve` output for a resolved artifact."""
    artifact = result.artifact
    assert artifact is not None  # resolved outcome implies an artifact
    return (
        f"{_bold(artifact.id)}\n"
        f"\n"
        f"Type: {artifact.type}\n"
        f"Title: {artifact.title or '—'}\n"
        f"Path: {artifact.path}"
    )


def render_find_human(result: SearchResult) -> str:
    """Human `rac find` output: aligned match rows, or a valid empty result."""
    if not result.matches:
        return f"No artifacts match {result.query!r}."
    id_w = max(len(m.id) for m in result.matches)
    type_w = max(len(m.type) for m in result.matches)
    lines: list[str] = []
    for m in result.matches:
        lines.append(f"{m.id:<{id_w}}  {m.type:<{type_w}}  {m.title or '—'}")
        # Heading/body matches carry a snippet; show the matched section and line
        # indented under the row so an agent or reader can triage without opening
        # the file (ADR-038). Metadata matches have no snippet and stay one line.
        if m.snippet is not None:
            section = f"{m.section}: " if m.section else ""
            lines.append(f"{' ' * id_w}  {' ' * type_w}  ↳ {section}{m.snippet}")
    lines.append("")
    lines.append(f"{result.match_count} match(es) for {result.query!r}.")
    return "\n".join(lines)


# --- migrate (v0.7.13) ----------------------------------------------------------


def render_migrate_human(report: MigrationReport) -> str:
    """Human `rac migrate metadata` output: assigned IDs and what remains."""
    lines: list[str] = []
    if report.dry_run:
        lines += [_bold("Dry run — no files were written."), ""]

    migrated = [f for f in report.files if f.status == STATUS_MIGRATED]
    unknown = [f for f in report.files if f.status == STATUS_SKIPPED_UNKNOWN]

    verb = "Would migrate" if report.dry_run else "Migrated"
    if migrated:
        lines.append(_bold(f"{verb} {len(migrated)} artifact(s):"))
        path_w = max(len(f.path) for f in migrated)
        for f in migrated:
            lines.append(f"  {f.path:<{path_w}}  {f.id}  ({f.type})")
    else:
        lines.append(f"{verb} 0 artifact(s) — nothing to migrate.")

    if unknown:
        lines += ["", _bold(f"Skipped {len(unknown)} unrecognized document(s):")]
        lines.extend(f"  - {f.path}" for f in unknown)

    lines += [
        "",
        f"{len(report.files)} file(s): {report.migrated} migrated, "
        f"{report.already_canonical} already canonical, "
        f"{report.skipped_unknown} skipped (unknown type).",
    ]
    return "\n".join(lines)


# --- skill (rac skill install / list, v0.10.5) -------------------------------


def render_skill_install_human(installation: SkillInstallation) -> str:
    """Human `rac skill install` output: what was installed and where."""
    lines = [f"Installed {s.skill} skill: {s.path}" for s in installation.skills]
    lines += [
        "",
        "Claude Code discovers skills automatically from .claude/skills/ in the project.",
    ]
    return "\n".join(lines)


def render_skill_list_human(specs: list[SkillSpec]) -> str:
    """Human `rac skill list` output: the bundled skill set."""
    lines = [_bold("Bundled agent skills:"), ""]
    name_w = max(len(spec.name) for spec in specs)
    lines.extend(f"- {spec.name:<{name_w}}  {spec.description}" for spec in specs)
    return "\n".join(lines)


def render_hook_install_human(installation: InstalledHook) -> str:
    """Human `rac hook install` output: what was installed and where."""
    h = installation
    return (
        f"Installed {h.style} git hook: {h.path}\n"
        f"\n"
        f"Git runs it automatically on each commit. Remove the file to stop it."
    )


def render_hook_list_human(specs: list[HookSpec]) -> str:
    """Human `rac hook list` output: the bundled hook set."""
    lines = [_bold("Bundled git hooks:"), ""]
    style_w = max(len(spec.style) for spec in specs)
    lines.extend(f"- {spec.style:<{style_w}}  {spec.description}" for spec in specs)
    return "\n".join(lines)


# --- mcp-stats (v0.10.4) ----------------------------------------------------


def render_mcp_stats_human(summary: MCPTelemetrySummary) -> str:
    """Human `rac mcp-stats` output — what the local telemetry log says.

    An empty or missing log is a valid answer (telemetry is off by default),
    rendered as guidance rather than an error.
    """
    lines = [
        _bold("Guide Telemetry"),
        "===============",
        "",
        f"Log: {summary.path}",
    ]
    if summary.event_count == 0:
        lines += [
            "",
            "No telemetry recorded.",
            "Telemetry is off by default; enable it with: rac mcp --telemetry",
        ]
        if summary.skipped_lines:
            lines += ["", f"Skipped Unreadable Lines: {summary.skipped_lines}"]
        return "\n".join(lines)
    lines += [
        f"Events: {summary.event_count}",
        f"Sessions: {summary.session_count}",
        f"First Event: {summary.first_ts}",
        f"Last Event: {summary.last_ts}",
        "",
        _bold("Tool Usage"),
        "==========",
        "",
    ]
    for usage in summary.tools:
        lines.append(
            f"  {usage.tool}: {usage.calls} call(s), {usage.errors} error(s), "
            f"{usage.truncated} truncated, avg {usage.avg_duration_ms} ms"
        )
    if summary.skipped_lines:
        lines += ["", f"Skipped Unreadable Lines: {summary.skipped_lines}"]
    return "\n".join(lines)


# --- watchkeeper --------------------------------------------------------------


def _delta(base: int, head: int) -> str:
    return f"{base} → {head}"


def _issue_phrase(issue: RelationshipIssueRef) -> str:
    if issue.relationship is None:
        subject = issue.identifier or issue.path
        return f"{subject}: {issue.code}"
    label = issue.relationship.replace("_", " ").title()
    return f"{issue.path} — {label} reference '{issue.target}' ({issue.code})"


def render_watchkeeper_human(report: WatchkeeperReport) -> str:
    """Human-readable `rac watchkeeper` output (v0.12.0).

    One report answering "what changed between these repository states?":
    changed artifacts, validation delta, relationship delta, and repository
    statistics delta.
    """
    comparison = report.comparison
    lines = [
        _bold("RAC Watchkeeper"),
        "===============",
        "",
        f"Directory:  {report.directory}",
        f"Comparing:  {report.base} → {report.head}",
        "",
        _bold("Changed Artifacts"),
        "-----------------",
        "",
    ]
    if comparison.changes:
        icons = {CHANGE_ADDED: "+", CHANGE_MODIFIED: "~", CHANGE_REMOVED: "-"}
        for change in comparison.changes:
            lines.append(f"  {icons[change.change]} {change.path}  ({change.type})")
    else:
        lines.append("  No product artifact changes detected.")

    validation = comparison.validation
    lines += [
        "",
        _bold("Validation"),
        "----------",
        "",
        f"  Valid:    {_delta(validation.base_valid, validation.head_valid)}",
        f"  Invalid:  {_delta(validation.base_invalid, validation.head_invalid)}",
    ]
    if validation.newly_invalid:
        lines += ["", "  Newly invalid:"]
        lines += [f"    {_red('✗')} {path}" for path in validation.newly_invalid]
    if validation.newly_valid:
        lines += ["", "  Newly valid:"]
        lines += [f"    {_green('✓')} {path}" for path in validation.newly_valid]

    relationships = comparison.relationships
    lines += [
        "",
        _bold("Relationships"),
        "-------------",
        "",
        f"  Total:    {_delta(relationships.base.total, relationships.head.total)}",
        f"  Valid:    {_delta(relationships.base.valid, relationships.head.valid)}",
        f"  Broken:   {_delta(relationships.base.broken, relationships.head.broken)}",
    ]
    if relationships.new_issues:
        lines += ["", "  New issues:"]
        lines += [
            f"    {_yellow('!')} {_issue_phrase(issue)}" for issue in relationships.new_issues
        ]
    if relationships.resolved_issues:
        lines += ["", "  Resolved issues:"]
        lines += [
            f"    {_green('✓')} {_issue_phrase(issue)}" for issue in relationships.resolved_issues
        ]

    stats = comparison.stats
    lines += [
        "",
        _bold("Repository Changes"),
        "------------------",
        "",
    ]
    for type_name, (base_count, head_count) in stats.by_type.items():
        if base_count or head_count:
            lines.append(f"  {type_name.title():<14} {_delta(base_count, head_count)}")
    lines.append(f"  {'Total':<14} {_delta(stats.total[0], stats.total[1])}")

    if report.findings:
        lines += ["", _bold(f"Findings ({len(report.findings)})"), "--------"]
        for finding in report.findings:
            icon = _yellow("!") if finding.severity == "warning" else "·"
            lines += [
                "",
                f"  {icon} [{finding.code}] {finding.path}",
                f"      {finding.detail}",
            ]
            lines += [f"      {line}" for line in finding.evidence]

    # Review verdict (v0.12.2).
    lines += ["", _bold("Review"), "------", ""]
    if report.review_recommended:
        lines.append(f"  {_yellow('Review recommended.')}")
        lines += ["", "  Reasons:", ""]
        lines += [f"    · {rec.reason}  [{rec.code}]" for rec in report.recommendations]
    else:
        lines.append(f"  {_green('✓ Nothing requiring attention.')}")

    return "\n".join(lines)
