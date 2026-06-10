"""Artifact classification — the shared heuristic over a parsed document.

Scores a :class:`~rac.core.models.Product` against the artifact schemas in
:mod:`rac.core.artifacts` and picks the best-fit type (or Unknown). This is a pure,
AI-optional function (ADR-002): it looks only at which ``##`` sections a document
contains. It is the single home for classification, consumed by ``inspect``,
``validate``, ``stats``, and future commands so they never reach it through one
another.

Classification works off ``product.sections`` (the canonical section map from the
parser); it never re-parses the Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass

from .artifacts import ARTIFACT_SPECS, ArtifactSpec
from .models import Product

# Below this best-fit score, the document is reported as Unknown rather than
# forced into a type. Unknown is a valid, successful outcome — not an error.
CONFIDENCE_THRESHOLD = 0.5


@dataclass
class TypeScore:
    """How well a document fits one artifact type — the explainable breakdown."""

    name: str
    display: str
    matched_required: list[str]
    matched_recommended: list[str]
    missing: list[str]
    points: float  # matched_required + 0.5 * matched_recommended
    ceiling: float  # |required| + 0.5 * |recommended|
    fit: float  # points / ceiling, 0.0 – 1.0 (unrounded)


@dataclass
class Classification:
    """The chosen artifact type for a document (or Unknown)."""

    type: str  # artifact name, or "unknown"
    confidence: float  # 0.0 – 1.0 (rounded to 2dp)
    present_sections: list[str]
    missing_sections: list[str]


def _mapped(product: Product, spec: ArtifactSpec) -> set[str]:
    """The document's ``##`` headings, with this spec's synonyms applied.

    The single source of synonym-aware section matching, shared by scoring
    (:func:`score_artifacts`) and the scoring-independent :func:`missing_sections`.
    """
    return {spec.synonyms.get(h, h) for h in product.sections}


def missing_sections(product: Product, spec: ArtifactSpec) -> tuple[list[str], list[str]]:
    """Return ``(missing_required, missing_recommended)`` for ``spec``.

    Synonym-aware and in schema declaration order. Independent of confidence
    scoring (no :class:`TypeScore`) so callers like ``improve`` depend only on the
    schema, not on classification internals.
    """
    mapped = _mapped(product, spec)
    return (
        [s for s in spec.required if s not in mapped],
        [s for s in spec.recommended if s not in mapped],
    )


def score_artifacts(product: Product) -> list[TypeScore]:
    """Score the document against every artifact type, best fit first.

    Synonyms (e.g. "success criteria" -> "success metrics") are applied before
    matching, so they contribute to the score deterministically.
    """
    scores: list[TypeScore] = []
    for spec in ARTIFACT_SPECS:
        mapped = _mapped(product, spec)
        matched_required = [s for s in spec.required if s in mapped]
        matched_recommended = [s for s in spec.recommended if s in mapped]
        missing = [s for s in spec.expected if s not in mapped]
        points = len(matched_required) + 0.5 * len(matched_recommended)
        ceiling = len(spec.required) + 0.5 * len(spec.recommended)
        fit = points / ceiling if ceiling else 0.0
        scores.append(
            TypeScore(
                name=spec.name,
                display=spec.display,
                matched_required=matched_required,
                matched_recommended=matched_recommended,
                missing=missing,
                points=points,
                ceiling=ceiling,
                fit=fit,
            )
        )
    # Best fit first; ties broken by more required matches, then ARTIFACT_SPECS
    # order (stable sort preserves it).
    scores.sort(key=lambda t: (t.fit, len(t.matched_required)), reverse=True)
    return scores


def classify(product: Product) -> Classification:
    """Pick the best-fit artifact type for ``product`` (or Unknown)."""
    scores = score_artifacts(product)
    best = scores[0] if scores else None

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
