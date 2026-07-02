"""Best-fit artifact classification over a parsed document.

Given a :class:`~rac.core.models.Product`, score it against every schema in
:mod:`rac.core.artifacts` and pick the closest-fitting type, or report
``"unknown"`` when nothing fits well enough. The heuristic is deterministic and
AI-free (ADR-002): it reads only which ``##`` sections a document declares,
never their prose, so identical section sets always classify identically.

Classification stays separate from validation. A recognisable-but-broken
artifact still classifies as its type here; whether it is *valid* is decided
later by :mod:`rac.core.validation`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .artifacts import ARTIFACT_SPECS, ArtifactSpec
from .models import Product

# A best fit at or above this threshold is confident enough to name a type;
# below it the document is "unknown", which is a successful outcome, not a
# failure. Imported by rac.output.human, so the value is part of the contract.
CONFIDENCE_THRESHOLD = 0.5


@dataclass
class TypeScore:
    """One type's fit against a document, with the breakdown that explains the
    number: which sections matched and which of the expected ones are absent."""

    name: str
    display: str
    matched_required: list[str]
    matched_recommended: list[str]
    missing: list[str]
    points: float  # matched required + 0.5 per matched recommended
    ceiling: float  # the most points this spec could award
    fit: float  # points / ceiling, unrounded


@dataclass
class Classification:
    """The type chosen for a document (or ``"unknown"``).

    ``present_sections`` carries two meanings by design (relied on by
    ``inspect``): for a classified document it is the matched required +
    recommended sections; for an unknown document it is *every* section the
    document declares, so a caller can still show what was found.
    """

    type: str  # an artifact name, or "unknown"
    confidence: float  # fit rounded to 2 decimal places
    present_sections: list[str]
    missing_sections: list[str]


def _mapped(product: Product, spec: ArtifactSpec) -> set[str]:
    """The document's headings with ``spec``'s synonyms folded to canonical
    names. The single place synonyms are applied, so scoring and
    :func:`missing_sections` agree on what "present" means."""
    return {spec.synonyms.get(heading, heading) for heading in product.sections}


def _score(product: Product, spec: ArtifactSpec) -> TypeScore:
    """Score one document against one spec."""
    mapped = _mapped(product, spec)
    matched_required = [section for section in spec.required if section in mapped]
    matched_recommended = [section for section in spec.recommended if section in mapped]
    # A recommended section is worth half a required one; this weighting is what
    # the pinned numeric anchors (e.g. prompt 3-of-4 required -> 3/5.5) rely on.
    points = len(matched_required) + 0.5 * len(matched_recommended)
    ceiling = len(spec.required) + 0.5 * len(spec.recommended)
    return TypeScore(
        name=spec.name,
        display=spec.display,
        matched_required=matched_required,
        matched_recommended=matched_recommended,
        missing=[section for section in spec.expected if section not in mapped],
        points=points,
        ceiling=ceiling,
        fit=points / ceiling if ceiling else 0.0,
    )


def missing_sections(product: Product, spec: ArtifactSpec) -> tuple[list[str], list[str]]:
    """Return ``(missing_required, missing_recommended)`` for ``spec``.

    Synonym-aware and in declaration order, read straight off the schema with no
    scoring involved — callers such as ``improve`` depend only on the schema,
    not on classification internals.
    """
    mapped = _mapped(product, spec)
    return (
        [section for section in spec.required if section not in mapped],
        [section for section in spec.recommended if section not in mapped],
    )


def score_artifacts(product: Product) -> list[TypeScore]:
    """Score the document against every artifact type, best fit first."""
    scores = [_score(product, spec) for spec in ARTIFACT_SPECS]
    # Order by fit, then by number of required matches. A stable sort leaves
    # ties in ARTIFACT_SPECS order, which pins the winner when fits are equal.
    scores.sort(key=lambda score: (score.fit, len(score.matched_required)), reverse=True)
    return scores


def classify(product: Product) -> Classification:
    """Pick the best-fit artifact type for ``product``, or ``"unknown"``."""
    best = score_artifacts(product)[0] if ARTIFACT_SPECS else None

    # Unknown when nothing scored, when the best fit is below threshold, or when
    # not one required section matched — a document can only *be* a type if it
    # carries at least one of that type's defining sections.
    if best is None or best.fit < CONFIDENCE_THRESHOLD or not best.matched_required:
        return Classification(
            type="unknown",
            confidence=round(best.fit, 2) if best else 0.0,
            present_sections=list(product.sections),
            missing_sections=[],
        )

    return Classification(
        type=best.name,
        confidence=round(best.fit, 2),
        present_sections=best.matched_required + best.matched_recommended,
        missing_sections=best.missing,
    )
