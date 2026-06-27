"""Validate a :class:`~rac.core.models.Product` against RAC's format rules.

Returns a flat list of :class:`~rac.core.models.Issue` objects (errors and warnings);
it never stops at the first problem. Whether a run "fails" is the CLI's decision,
based on whether any ``error``-severity issues are present.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from typing import Literal

from .artifacts import ArtifactSpec, spec_for
from .classification import classify
from .identity import identity_conflict
from .models import Issue, Product, Requirement

# A file with more requirements than this earns a (non-failing) warning.
MAX_REQUIREMENTS = 50

# Vague verbs that tend to hide unspecified behavior.
AMBIGUOUS_VERBS = ("support", "handle", "allow", "enable")
_AMBIGUOUS_RE = re.compile(r"\b(" + "|".join(AMBIGUOUS_VERBS) + r")\b", re.IGNORECASE)

# Requirements quality standards (v0.17.1, ADR-056). The normative requirement
# verbs RAC disciplines; per RFC 8174 only their ALL-CAPS form carries normative
# weight, so a non-uppercase occurrence inside a requirement line is ambiguous.
_NORMATIVE_RE = re.compile(r"\b(shall|must|should)\b", re.IGNORECASE)
_EARS_IF_RE = re.compile(r"^\s*if\b", re.IGNORECASE)
_THEN_RE = re.compile(r"\bthen\b", re.IGNORECASE)
# Roadmap horizon (ADR-056): now/next/later or a calendar quarter (e.g. Q3 2026).
_HORIZON_VALUES = ("now", "next", "later")
_QUARTER_RE = re.compile(r"^Q[1-4]\s+\d{4}$")

# External ticketing format-lint (ADR-087). ``## Related Tickets`` carries
# external ticket identifiers, not artifact references; each entry must be a
# well-formed key or URL for the repository's configured provider (ADR-088).
# Pure and offline — the engine never contacts the ticketing system; existence
# and state checks are a satellite's job (ADR-090). The provider is resolved from
# ``.rac/config.yaml`` by the services layer and passed into ``validate``; core
# stays config-free. Organisations standardise on one provider, so exactly one
# validator is ever active per repository.
MALFORMED_TICKET_REFERENCE = "malformed-ticket-reference"
TICKETING_SECTION = "related tickets"  # normalized ## Related Tickets

_TICKET_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")
_URL_RE = re.compile(r"^https?://\S+$")
_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_LINEAR_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_GITHUB_REF_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+$")
_ADO_REF_RE = re.compile(r"^(?:AB#)?\d+$")
_SERVICENOW_RE = re.compile(r"^[A-Z]{2,}\d{5,}$")


def _ticket_validator(pattern: re.Pattern[str]) -> Callable[[str], bool]:
    """An entry validator accepting ``pattern`` or any http(s) URL."""

    def is_valid(entry: str) -> bool:
        return bool(_URL_RE.match(entry) or pattern.match(entry))

    return is_valid


# Per ticketing provider: (entry validator, human label for the diagnostic). The
# key set is the recognised provider vocabulary; ``none`` (no provider) skips the
# format-lint entirely. Adding a provider is a code change here, not a new ADR.
TICKETING_PROVIDERS: dict[str, tuple[Callable[[str], bool], str]] = {
    "jira": (_ticket_validator(_JIRA_KEY_RE), "Jira key (e.g. PROJ-1234) or URL"),
    "github": (_ticket_validator(_GITHUB_REF_RE), "GitHub issue (e.g. owner/repo#123) or URL"),
    "linear": (_ticket_validator(_LINEAR_KEY_RE), "Linear key (e.g. ENG-123) or URL"),
    "azure-devops": (
        _ticket_validator(_ADO_REF_RE),
        "Azure DevOps work item (e.g. 1234 or AB#1234) or URL",
    ),
    "servicenow": (_ticket_validator(_SERVICENOW_RE), "ServiceNow record (e.g. INC0010023) or URL"),
}

# The recognised provider names, plus ``none`` — the config layer validates a
# ticketing.provider value against this set (ADR-088).
TICKETING_PROVIDER_NAMES: tuple[str, ...] = (*TICKETING_PROVIDERS, "none")


def has_errors(issues: list[Issue]) -> bool:
    """True if any issue is error-severity."""
    return any(issue.severity == "error" for issue in issues)


def validate(product: Product, *, ticketing_provider: str | None = None) -> list[Issue]:
    """Check ``product`` and return all structural and quality findings.

    Dispatches on artifact type. Each type with its own schema is routed
    explicitly; the final ``_validate_requirement`` arm is a
    backwards-compatibility fallback for Unknown/legacy documents (and RAC's
    original Requirement rules), *not* the long-term model — new artifact types
    must be routed explicitly above it.

    ``ticketing_provider`` enables the external ticket format-lint (ADR-087): when
    set to a recognised provider, ``## Related Tickets`` entries are checked
    against that provider's key/URL format. It defaults to ``None`` so the many
    pure ``validate(product)`` callers are unaffected; the config-aware service
    layer injects the repository's configured provider (ADR-088). Stays
    deterministic — a pure function of ``(product, ticketing_provider)``.
    """
    issues = _validate_metadata(product)
    issues += _validate_ticketing_references(product, ticketing_provider)
    artifact_type = classify(product).type
    if artifact_type == "decision":
        return issues + _validate_decision(product)
    if artifact_type == "roadmap":
        return issues + _validate_roadmap(product)
    if artifact_type == "prompt":
        return issues + _validate_prompt(product)
    if artifact_type == "design":
        return issues + _validate_design(product)
    if artifact_type == "requirement":
        spec = spec_for("requirement")
        assert spec is not None  # the requirement spec always exists
        return (
            issues
            + _validate_requirement(product)
            + _validate_status_metadata(product, spec)
            + _validate_requirement_standards(product)
        )
    # Unknown/legacy fallback: requirement rules only, no constrained metadata or
    # per-type standards (an Unknown document is not linted as a requirement).
    return issues + _validate_requirement(product)


def _validate_requirement_standards(product: Product) -> list[Issue]:
    """Per-line requirement quality checks: BCP-14, 29148 singular, EARS (ADR-056).

    Deterministic and decidable by parsing — no prose judgement (ADR-002). BCP-14
    keyword discipline is an error inside ``requirement`` artifacts; the 29148/EARS
    checks are warnings (legacy requirements will not comply), all overridable per
    ADR-053. Each diagnostic names the standard and the fix.
    """
    issues: list[Issue] = []
    for r in product.requirements:
        keywords = _NORMATIVE_RE.findall(r.text)

        # BCP-14: only ALL-CAPS normative keywords carry weight (RFC 8174); a
        # lowercase/mixed-case shall/must/should is ambiguous normative language.
        ambiguous = sorted({k for k in keywords if k != k.upper()})
        if ambiguous:
            issues.append(
                Issue(
                    "error",
                    "requirement-normative-keyword",
                    f"{r.id} uses non-normative {', '.join(ambiguous)!r}; only "
                    "uppercase MUST/SHALL/SHOULD/MAY carry normative weight (BCP 14).",
                    r.line,
                )
            )

        # 29148 well-formed: a requirement should be singular — one normative
        # statement per line.
        if len(keywords) > 1:
            issues.append(
                Issue(
                    "warning",
                    "requirement-not-singular",
                    f"{r.id} has {len(keywords)} normative keywords; a requirement "
                    "should be singular (ISO/IEC/IEEE 29148).",
                    r.line,
                )
            )

        # EARS: a requirement must state a normative response; a sentence-initial
        # "If" (unwanted-behaviour pattern) needs a "then" response clause.
        if not keywords:
            issues.append(
                Issue(
                    "warning",
                    "requirement-non-ears",
                    f"{r.id} has no normative keyword (SHALL/SHOULD/MAY); it does not "
                    "state a testable requirement (EARS).",
                    r.line,
                )
            )
        elif _EARS_IF_RE.search(r.text) and not _THEN_RE.search(r.text):
            issues.append(
                Issue(
                    "warning",
                    "requirement-ears-clause",
                    f"{r.id} opens with 'If' but has no 'then' response clause "
                    "(EARS unwanted-behaviour pattern: If <condition> then <system> SHALL …).",
                    r.line,
                )
            )
    return issues


def _validate_status_metadata(product: Product, spec: ArtifactSpec) -> list[Issue]:
    """Constrained metadata: a present value must be in the type's allowed set.

    Generalised across all artifact types (ADR-051): a missing section is fine —
    metadata is optional. The issue code is per-type (``invalid-<type>-<field>``)
    so ``invalid-decision-status`` is unchanged (ADR-007) and other types gain
    their own codes.
    """
    issues: list[Issue] = []
    for field_name, allowed in spec.metadata.items():
        body = product.sections.get(field_name, "")
        value = _first_value(body)
        if value and not any(value.casefold() == a.casefold() for a in allowed):
            issues.append(
                Issue(
                    "error",
                    f"invalid-{spec.name}-{field_name}",
                    f"## {field_name.title()} value {value!r} is not one of: {', '.join(allowed)}.",
                )
            )
    return issues


def _validate_metadata(product: Product) -> list[Issue]:
    """Frontmatter envelope findings (ADR-025/026, v0.7.11).

    Parse and schema issues come from the parser; the identity conflict check
    (frontmatter ``id`` vs a differing legacy ``## ID`` / ``spec.id_field``
    declaration) is detected here because it needs the classified spec. RAC
    never silently picks one identity (Initiative 7).
    """
    issues = list(product.metadata_issues) + list(product.parse_issues)
    spec = spec_for(classify(product).type)
    conflict = identity_conflict(product, spec)
    if conflict is not None:
        frontmatter_id, legacy_id = conflict
        issues.append(
            Issue(
                "error",
                "conflicting-identity",
                f"frontmatter id {frontmatter_id!r} conflicts with declared "
                f"legacy identity {legacy_id!r}; align them — RAC will not "
                "choose one",
            )
        )
    return issues


def _validate_ticketing_references(product: Product, provider: str | None) -> list[Issue]:
    """Format-lint ``## Related Tickets`` against the configured provider (ADR-087).

    Each entry must be a well-formed key or URL for the repository's ticketing
    provider. A pure, offline syntax check — the engine never contacts the
    ticketing system; existence and state checks live in a satellite (ADR-090).
    No provider (``None`` or ``"none"``) means no lint: the edge still works, it
    is simply unvalidated. Only an artifact type that declares the section is
    linted. Overridable per ADR-053 like any rule.
    """
    if not provider or provider == "none":
        return []
    rule = TICKETING_PROVIDERS.get(provider)
    if rule is None:
        return []  # the config layer validates the name; be lenient here
    spec = spec_for(classify(product).type)
    if spec is None or TICKETING_SECTION not in spec.optional:
        return []
    is_valid, label = rule
    issues: list[Issue] = []
    for line in product.sections.get(TICKETING_SECTION, "").splitlines():
        entry = _TICKET_LIST_MARKER_RE.sub("", line.strip(), count=1).strip()
        if entry and not is_valid(entry):
            issues.append(
                Issue(
                    "error",
                    MALFORMED_TICKET_REFERENCE,
                    f"## Related Tickets entry {entry!r} is not a valid {label}.",
                )
            )
    return issues


def _first_value(body: str) -> str:
    """First non-empty line of a section body (single-value metadata)."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _validate_title(product: Product) -> list[Issue]:
    """Title structure shared by every artifact type: exactly one ``#`` title.

    A missing top-level title is an error; so is more than one. The same rule
    applies to every artifact type, so all validators share this check.
    """
    issues: list[Issue] = []
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
    return issues


