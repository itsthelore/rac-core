"""Advisory, schema-driven completion guidance (`rac improve`).

`rac improve <file>` reports which required and recommended sections an artifact
is missing and, for each, the schema-defined questions that guide filling it in.
It is strictly read-only (REQ-004) and deterministic (ADR-002): no AI, no
rewriting, no content generated beyond schema-derived placeholders.

Guidance depends only on the artifact *type* and a *schema comparison*
(:func:`rac.core.classification.missing_sections`) — never on classification
internals, and it never feeds back into classification, validation, or
statistics. A type earns support purely through its :class:`ArtifactSpec`: it
must define guidance for every expected section (:func:`supports_improve`).
There is no per-type engine — the same pipeline serves every artifact family,
which is why a new type becomes improvable the moment its spec gains complete
guidance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.artifacts import ArtifactSpec, spec_for
from rac.core.classification import classify, missing_sections
from rac.core.markdown import parse, parse_file
from rac.core.models import Product


def supports_improve(spec: ArtifactSpec) -> bool:
    """True when ``spec`` defines guidance for every section it expects.

    This gate is what makes support spec-driven rather than hard-coded: a future
    type cannot become improvable until its schema covers all of its required
    and recommended sections.
    """
    return all(section in spec.guidance for section in spec.expected)


def _snake(section: str) -> str:
    return section.replace(" ", "_")


@dataclass
class ImprovementResult:
    """Typed improvement analysis for one artifact (ADR-003).

    Section names are stored in their normalized form (e.g. ``"success
    metrics"``); renderers do the casing. ``to_dict`` is the stable JSON
    contract (ADR-007): ``{type, missing_required, missing_recommended,
    guidance}`` with snake-cased section names.
    """

    type: str  # classified type, or "unknown"
    missing_required: list[str]
    missing_recommended: list[str]
    # Guidance questions for each missing section: {section -> questions}.
    guidance: dict[str, list[str]] = field(default_factory=dict)
    # Whether this type yields suggestions at all (spec present + full coverage).
    supported: bool = False
    # Reserved for future unknown-type handling (e.g. nearest match); not serialized.
    closest_type: str | None = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "missing_required": [_snake(s) for s in self.missing_required],
            "missing_recommended": [_snake(s) for s in self.missing_recommended],
            "guidance": {_snake(s): list(questions) for s, questions in self.guidance.items()},
        }


def improve_product(product: Product) -> ImprovementResult:
    """Analyze a parsed ``product`` and return its completion guidance."""
    artifact_type = classify(product).type
    spec = spec_for(artifact_type)
    if spec is None or not supports_improve(spec):
        # Unknown, or a known type whose schema lacks complete guidance: there is
        # nothing actionable to report.
        return ImprovementResult(
            type=artifact_type,
            missing_required=[],
            missing_recommended=[],
            supported=False,
        )

    missing_required, missing_recommended = missing_sections(product, spec)
    # Keep required sections ahead of recommended so renderers preserve priority.
    guidance = {
        section: list(spec.guidance[section])
        for section in missing_required + missing_recommended
        if spec.guidance.get(section)
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
