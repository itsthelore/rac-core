"""AST-level requirement diff between two versions of an artifact.

``diff`` compares two :class:`~rac.core.models.Product` ASTs and classifies
what changed. It reads only the parsed structure — requirements, success
metrics, risks — never the raw Markdown, so cosmetic edits (reflowed prose,
reordered paragraphs) never register as a change.

Matching rules:

- Requirements are keyed by their ``[REQ-NNN]`` id. A shared id with identical
  text is unchanged (omitted); a shared id with different text is *modified*;
  an id present only in the new version is *added*; one present only in the old
  is *removed*.
- Success metrics and risks are compared as plain strings by exact equality:
  each direction's delta is the ordered set difference.
"""

from __future__ import annotations

from rac.core.models import Diff, Product, Requirement, RequirementChange


def _index_by_id(requirements: list[Requirement]) -> dict[str, Requirement]:
    # A duplicate id is a validation error handled elsewhere; here the last
    # occurrence wins so the mapping — and thus the diff — stays well-defined.
    return {requirement.id: requirement for requirement in requirements}


def _ordered_difference(source: list[str], other: list[str]) -> list[str]:
    """Items in ``source`` absent from ``other``, in ``source`` order, de-duped."""
    excluded = set(other)
    seen: set[str] = set()
    result: list[str] = []
    for item in source:
        if item not in excluded and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def diff(old: Product, new: Product) -> Diff:
    """Return the classified :class:`Diff` between ``old`` and ``new``."""
    old_by_id = _index_by_id(old.requirements)
    new_by_id = _index_by_id(new.requirements)

    result = Diff()

    # Added and modified are emitted in new-file order (first appearance of each id).
    for req_id, new_req in new_by_id.items():
        old_req = old_by_id.get(req_id)
        if old_req is None:
            result.added_requirements.append(new_req)
        elif old_req.text != new_req.text:
            result.modified_requirements.append(
                RequirementChange(id=req_id, old_text=old_req.text, new_text=new_req.text)
            )

    # Removed are emitted in old-file order.
    for req_id, old_req in old_by_id.items():
        if req_id not in new_by_id:
            result.removed_requirements.append(old_req)

    result.added_metrics = _ordered_difference(new.success_metrics, old.success_metrics)
    result.removed_metrics = _ordered_difference(old.success_metrics, new.success_metrics)
    result.added_risks = _ordered_difference(new.risks, old.risks)
    result.removed_risks = _ordered_difference(old.risks, new.risks)

    return result
