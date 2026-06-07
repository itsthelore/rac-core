"""Markdown template rendering for RAC command results.

Starter templates for missing sections (``rac improve --template``) and full
artifact scaffolds (``rac schema --template``). Templates are deterministic,
schema-derived Markdown — never AI-generated content (ADR-002).
"""

from __future__ import annotations

from rac.core.schema import SchemaReference, template_sections
from rac.services.improve import ImprovementResult

from ._shared import _UNKNOWN_MESSAGE, _unsupported_message


def render_improve_template(result: ImprovementResult) -> str:
    """Emit Markdown templates for missing sections (required first)."""
    if result.type == "unknown":
        return _UNKNOWN_MESSAGE
    if not result.supported:
        return _unsupported_message(result)

    missing = result.missing_required + result.missing_recommended
    if not missing:
        return "# Nothing to add — all expected sections present."

    blocks: list[str] = []
    for section in missing:
        block = f"## {section.title()}\n\n_TODO_"
        guidance_lines = result.guidance.get(section, [])
        if guidance_lines:
            block += "\n\n" + "\n".join(f"<!-- {q} -->" for q in guidance_lines)
        blocks.append(block)
    return "\n\n".join(blocks) + "\n"


def render_schema_template(ref: SchemaReference) -> str:
    blocks = ["# Title"]
    for section in template_sections(ref):
        block = f"## {section.name.title()}\n\n{section.body}"
        comments: list[str] = []
        if section.metadata_values:
            comments.append(f"Choose one: {' | '.join(section.metadata_values)}")
        comments.extend(section.guidance)
        if comments:
            block += "\n\n" + "\n".join(f"<!-- {comment} -->" for comment in comments)
        blocks.append(block)
    return "\n\n".join(blocks) + "\n"