def _validate_required_sections(product: Product, spec: ArtifactSpec) -> list[Issue]:
    """Each of the type's required sections must be present (ADR format).

    The issue code spells multi-word section names with hyphens
    (``missing-user-need``); for single-word sections this is a no-op, so the
    codes are unchanged for types whose required sections are all single words.
    The human label is the artifact type's display name.
    """
    issues: list[Issue] = []
    for section in spec.required:
        if section not in product.sections:
            issues.append(
                Issue(
                    "error",
                    f"missing-{section.replace(' ', '-')}",
                    f"{spec.name.title()} is missing a ## {section.title()} section.",
                )
            )
    return issues


def _validate_decision(product: Product) -> list[Issue]:
    """Validate a Decision artifact (REQ-001/002/006/007).

    Missing metadata never fails (it is optional); only *invalid values* are
    errors. Required sections (Context, Decision, Consequences) must be present.
    """
    spec = spec_for("decision")
    assert spec is not None  # the decision spec always exists
    issues = _validate_title(product)
    issues += _validate_required_sections(product, spec)

    # Constrained metadata (status, category): a present value must be in the
    # allowed set. A missing section is fine — metadata is optional (REQ-007).
    issues += _validate_status_metadata(product, spec)

    return issues


def _validate_roadmap(product: Product) -> list[Issue]:
    """Validate a Roadmap artifact (REQ-003).

    Required sections (Outcomes, Initiatives) must be present; missing recommended
    sections never fail. Status is an optional, validated lifecycle field
    (ADR-051: Planned/Superseded/Abandoned) — knowledge currency, never work or
    delivery state (ADR-017).
    """
    spec = spec_for("roadmap")
    assert spec is not None  # the roadmap spec always exists
    issues = _validate_title(product)
    issues += _validate_required_sections(product, spec)

    # Horizon (v0.17.1, ADR-056): optional, validated when present — now/next/later
    # or a calendar quarter. Absent is fine (no horizon is forced on a roadmap).
    horizon = _first_value(product.sections.get("horizon", ""))
    if horizon and horizon.casefold() not in _HORIZON_VALUES and not _QUARTER_RE.match(horizon):
        issues.append(
            Issue(
                "error",
                "invalid-roadmap-horizon",
                f"## Horizon value {horizon!r} is not one of: now, next, later, "
                "or a quarter (e.g. Q3 2026).",
            )
        )

    # Linkage (warning): a roadmap should advance at least one requirement or
    # decision it links to (the edge into the graph is the roadmap's value).
    if (
        "related requirements" not in product.sections
        and "related decisions" not in product.sections
    ):
        issues.append(
            Issue(
                "warning",
                "roadmap-no-advancement-link",
                "Roadmap links no ## Related Requirements or ## Related Decisions it advances.",
            )
        )

    issues += _validate_status_metadata(product, spec)
    return issues


