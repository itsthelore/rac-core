"""Artifact improvement — deterministic, schema-driven guidance (ADR-002).

`rac improve <file>` is RAC's *advisory* capability: it reports which required and
recommended sections an artifact is missing, explains *how to complete them* with
schema-defined guidance (v0.5.1), and can emit Markdown templates. It is strictly
read-only (REQ-004) and generates no content beyond schema-derived placeholders —
no AI, no rewriting.

Improvement depends only on the artifact *type* and a *schema comparison*
(:func:`rac.core.classification.missing_sections`); it never reaches into classification
confidence internals. A type is *supported* when it has an :class:`ArtifactSpec`
**and** complete guidance coverage for its expected sections — so requirement and
decision are supported today, while Unknown (and any future spec lacking guidance)
is not. Guidance is informational only: it never affects classification, validation,
or statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.artifacts import ArtifactSpec, spec_for
from rac.core.classification import classify, missing_sections
from rac.core.markdown import parse, parse_file
from rac.core.models import Product


def supports_improve(spec: ArtifactSpec) -> bool:
    """True when every expected section of ``spec`` defines guidance.

    Gates ``rac improve`` so a future artifact type cannot become improvable until
    its schema includes guidance for all required and recommended sections.
    """
    return all(section in spec.guidance for section in spec.expected)


@dataclass
class ImprovementResult:
    """Typed improvement analysis for one artifact (ADR-003).

    Section names are stored normalized (e.g. ``"success metrics"``); renderers
    format them. ``to_dict`` is the stable JSON contract (ADR-007):
    ``{type, missing_required, missing_recommended, guidance}``.
    """

    type: str  # classified artifact type, or "unknown"
    missing_required: list[str]
    missing_recommended: list[str]
    # Schema guidance for the missing sections: {section -> prompting questions}.
    guidance: dict[str, list[str]] = field(default_factory=dict)
    # Whether `improve` produces suggestions for this type (spec + full coverage).
    supported: bool = False
    # Reserved for future Unknown handling (e.g. "closest match"); not serialized.
    closest_type: str | None = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "missing_required": [_snake(s) for s in self.missing_required],
            "missing_recommended": [_snake(s) for s in self.missing_recommended],
            "guidance": {_snake(s): list(g) for s, g in self.guidance.items()},
        }


def _snake(section: str) -> str:
    return section.replace(" ", "_")


def improve_product(product: Product) -> ImprovementResult:
    """Analyze a parsed ``product`` and return improvement guidance."""
    artifact_type = classify(product).type
    spec = spec_for(artifact_type)
    if spec is None or not supports_improve(spec):
        # Unknown, or a known type whose schema lacks complete guidance.
        return ImprovementResult(
            type=artifact_type,
            missing_required=[],
            missing_recommended=[],
            supported=False,
        )
    missing_required, missing_recommended = missing_sections(product, spec)
    guidance = {
        s: list(spec.guidance[s])
        for s in missing_required + missing_recommended
        if spec.guidance.get(s)
    }
    return ImprovementResult(
        type=artifact_type,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
        guidance=guidance,
        supported=True,
    )


def improve_text(text: str) -> ImprovementResult:
    return improve_product(parse(text))


def improve_file(path: str) -> ImprovementResult:
    return improve_product(parse_file(path))
