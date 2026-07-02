"""Public schema reference and starter-template derivation.

``rac schema`` answers "what should this artifact look like?" without needing an
existing file. This module is the read-only projection of :mod:`rac.core.artifacts`
that the CLI, the output renderers, and the Explorer adapter consume:

* :class:`SchemaReference` is the public, list-based view of one
  :class:`~rac.core.artifacts.ArtifactSpec` (tuples become lists; ``to_dict``
  snake-cases section names for JSON).
* :class:`TemplateSection` and :func:`template_sections` derive a *structurally
  valid* starter — required and recommended sections only, each with a
  placeholder body that passes validation on its own.

The starter bodies here are byte-pinned: they are compared against the packaged
``rac/templates/*.md`` resources by the template drift guard, so any wording change
must be regenerated into those files in lockstep.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .artifacts import ARTIFACT_SPECS, ArtifactSpec, spec_for


@dataclass
class SchemaReference:
    """Public reference view of one registered artifact schema.

    Mirrors an :class:`ArtifactSpec` with lists instead of tuples so consumers can
    treat it as plain data. ``display`` is carried for human rendering but is
    deliberately absent from :meth:`to_dict` (the JSON contract exposes ``type``).
    """

    type: str
    display: str
    required: list[str]
    recommended: list[str]
    optional: list[str]
    descriptions: dict[str, str] = field(default_factory=dict)
    guidance: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-shaped view: section names snake-cased, ``display`` omitted."""
        return {
            "type": self.type,
            "required": [_snake(s) for s in self.required],
            "recommended": [_snake(s) for s in self.recommended],
            "optional": [_snake(s) for s in self.optional],
            "descriptions": {
                _snake(section): description for section, description in self.descriptions.items()
            },
            "guidance": {_snake(section): list(lines) for section, lines in self.guidance.items()},
            "metadata": {
                _snake(section): list(values) for section, values in self.metadata.items()
            },
        }


@dataclass
class TemplateSection:
    """One Markdown section of a structurally valid starter template."""

    name: str
    body: str
    guidance: list[str] = field(default_factory=list)
    metadata_values: list[str] = field(default_factory=list)


def available_schemas() -> list[str]:
    """Registered schema names, in :data:`ARTIFACT_SPECS` order."""
    return [spec.name for spec in ARTIFACT_SPECS]


def schema_reference(name: str) -> SchemaReference | None:
    """Return the public schema reference for ``name``, or ``None`` if unknown."""
    spec = spec_for(name)
    if spec is None:
        return None
    return _reference_from_spec(spec)


def template_sections(ref: SchemaReference) -> list[TemplateSection]:
    """Starter-template sections: required first, then recommended.

    Optional sections (relationship links) are omitted from the starter while
    staying visible in the human and JSON schema reference — a fresh artifact
    declares its own structure before it links out to others.
    """
    return [_template_section(ref, section) for section in ref.required + ref.recommended]


def _reference_from_spec(spec: ArtifactSpec) -> SchemaReference:
    """Copy a spec's tuple/dict data into the list-based public view."""
    return SchemaReference(
        type=spec.name,
        display=spec.display,
        required=list(spec.required),
        recommended=list(spec.recommended),
        optional=list(spec.optional),
        descriptions=dict(spec.descriptions),
        guidance={section: list(lines) for section, lines in spec.guidance.items()},
        metadata={section: list(values) for section, values in spec.metadata.items()},
    )


def _template_section(ref: SchemaReference, section: str) -> TemplateSection:
    metadata_values = ref.metadata.get(section, [])
    return TemplateSection(
        name=section,
        body=_starter_body(ref, section, metadata_values),
        guidance=list(ref.guidance.get(section, [])),
        metadata_values=list(metadata_values),
    )


def _starter_body(ref: SchemaReference, section: str, metadata_values: list[str]) -> str:
    """A placeholder body that keeps the emitted template passing validation.

    A constrained field must open on a valid enum value; the requirement's
    ``requirements`` section must carry a real ``[REQ-NNN]`` line or the artifact
    fails validation; design phrasings differ enough to warrant their own table.
    Everything else falls back to the shared free-text TODOs.
    """
    if metadata_values:
        return _metadata_default(section, metadata_values)
    if ref.type == "requirement" and section == "requirements":
        return "- [REQ-001] TODO: describe a required system behaviour."
    if ref.type == "design":
        return _design_free_text_todo(section)
    return _free_text_todo(section)


def _metadata_default(section: str, values: list[str]) -> str:
    """Pick the safe default enum value: the live/neutral one when it exists."""
    if section == "status" and "Proposed" in values:
        return "Proposed"
    if section == "category" and "Other" in values:
        return "Other"
    return values[0] if values else "TODO"


def _free_text_todo(section: str) -> str:
    """Shared placeholder prose per section, with a generic fallback."""
    messages = {
        "problem": "TODO: describe the problem being solved and who experiences it.",
        "success metrics": "TODO: describe how success will be measured.",
        "risks": ("TODO: describe implementation, delivery, operational, or adoption risks."),
        "assumptions": "TODO: describe conditions assumed to be true.",
        "outcomes": "TODO: describe the outcomes this roadmap is intended to achieve.",
        "initiatives": "TODO: describe the major initiatives that support the outcomes.",
        "success measures": "TODO: describe how progress or success will be measured.",
        "objective": "TODO: describe what this prompt is intended to achieve.",
        "input": (
            "TODO: describe the information, context, or source material the prompt expects."
        ),
        "instructions": ("TODO: describe the steps, rules, or approach the model should follow."),
        "output": "TODO: describe the expected response format or result.",
        "constraints": "TODO: describe any boundaries or restrictions.",
        "examples": "TODO: provide example inputs and outputs if useful.",
        "evaluation": "TODO: describe how the output should be judged.",
        "context": "TODO: describe the situation, constraints, and background.",
        "decision": "TODO: describe the decision that has been made.",
        "consequences": ("TODO: describe the expected positive and negative consequences."),
        "alternatives considered": (
            "TODO: describe the options that were considered and why they were not chosen."
        ),
    }
    return messages.get(section, f"TODO: describe {section}.")


def _design_free_text_todo(section: str) -> str:
    """Design-specific placeholder prose, falling back to the shared table."""
    messages = {
        "context": "TODO: describe the design context and why this design exists.",
        "user need": ("TODO: describe who this design is for and what they need to accomplish."),
        "design": (
            "TODO: describe the proposed experience, interaction, layout, flow, or system behavior."
        ),
        "constraints": (
            "TODO: describe technical, product, accessibility, platform, or "
            "implementation constraints."
        ),
        "rationale": "TODO: explain why this design approach was chosen.",
        "alternatives": "TODO: describe alternatives that were considered.",
        "accessibility": "TODO: describe accessibility considerations.",
        "style guidance": ("TODO: describe visual, tone, layout, or interaction style guidance."),
        "open questions": "TODO: list unresolved design questions.",
    }
    return messages.get(section, _free_text_todo(section))


def _snake(section: str) -> str:
    """Normalized section name -> JSON key: ``"user need"`` -> ``"user_need"``."""
    return section.replace(" ", "_")
