"""Compare two :class:`~rac.models.Product` ASTs and classify the changes.

Diffing operates purely on the AST, never on raw Markdown text.

- Requirements are matched by ID:
    * same ID, same text   -> unchanged (omitted)
    * same ID, different    -> modified
    * ID only in the new    -> added
    * ID only in the old    -> removed
- Metrics and risks are matched by exact string (set difference).
"""

from __future__ import annotations

from .models import Diff, Product, Requirement, RequirementChange


def _by_id(requirements: list[Requirement]) -> dict[str, Requirement]:
    # On a duplicate ID (a validation error) the last occurrence wins; the diff
    # is still well-defined.
    return {r.id: r for r in requirements}


def _ordered_difference(a: list[str], b: list[str]) -> list[str]:
    """Items in ``a`` not present in ``b``, preserving ``a``'s order, de-duped."""
    b_set = set(b)
    seen: set[str] = set()
    out: list[str] = []
    for item in a:
        if item not in b_set and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def diff(old: Product, new: Product) -> Diff:
    """Return the classified :class:`Diff` between ``old`` and ``new``."""
    old_reqs = _by_id(old.requirements)
    new_reqs = _by_id(new.requirements)

    result = Diff()

    # Added / modified: iterate new (preserves new-file order).
    for req_id, new_req in new_reqs.items():
        old_req = old_reqs.get(req_id)
        if old_req is None:
            result.added_requirements.append(new_req)
        elif old_req.text != new_req.text:
            result.modified_requirements.append(
                RequirementChange(
                    id=req_id, old_text=old_req.text, new_text=new_req.text
                )
            )

    # Removed: in old but not new (preserves old-file order).
    for req_id, old_req in old_reqs.items():
        if req_id not in new_reqs:
            result.removed_requirements.append(old_req)

    result.added_metrics = _ordered_difference(
        new.success_metrics, old.success_metrics
    )
    result.removed_metrics = _ordered_difference(
        old.success_metrics, new.success_metrics
    )
    result.added_risks = _ordered_difference(new.risks, old.risks)
    result.removed_risks = _ordered_difference(old.risks, new.risks)

    return result
