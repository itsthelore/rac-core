"""Deterministic intent analysis of repository comparisons (v0.12.1).

``analyze_intent`` consumes a :class:`~rac.services.compare.RepositoryComparison`
and reports changes that reduce product clarity: measurable requirements
becoming vague, mandatory language weakening, ambiguous wording arriving,
acceptance criteria or success measures disappearing, relationship impact,
and new scope without supporting context.

Every check is a pure, explainable function of the two repository states —
token-boundary text matching and parsed-section comparison, no semantic
scoring (ADR-015). Findings flag changes for human attention; they never
judge correctness. Codes reuse the policy vocabulary of the Product Intent
CI requirement so downstream policy needs no translation layer.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from rac.core.models import Product
from rac.services.compare import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    ArtifactChange,
    RepositoryComparison,
    RepoState,
)

# Stable finding codes (part of the watchkeeper JSON contract, ADR-007).
SPECIFICITY_REGRESSION = "specificity_regression"
AMBIGUITY_INTRODUCED = "ambiguity_introduced"
CONSTRAINT_WEAKENED = "constraint_weakened"
CONSTRAINT_REMOVED = "constraint_removed"
ACCEPTANCE_CRITERIA_REMOVED = "acceptance_criteria_removed"
SUCCESS_MEASURES_REMOVED = "success_measures_removed"
RELATIONSHIP_IMPACT = "relationship_impact"
UNLINKED_SCOPE = "unlinked_scope"

SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

# Pinned by the v0.12.1 implementation contract; changing the vocabulary is
# a corpus edit (roadmap/decision), not a code tweak.
AMBIGUITY_TERMS = frozenset(
    {
        "easy",
        "intuitive",
        "simple",
        "seamless",
        "user-friendly",
        "scalable",
        "fast",
        "quickly",
        "robust",
        "flexible",
    }
)
MANDATORY_TERMS = ("must", "shall")
HEDGE_TERMS = ("should", "may", "could")

# Normalized section headings (Product.sections keys are casefolded).
_ACCEPTANCE_SECTIONS = ("acceptance criteria",)
_SUCCESS_SECTIONS = ("success measures", "success metrics")


@dataclass(frozen=True)
class IntentFinding:
    """One deterministic intent finding about a compared change."""

    code: str
    severity: str  # SEVERITY_WARNING | SEVERITY_INFO
    path: str  # corpus-relative artifact path (head side; base side for removals)
    identifier: str | None  # artifact id
    detail: str  # one deterministic human sentence
    evidence: tuple[str, ...]  # the triggering text, diff-style where applicable


def _has_token(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text, re.IGNORECASE) is not None


def _ambiguous_terms(text: str) -> list[str]:
    return sorted(term for term in AMBIGUITY_TERMS if _has_token(text, term))


def _has_digit(text: str) -> bool:
    return re.search(r"\d", text) is not None


def _has_mandatory(text: str) -> bool:
    return any(_has_token(text, term) for term in MANDATORY_TERMS)


def _has_hedge(text: str) -> bool:
    return any(_has_token(text, term) for term in HEDGE_TERMS)


def _section_filled(product: Product, headings: tuple[str, ...]) -> bool:
    return any(product.sections.get(heading, "").strip() for heading in headings)


def _modified_findings(change: ArtifactChange, base: Product, head: Product) -> list[IntentFinding]:
    findings: list[IntentFinding] = []

    for req_change in change.diff.modified_requirements if change.diff else []:
        evidence = (f"- {req_change.old_text}", f"+ {req_change.new_text}")
        if _has_digit(req_change.old_text) and not _has_digit(req_change.new_text):
            findings.append(
                IntentFinding(
                    code=SPECIFICITY_REGRESSION,
                    severity=SEVERITY_WARNING,
                    path=change.path,
                    identifier=change.id,
                    detail=f"Measurable requirement {req_change.id} became vague.",
                    evidence=evidence,
                )
            )
        new_terms = [
            term
            for term in _ambiguous_terms(req_change.new_text)
            if not _has_token(req_change.old_text, term)
        ]
        if new_terms:
            joined = ", ".join(f"'{term}'" for term in new_terms)
            findings.append(
                IntentFinding(
                    code=AMBIGUITY_INTRODUCED,
                    severity=SEVERITY_WARNING,
                    path=change.path,
                    identifier=change.id,
                    detail=f"Ambiguous wording introduced in {req_change.id}: {joined}.",
                    evidence=evidence,
                )
            )
        if (
            _has_mandatory(req_change.old_text)
            and not _has_mandatory(req_change.new_text)
            and _has_hedge(req_change.new_text)
        ):
            findings.append(
                IntentFinding(
                    code=CONSTRAINT_WEAKENED,
                    severity=SEVERITY_WARNING,
                    path=change.path,
                    identifier=change.id,
                    detail=f"Mandatory requirement {req_change.id} weakened to hedged wording.",
                    evidence=evidence,
                )
            )

    for removed in change.diff.removed_requirements if change.diff else []:
        if _has_mandatory(removed.text):
            findings.append(
                IntentFinding(
                    code=CONSTRAINT_REMOVED,
                    severity=SEVERITY_WARNING,
                    path=change.path,
                    identifier=change.id,
                    detail=f"Requirement {removed.id} with mandatory wording removed.",
                    evidence=(f"- {removed.text}",),
                )
            )

    if _section_filled(base, _ACCEPTANCE_SECTIONS) and not _section_filled(
        head, _ACCEPTANCE_SECTIONS
    ):
        findings.append(
            IntentFinding(
                code=ACCEPTANCE_CRITERIA_REMOVED,
                severity=SEVERITY_WARNING,
                path=change.path,
                identifier=change.id,
                detail="Acceptance criteria section removed.",
                evidence=(),
            )
        )
    if _section_filled(base, _SUCCESS_SECTIONS) and not _section_filled(head, _SUCCESS_SECTIONS):
        findings.append(
            IntentFinding(
                code=SUCCESS_MEASURES_REMOVED,
                severity=SEVERITY_WARNING,
                path=change.path,
                identifier=change.id,
                detail="Success measures section removed.",
                evidence=(),
            )
        )

    return findings


def _removed_findings(change: ArtifactChange, base: RepoState) -> list[IntentFinding]:
    findings: list[IntentFinding] = []
    product = base.products.get(change.path)
    for requirement in product.requirements if product else []:
        if _has_mandatory(requirement.text):
            findings.append(
                IntentFinding(
                    code=CONSTRAINT_REMOVED,
                    severity=SEVERITY_WARNING,
                    path=change.path,
                    identifier=change.id,
                    detail=f"Requirement {requirement.id} with mandatory wording removed.",
                    evidence=(f"- {requirement.text}",),
                )
            )
    return findings


def _added_findings(change: ArtifactChange, head: RepoState) -> list[IntentFinding]:
    findings: list[IntentFinding] = []
    product = head.products.get(change.path)
    for requirement in product.requirements if product else []:
        terms = _ambiguous_terms(requirement.text)
        if terms:
            joined = ", ".join(f"'{term}'" for term in terms)
            findings.append(
                IntentFinding(
                    code=AMBIGUITY_INTRODUCED,
                    severity=SEVERITY_WARNING,
                    path=change.path,
                    identifier=change.id,
                    detail=f"Ambiguous wording introduced in {requirement.id}: {joined}.",
                    evidence=(f"+ {requirement.text}",),
                )
            )
    return findings


def _reference_maps(state: RepoState) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    """Incoming references (target path -> source ids) and declared targets."""
    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, set[str]] = {}
    for relationship in state.repository.relationships:
        source_rel = _rel(state, relationship.source_path)
        outgoing.setdefault(source_rel, set()).add(relationship.target)
        if relationship.resolved_path is not None:
            target_rel = _rel(state, relationship.resolved_path)
            source = state.artifacts.get(source_rel)
            incoming.setdefault(target_rel, []).append(
                source.id if source is not None else source_rel
            )
    return incoming, outgoing


def _rel(state: RepoState, path: str) -> str:
    return os.path.relpath(path, state.directory).replace(os.sep, "/")


def _impact_finding(
    change: ArtifactChange, incoming: dict[str, list[str]], verb: str
) -> IntentFinding | None:
    sources = sorted(set(incoming.get(change.path, [])))
    if not sources:
        return None
    return IntentFinding(
        code=RELATIONSHIP_IMPACT,
        severity=SEVERITY_INFO,
        path=change.path,
        identifier=change.id,
        detail=f"{verb} artifact is referenced by {len(sources)} artifact(s).",
        evidence=tuple(sources),
    )


def analyze_intent(comparison: RepositoryComparison) -> list[IntentFinding]:
    """Deterministic, stably ordered intent findings for ``comparison``."""
    findings: list[IntentFinding] = []
    base_incoming, _ = _reference_maps(comparison.base)
    head_incoming, head_outgoing = _reference_maps(comparison.head)

    for change in comparison.changes:
        if change.change == CHANGE_MODIFIED:
            base_product = comparison.base.products.get(change.path)
            head_product = comparison.head.products.get(change.path)
            if base_product is not None and head_product is not None:
                findings.extend(_modified_findings(change, base_product, head_product))
            impact = _impact_finding(change, head_incoming, "Modified")
            if impact is not None:
                findings.append(impact)
        elif change.change == CHANGE_REMOVED:
            findings.extend(_removed_findings(change, comparison.base))
            impact = _impact_finding(change, base_incoming, "Removed")
            if impact is not None:
                findings.append(impact)
        elif change.change == CHANGE_ADDED:
            findings.extend(_added_findings(change, comparison.head))
            if (
                change.type != "unknown"
                and not head_outgoing.get(change.path)
                and not head_incoming.get(change.path)
            ):
                findings.append(
                    IntentFinding(
                        code=UNLINKED_SCOPE,
                        severity=SEVERITY_WARNING,
                        path=change.path,
                        identifier=change.id,
                        detail=(
                            "New artifact declares no relationships and nothing references it."
                        ),
                        evidence=(),
                    )
                )

    findings.sort(key=lambda f: (f.severity != SEVERITY_WARNING, f.code, f.path, f.detail))
    return findings
