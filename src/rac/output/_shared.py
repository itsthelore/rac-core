"""Output helpers shared by more than one formatter.

Currently just the improvement-guidance fallbacks, used by both the human and the
template renderers — kept here so ``human`` and ``templates`` stay decoupled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rac.services.improve import ImprovementResult

# Shown when guidance cannot be produced. Ordering everywhere is required-first,
# then recommended (schema declaration order within each).
_UNKNOWN_MESSAGE = (
    "Unable to generate improvement guidance.\n"
    "Artifact type could not be determined."
)


def _unsupported_message(result: ImprovementResult) -> str:
    """Generic guidance for a known but unsupported artifact type (e.g. Decision)."""
    return (
        f"Artifact Type: {result.type.title()}\n\n"
        "Improvement guidance is not currently available for this artifact type."
    )
