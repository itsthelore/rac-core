"""Improvement-guidance fallbacks shared by the human and template renderers.

These two symbols live here, rather than in either renderer, so ``human`` and
``templates`` can both reach them without importing each other. The message
strings are part of the ``rac improve`` contract (pinned by
``tests/test_improve.py``): do not reword them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rac.services.improve import ImprovementResult

# Shown when the artifact type cannot be determined, so no guidance can be
# produced at all.
_UNKNOWN_MESSAGE = (
    "Unable to generate improvement guidance.\nArtifact type could not be determined."
)


def _unsupported_message(result: ImprovementResult) -> str:
    """Guidance for a known but unsupported artifact type (e.g. Decision)."""
    return (
        f"Artifact Type: {result.type.title()}\n\n"
        "Improvement guidance is not currently available for this artifact type."
    )