def _validate_prompt(product: Product) -> list[Issue]:
    """Validate a Prompt artifact (REQ-006).

    Required sections (Objective, Input, Instructions, Output) must be present;
    missing recommended/optional sections never fail or warn. Status is an
    optional, validated lifecycle field (ADR-051: Active/Deprecated); prompts are
    never executed (REQ-011) — RAC treats them as knowledge.

    Section presence is checked against the raw headings, consistent with the
    Decision and Roadmap validators; the Prompt spec's synonyms are a
    classification aid only, so validation still expects the canonical headings.
    """
    spec = spec_for("prompt")
    assert spec is not None  # the prompt spec always exists
    issues = _validate_title(product)
    issues += _validate_required_sections(product, spec)

    issues += _validate_status_metadata(product, spec)
    return issues


def _validate_design(product: Product) -> list[Issue]:
    """Validate a Design artifact (v0.6.3).

    Required sections (Context, User Need, Design, Constraints) must be present;
    missing recommended/optional sections never fail or warn. Status is an
    optional, validated lifecycle field (ADR-051); designs are knowledge
    artifacts, not UI renderings or component systems.
    """
    spec = spec_for("design")
    assert spec is not None  # the design spec always exists
    issues = _validate_title(product)
    issues += _validate_required_sections(product, spec)

    issues += _validate_status_metadata(product, spec)
    return issues


