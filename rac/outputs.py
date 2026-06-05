"""Rendering for RAC command results: human-readable text and JSON.

Keeping this separate from :mod:`rac.cli` lets the CLI stay thin and makes the
output formats easy to test directly.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from .artifacts import ARTIFACT_SPECS
from .classification import CONFIDENCE_THRESHOLD, TypeScore
from .improve import ImprovementResult
from .ingest import IngestResult
from .inspect import DirectoryInspection, InspectionResult
from .models import Diff, Issue, Product
from .schema import SchemaReference, template_sections
from .stats import PortfolioStats

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
        lines.append(
            f"  {_yellow('warning')} [{issue.code}] {_loc(file, issue.line)}"
        )
        lines.append(f"          {issue.message}")

    lines.append("")
    lines.append(
        f"{len(errors)} error(s), {len(warnings)} warning(s)."
    )
    return "\n".join(lines)


def render_validation_json(product: Product, issues: list[Issue]) -> str:
    errors = [asdict(i) for i in issues if i.severity == "error"]
    warnings = [asdict(i) for i in issues if i.severity == "warning"]
    payload = {
        "file": product.source_path or None,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    return json.dumps(payload, indent=2)


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


def render_diff_json(d: Diff, old_path: str, new_path: str) -> str:
    payload = {
        "old": old_path,
        "new": new_path,
        "added_requirements": [asdict(r) for r in d.added_requirements],
        "removed_requirements": [asdict(r) for r in d.removed_requirements],
        "modified_requirements": [asdict(c) for c in d.modified_requirements],
        "added_metrics": d.added_metrics,
        "removed_metrics": d.removed_metrics,
        "added_risks": d.added_risks,
        "removed_risks": d.removed_risks,
    }
    return json.dumps(payload, indent=2)


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
    lines.append(
        f"Average Requirements Per Feature: {s.average_requirements:.1f}"
    )

    largest = s.largest_feature
    if largest is not None:
        lines.append(
            f"Largest Feature: {largest.name} ({largest.requirements} requirements)"
        )
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

    return "\n".join(lines)


def render_stats_json(s: PortfolioStats) -> str:
    largest = s.largest_feature
    payload = {
        "directory": s.directory,
        "features": s.files_found,
        "valid_features": s.valid_features,
        "invalid_features": s.invalid_features,
        "requirements": s.total_requirements,
        "metrics": s.total_metrics,
        "risks": s.total_risks,
        "features_missing_metrics": s.features_missing_metrics,
        "features_missing_risks": s.features_missing_risks,
        "missing_metrics": s.missing_metrics,
        "missing_risks": s.missing_risks,
        "average_requirements_per_feature": round(s.average_requirements, 1),
        "largest_feature": (
            {"name": largest.name, "requirements": largest.requirements}
            if largest is not None
            else None
        ),
        "requirements_by_feature": [
            {"name": f.name, "requirements": f.requirements}
            for f in s.requirements_by_feature
        ],
        "invalid": [{"file": f.path, "errors": f.error_codes} for f in s.invalid],
    }
    # Additive: only present when the portfolio actually contains decisions, so
    # requirement-only output is unchanged.
    if s.decisions:
        payload["decisions"] = {
            "count": s.decision_count,
            "by_status": s.decision_status_counts,
            "by_category": s.decision_category_counts,
        }
    # Additive: only present when the portfolio contains roadmaps. Lightweight by
    # design — count and validity only (no section-completeness breakdown).
    if s.roadmaps:
        payload["roadmaps"] = {
            "count": s.roadmap_count,
            "valid": s.valid_roadmaps,
            "invalid": [
                {"file": r.path, "errors": r.error_codes} for r in s.invalid_roadmaps
            ],
        }
    return json.dumps(payload, indent=2)


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
    return "\n".join(lines)


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


def render_inspect_json(result: InspectionResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def render_inspect_verbose(
    result: InspectionResult, scores: list[TypeScore]
) -> str:
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


def render_dir_inspect_json(d: DirectoryInspection) -> str:
    payload = {
        "schema_version": "1",
        "directory": d.directory,
        "recursive": d.recursive,
        "summary": {
            "total_files": d.total_files,
            "counts": d.counts,
            "unknown": d.unknown_count,
        },
        "files": [
            {"path": f.path, "type": f.type, "confidence": f.confidence}
            for f in d.files
        ],
    }
    return json.dumps(payload, indent=2)


# --- improve -----------------------------------------------------------------

# Shown when guidance cannot be produced. Ordering everywhere is required-first,
# then recommended (schema declaration order within each).
_UNKNOWN_MESSAGE = (
    "Unable to generate improvement guidance.\n"
    "Artifact type could not be determined."
)


def _unsupported_message(result: ImprovementResult) -> str:
    """Generic guidance for a known but unsupported artifact type (e.g. Decision)."""
    return (
        f"Artifact Type: {result.type.title()}\n\n"
        "Improvement guidance is not currently available for this artifact type."
    )


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


def render_improve_json(result: ImprovementResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def render_improve_template(result: ImprovementResult) -> str:
    """Emit Markdown templates for missing sections (required first)."""
    if result.type == "unknown":
        return _UNKNOWN_MESSAGE
    if not result.supported:
        return _unsupported_message(result)

    missing = result.missing_required + result.missing_recommended
    if not missing:
        return "# Nothing to add — all expected sections present."

    blocks: list[str] = []
    for section in missing:
        block = f"## {section.title()}\n\n_TODO_"
        guidance_lines = result.guidance.get(section, [])
        if guidance_lines:
            block += "\n\n" + "\n".join(f"<!-- {q} -->" for q in guidance_lines)
        blocks.append(block)
    return "\n\n".join(blocks) + "\n"


# --- schema ------------------------------------------------------------------


def render_schema_list_human(names: list[str]) -> str:
    lines = [_bold("Available Schemas:")]
    lines.extend(f"- {name}" for name in names)
    return "\n".join(lines)


def render_schema_list_json(names: list[str]) -> str:
    return json.dumps({"schemas": names}, indent=2)


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


def render_schema_json(ref: SchemaReference) -> str:
    return json.dumps(ref.to_dict(), indent=2)


def render_schema_template(ref: SchemaReference) -> str:
    blocks = ["# Title"]
    for section in template_sections(ref):
        block = f"## {section.name.title()}\n\n{section.body}"
        comments: list[str] = []
        if section.metadata_values:
            comments.append(f"Choose one: {' | '.join(section.metadata_values)}")
        comments.extend(section.guidance)
        if comments:
            block += "\n\n" + "\n".join(f"<!-- {comment} -->" for comment in comments)
        blocks.append(block)
    return "\n\n".join(blocks) + "\n"


# --- ingest ------------------------------------------------------------------


def render_ingest_json(result: IngestResult, output_path: str | None) -> str:
    payload = {
        "source": result.source_path,
        "converter": result.converter,
        "output": output_path,
        "markdown": result.markdown,
    }
    return json.dumps(payload, indent=2)
