"""Schema reference service — expose registered artifact schemas directly.

`rac schema` answers "what should this artifact look like?" without requiring an
existing file. It consumes :mod:`rac.artifacts` as the single source of truth and
derives human/JSON/template data from registered :class:`ArtifactSpec` objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .artifacts import ARTIFACT_SPECS, ArtifactSpec, spec_for


@dataclass
class SchemaReference:
    """Public reference view for one registered artifact schema."""

    type: str
    display: str
    required: list[str]
    recommended: list[str]
    optional: list[str]
    descriptions: dict[str, str] = field(default_factory=dict)
    guidance: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "required": [_snake(s) for s in self.required],
            "recommended": [_snake(s) for s in self.recommended],
            "optional": [_snake(s) for s in self.optional],
            "descriptions": {
                _snake(section): description
                for section, description in self.descriptions.items()
            },
            "guidance": {
                _snake(section): list(lines)
                for section, lines in self.guidance.items()
            },
            "metadata": {
                _snake(section): list(values)
                for section, values in self.metadata.items()
            },
        }


@dataclass
class TemplateSection:
    """One Markdown section in a structurally valid starter template."""

    name: str
    body: str
    guidance: list[str] = field(default_factory=list)
    metadata_values: list[str] = field(default_factory=list)


def available_schemas() -> list[str]:
    """Registered schema names, in :data:`ARTIFACT_SPECS` order."""
    return [spec.name for spec in ARTIFACT_SPECS]


def schema_reference(name: str) -> SchemaReference | None:
    """Return a public schema reference for ``name``, or None if unknown."""
    spec = spec_for(name)
    if spec is None:
        return None
    return _reference_from_spec(spec)


def template_sections(ref: SchemaReference) -> list[TemplateSection]:
    """Full starter template sections: required first, then recommended.

    Optional sections are intentionally omitted from the starter, while remaining
    visible in the human and JSON schema reference.
    """
    return [_template_section(ref, section) for section in ref.required + ref.recommended]


def _reference_from_spec(spec: ArtifactSpec) -> SchemaReference:
    return SchemaReference(
        type=spec.name,
        display=spec.display,
        required=list(spec.required),
        recommended=list(spec.recommended),
        optional=list(spec.optional),
        descriptions=dict(spec.descriptions),
        guidance={
            section: list(lines)
            for section, lines in spec.guidance.items()
        },
        metadata={
            section: list(values)
            for section, values in spec.metadata.items()
        },
    )


def _template_section(ref: SchemaReference, section: str) -> TemplateSection:
    metadata_values = ref.metadata.get(section, [])
    return TemplateSection(
        name=section,
        body=_starter_body(ref, section, metadata_values),
        guidance=list(ref.guidance.get(section, [])),
        metadata_values=list(metadata_values),
    )


def _starter_body(
    ref: SchemaReference, section: str, metadata_values: list[str]
) -> str:
    """Validation-safe starter body for one section."""
    if metadata_values:
        return _metadata_default(section, metadata_values)
    if ref.type == "requirement" and section == "requirements":
        return "- [REQ-001] TODO: describe a required system behaviour."
    return _free_text_todo(section)


def _metadata_default(section: str, values: list[str]) -> str:
    if section == "status" and "Proposed" in values:
        return "Proposed"
    if section == "category" and "Other" in values:
        return "Other"
    return values[0] if values else "TODO"


def _free_text_todo(section: str) -> str:
    messages = {
        "problem": "TODO: describe the problem being solved and who experiences it.",
        "success metrics": "TODO: describe how success will be measured.",
        "risks": (
            "TODO: describe implementation, delivery, operational, "
            "or adoption risks."
        ),
        "assumptions": "TODO: describe conditions assumed to be true.",
        "context": "TODO: describe the situation, constraints, and background.",
        "decision": "TODO: describe the decision that has been made.",
        "consequences": (
            "TODO: describe the expected positive and negative consequences."
        ),
        "alternatives considered": (
            "TODO: describe the options that were considered and why they "
            "were not chosen."
        ),
    }
    return messages.get(section, f"TODO: describe {section}.")


def _snake(section: str) -> str:
    return section.replace(" ", "_")