def _report_duplicates(
    requirements: list[Requirement],
    *,
    key: Callable[[Requirement], str],
    severity: Literal["error", "warning"],
    code: str,
    message: Callable[[Requirement, int], str],
) -> list[Issue]:
    """One issue per requirement whose ``key`` collides with another's.

    The issue is reported at the first offending occurrence of each duplicated
    key, in document order, so each duplicate group is named exactly once.
    ``message`` receives the offending requirement and its occurrence count.
    """
    counts = Counter(key(r) for r in requirements)
    seen: set[str] = set()
    issues: list[Issue] = []
    for r in requirements:
        k = key(r)
        if counts[k] > 1 and k not in seen:
            seen.add(k)
            issues.append(Issue(severity, code, message(r, counts[k]), r.line))
    return issues


def _malformed_requirement_issues(product: Product) -> list[Issue]:
    """Hard failures for requirement lines that are not a well-formed [REQ-NNN].

    One issue per malformed line, in document order: a missing ID, an empty
    description, or a bracket ID that is not the canonical ``REQ-NNN`` shape.
    """
    issues: list[Issue] = []
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
    return issues


def _requirement_warning_issues(product: Product) -> list[Issue]:
    """Non-failing requirement findings, in report order.

    Missing optional sections, an empty problem, excess volume, duplicate
    requirement text, then ambiguous verbs. All warnings — they never fail a
    run, but they are the findings most requirement rules accrete to, so they
    live here rather than inflating :func:`_validate_requirement`.
    """
    issues: list[Issue] = []

    # Missing optional sections.
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

    # Empty problem.
    if product.has_problem_section and not (product.problem or "").strip():
        issues.append(Issue("warning", "empty-problem", "## Problem section is empty."))

    # Too many requirements.
    if len(product.requirements) > MAX_REQUIREMENTS:
        issues.append(
            Issue(
                "warning",
                "too-many-requirements",
                f"{len(product.requirements)} requirements "
                f"(more than {MAX_REQUIREMENTS}); consider splitting the feature.",
            )
        )

    # Duplicate requirement text.
    issues += _report_duplicates(
        product.requirements,
        key=lambda r: r.text.strip().casefold(),
        severity="warning",
        code="duplicate-req-text",
        message=lambda r, n: f"Duplicate requirement text: {r.text!r}.",
    )

    issues += _ambiguous_verb_issues(product)
    return issues


