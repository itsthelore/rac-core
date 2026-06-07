"""Validate a :class:`~rac.models.Product` against RAC's format rules.

Returns a flat list of :class:`~rac.models.Issue` objects (errors and warnings);
it never stops at the first problem. Whether a run "fails" is the CLI's decision,
based on whether any ``error``-severity issues are present.
"""

from __future__ import annotations

import re
from collections import Counter

from .artifacts import spec_for
from .classification import classify
from .models import Issue, Product

# A file with more requirements than this earns a (non-failing) warning.
MAX_REQUIREMENTS = 50

# Vague verbs that tend to hide unspecified behavior.
AMBIGUOUS_VERBS = ("support", "handle", "allow", "enable")
_AMBIGUOUS_RE = re.compile(
    r"\b(" + "|".join(AMBIGUOUS_VERBS) + r")\b", re.IGNORECASE
)


def has_errors(issues: list[Issue]) -> bool:
    """True if any issue is error-severity."""
    return any(issue.severity == "error" for issue in issues)


def validate(product: Product) -> list[Issue]:
    """Check ``product`` and return all structural and quality findings.

    Dispatches on artifact type. Each type with its own schema is routed
    explicitly; the final ``_validate_requirement`` arm is a
    backwards-compatibility fallback for Unknown/legacy documents (and RAC's
    original Requirement rules), *not* the long-term model — new artifact types
    must be routed explicitly above it.
    """
    artifact_type = classify(product).type
    if artifact_type == "decision":
        return _validate_decision(product)
    if artifact_type == "roadmap":
        return _validate_roadmap(product)
    if artifact_type == "prompt":
        return _validate_prompt(product)
    if artifact_type == "design":
        return _validate_design(product)
    return _validate_requirement(product)


