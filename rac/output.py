"""Rendering for RAC command results: human-readable text and JSON.

Keeping this separate from :mod:`rac.cli` lets the CLI stay thin and makes the
output formats easy to test directly.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from .models import Diff, Issue, Product

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