def _ambiguous_verb_issues(product: Product) -> list[Issue]:
    """Warn on vague verbs (support/handle/allow/enable) that hide behavior.

    One warning per requirement line that uses any, naming the verbs found.
    """
    issues: list[Issue] = []
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


def _validate_requirement(product: Product) -> list[Issue]:
    """Check ``product`` and return all structural and quality findings.

    Hard failures first (title, required sections, malformed lines, duplicate
    IDs), then non-failing warnings. The malformed-line and warning clusters
    live in helpers so this validator — the one most new requirement rules
    accrete to — stays flat as the rule set grows. Findings are appended in a
    fixed order so the report is deterministic.
    """
    issues = _validate_title(product)

    if not product.has_problem_section:
        issues.append(Issue("error", "missing-problem", "File is missing a ## Problem section."))
    if not product.has_requirements_section:
        issues.append(
            Issue("error", "missing-requirements", "File is missing a ## Requirements section.")
        )

    issues += _malformed_requirement_issues(product)
    issues += _report_duplicates(
        product.requirements,
        key=lambda r: r.id,
        severity="error",
        code="duplicate-req-id",
        message=lambda r, n: f"Duplicate requirement ID {r.id} (used {n} times).",
    )
    issues += _requirement_warning_issues(product)
    return issues
