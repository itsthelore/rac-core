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
    lines: list[str] = [_bold(f"diff  {old_path} -> {new_path}"), ""]

    if d.is_empty():
        lines.append("No changes.")
        return "\n".join(lines)

    def section(title: str, items: list[str]) -> None:
        if items:
            lines.append(_bold(title))
            lines.extend(f"  {item}" for item in items)
            lines.append("")

    section(
        f"Added requirements ({len(d.added_requirements)})",
        [_green(f"+ [{r.id}] {r.text}") for r in d.added_requirements],
    )
    section(
        f"Removed requirements ({len(d.removed_requirements)})",
        [_red(f"- [{r.id}] {r.text}") for r in d.removed_requirements],
    )
    if d.modified_requirements:
        lines.append(_bold(f"Modified requirements ({len(d.modified_requirements)})"))
        for c in d.modified_requirements:
            lines.append(f"  ~ [{c.id}]")
            lines.append(f"      {_red('- ' + c.old_text)}")
            lines.append(f"      {_green('+ ' + c.new_text)}")
        lines.append("")

    section(
        f"Added metrics ({len(d.added_metrics)})",
        [_green(f"+ {m}") for m in d.added_metrics],
    )
    section(
        f"Removed metrics ({len(d.removed_metrics)})",
        [_red(f"- {m}") for m in d.removed_metrics],
    )
    section(
        f"Added risks ({len(d.added_risks)})",
        [_green(f"+ {r}") for r in d.added_risks],
    )
    section(
        f"Removed risks ({len(d.removed_risks)})",
        [_red(f"- {r}") for r in d.removed_risks],
    )

    return "\n".join(lines).rstrip()


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
