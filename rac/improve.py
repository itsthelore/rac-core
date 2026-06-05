"""Artifact improvement — deterministic, schema-driven guidance (ADR-002).

`rac improve <file>` is RAC's first *advisory* capability: it reports which
required and recommended sections an artifact is missing and can emit Markdown
templates for them. It is strictly read-only (REQ-004) and generates no content
beyond schema-derived placeholders — no AI, no rewriting.

Improvement depends only on the artifact *type* and a *schema comparison*
(:func:`rac.classification.missing_sections`); it never reaches into classification
confidence internals. v0.5.0 produces suggestions for Requirement artifacts only;
other known types and Unknown return no suggestions (the renderers explain why).
"""

from __future__ import annotations

from dataclasses import dataclass

from .artifacts import spec_for
from .classification import classify, missing_sections
from .models import Product
from .parser import parse, parse_file

# The single artifact type that v0.5.0 generates suggestions for. Written as a
# constant (not hard-coded throughout) so widening scope later is a one-line change.
SUPPORTED_TYPE = "requirement"


@dataclass
class ImprovementResult:
    """Typed improvement analysis for one artifact (ADR-003).

    Section names are stored normalized (e.g. ``"success metrics"``); renderers
    format them. ``to_dict`` is the stable JSON contract (ADR-007):
    ``{type, missing_required, missing_recommended}``.
    """

    type: str  # classified artifact type, or "unknown"
    missing_required: list[str]
    missing_recommended: list[str]
    # Reserved for future Unknown handling (e.g. "closest match" guidance). Always
    # None in v0.5.0 and intentionally not serialized yet — additive later (ADR-007).
    closest_type: str | None = None

    @property
    def supported(self) -> bool:
        """True when this is a type ``improve`` generates suggestions for."""
        return self.type == SUPPORTED_TYPE

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "missing_required": [_snake(s) for s in self.missing_required],
            "missing_recommended": [_snake(s) for s in self.missing_recommended],
        }


def _snake(section: str) -> str:
    return section.replace(" ", "_")


def improve_product(product: Product) -> ImprovementResult:
    """Analyze a parsed ``product`` and return improvement guidance."""
    artifact_type = classify(product).type
    if artifact_type != SUPPORTED_TYPE:
        # Decision / other known types and Unknown: no suggestions in v0.5.0.
        return ImprovementResult(
            type=artifact_type, missing_required=[], missing_recommended=[]
        )
    spec = spec_for(SUPPORTED_TYPE)
    assert spec is not None  # the requirement spec always exists
    missing_required, missing_recommended = missing_sections(product, spec)
    return ImprovementResult(
        type=artifact_type,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
    )


def improve_text(text: str) -> ImprovementResult:
    return improve_product(parse(text))


def improve_file(path: str) -> ImprovementResult:
    return improve_product(parse_file(path))