def _first_value(body: str) -> str:
    """First non-empty line of a section body (single-value metadata)."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _validate_decision(product: Product) -> list[Issue]:
    """Validate a Decision artifact (REQ-001/002/006/007).

    Missing metadata never fails (it is optional); only *invalid values* are
    errors. Required sections (Context, Decision, Consequences) must be present.
    """
    spec = spec_for("decision")
    assert spec is not None  # the decision spec always exists
    issues: list[Issue] = []

    if not product.title:
        issues.append(Issue("error", "missing-title", "File has no top-level # title."))

    if product.extra_title_lines:
        issues.append(
            Issue(
                "error",
                "multiple-titles",
                "File has more than one top-level # title; expected exactly one.",
                product.extra_title_lines[0],
            )
        )

    # Required sections define the artifact (ADR format).
    for section in spec.required:
        if section not in product.sections:
            issues.append(
                Issue(
                    "error",
                    f"missing-{section}",
                    f"Decision is missing a ## {section.title()} section.",
                )
            )

    # Constrained metadata: a present value must be in the allowed set. A missing
    # section is fine — metadata is optional (REQ-007).
    for field_name, allowed in spec.metadata.items():
        body = product.sections.get(field_name, "")
        value = _first_value(body)
        if value and not any(value.casefold() == a.casefold() for a in allowed):
            issues.append(
                Issue(
                    "error",
                    f"invalid-decision-{field_name}",
                    f"## {field_name.title()} value {value!r} is not one of: "
                    f"{', '.join(allowed)}.",
                )
            )

    return issues


def _validate_roadmap(product: Product) -> list[Issue]:
    """Validate a Roadmap artifact (REQ-003).

    Required sections (Outcomes, Initiatives) must be present; missing recommended
    sections never fail. Roadmaps carry no constrained metadata (no owners, dates,
    or status — ADR-017: RAC manages knowledge, not work).
    """
    spec = spec_for("roadmap")
    assert spec is not None  # the roadmap spec always exists
    issues: list[Issue] = []

    if not product.title:
        issues.append(Issue("error", "missing-title", "File has no top-level # title."))

    if product.extra_title_lines:
        issues.append(
            Issue(
                "error",
                "multiple-titles",
                "File has more than one top-level # title; expected exactly one.",
                product.extra_title_lines[0],
            )
        )

    for section in spec.required:
        if section not in product.sections:
            issues.append(
                Issue(
                    "error",
                    f"missing-{section}",
                    f"Roadmap is missing a ## {section.title()} section.",
                )
            )

    return issues


def _validate_prompt(product: Product) -> list[Issue]:
    """Validate a Prompt artifact (REQ-006).

    Required sections (Objective, Input, Instructions, Output) must be present;
    missing recommended/optional sections never fail or warn. Prompts carry no
    metadata and are never executed (REQ-011) — RAC treats them as knowledge.

    Section presence is checked against the raw headings, consistent with the
    Decision and Roadmap validators; the Prompt spec's synonyms are a
    classification aid only, so validation still expects the canonical headings.
    """
    spec = spec_for("prompt")
    assert spec is not None  # the prompt spec always exists
    issues: list[Issue] = []

    if not product.title:
        issues.append(Issue("error", "missing-title", "File has no top-level # title."))

    if product.extra_title_lines:
        issues.append(
            Issue(
                "error",
                "multiple-titles",
                "File has more than one top-level # title; expected exactly one.",
                product.extra_title_lines[0],
            )
        )

    for section in spec.required:
        if section not in product.sections:
            issues.append(
                Issue(
                    "error",
                    f"missing-{section}",
                    f"Prompt is missing a ## {section.title()} section.",
                )
            )

    return issues


def _validate_design(product: Product) -> list[Issue]:
    """Validate a Design artifact (v0.6.3).

    Required sections (Context, User Need, Design, Constraints) must be present;
    missing recommended/optional sections never fail or warn. Designs carry no
    metadata and are knowledge artifacts, not UI renderings or component systems.
    """
    spec = spec_for("design")
    assert spec is not None  # the design spec always exists
    issues: list[Issue] = []

    if not product.title:
        issues.append(Issue("error", "missing-title", "File has no top-level # title."))

    if product.extra_title_lines:
        issues.append(
            Issue(
                "error",
                "multiple-titles",
                "File has more than one top-level # title; expected exactly one.",
                product.extra_title_lines[0],
            )
        )

    for section in spec.required:
        if section not in product.sections:
            issues.append(
                Issue(
                    "error",
                    f"missing-{section.replace(' ', '-')}",
                    f"Design is missing a ## {section.title()} section.",
                )
            )

    return issues


def _validate_requirement(product: Product) -> list[Issue]:
    """Check ``product`` and return all structural and quality findings."""
    issues: list[Issue] = []

    # --- Hard failures: structure -------------------------------------------
    if not product.title:
        issues.append(Issue("error", "missing-title", "File has no top-level # title."))

    if product.extra_title_lines:
        # One error regardless of how many extra titles there are; point at the
        # first offending title.
        issues.append(
            Issue(
                "error",
                "multiple-titles",
                "File has more than one top-level # title; expected exactly one.",
                product.extra_title_lines[0],
            )
        )

    if not product.has_problem_section:
        issues.append(
            Issue("error", "missing-problem", "File is missing a ## Problem section.")
        )

    if not product.has_requirements_section:
        issues.append(
            Issue(
                "error",
                "missing-requirements",
                "File is missing a ## Requirements section.",
            )
        )

    # --- Hard failures: malformed requirement lines -------------------------
    for m in product.malformed_requirements:
        if m.bad_id is None:
            issues.append(
                Issue(
                    "error",
                    "req-missing-id",
                    f"Requirement line has no [REQ-NNN] ID: {m.raw!r}",
                    m.line,
                )
            )
        elif m.empty_text:
            issues.append(
                Issue(
                    "error",
                    "empty-req-text",
                    f"Requirement [{m.bad_id}] has no description text.",
                    m.line,
                )
            )
        else:
            issues.append(
                Issue(
                    "error",
                    "malformed-req-id",
                    f"Malformed requirement ID [{m.bad_id}]; expected form [REQ-NNN].",
                    m.line,
                )
            )

    # --- Hard failures: duplicate IDs ---------------------------------------
    id_counts = Counter(r.id for r in product.requirements)
    seen: set[str] = set()
    for r in product.requirements:
        if id_counts[r.id] > 1 and r.id not in seen:
            seen.add(r.id)
            issues.append(
                Issue(
                    "error",
                    "duplicate-req-id",
                    f"Duplicate requirement ID {r.id} (used {id_counts[r.id]} times).",
                    r.line,
                )
            )

    # --- Warnings: missing optional sections --------------------------------
    if not product.has_metrics_section:
        issues.append(
            Issue(
                "warning",
                "missing-success-metrics",
                "No ## Success Metrics section (optional, but recommended).",
            )
        )
    if not product.has_risks_section:
        issues.append(
            Issue(
                "warning",
                "missing-risks",
                "No ## Risks section (optional, but recommended).",
            )
        )

    # --- Warnings: empty problem --------------------------------------------
    if product.has_problem_section and not (product.problem or "").strip():
        issues.append(
            Issue("warning", "empty-problem", "## Problem section is empty.")
        )

    # --- Warnings: too many requirements ------------------------------------
    if len(product.requirements) > MAX_REQUIREMENTS:
        issues.append(
            Issue(
                "warning",
                "too-many-requirements",
                f"{len(product.requirements)} requirements "
                f"(more than {MAX_REQUIREMENTS}); consider splitting the feature.",
            )
        )

    # --- Warnings: duplicate requirement text -------------------------------
    text_counts = Counter(r.text.strip().casefold() for r in product.requirements)
    seen_text: set[str] = set()
    for r in product.requirements:
        key = r.text.strip().casefold()
        if text_counts[key] > 1 and key not in seen_text:
            seen_text.add(key)
            issues.append(
                Issue(
                    "warning",
                    "duplicate-req-text",
                    f"Duplicate requirement text: {r.text!r}.",
                    r.line,
                )
            )

    # --- Warnings: ambiguous verbs ------------------------------------------
    for r in product.requirements:
        found = _AMBIGUOUS_RE.findall(r.text)
        if found:
            verbs = ", ".join(sorted({v.lower() for v in found}))
            issues.append(
                Issue(
                    "warning",
                    "ambiguous-verb",
                    f"{r.id} uses ambiguous verb(s) ({verbs}); be more specific.",
                    r.line,
                )
            )

    return issues
