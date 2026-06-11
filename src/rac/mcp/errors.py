"""Structured error shapes for Guide tools (v0.10.0).

Failed lookups are returned as data, never raised as protocol exceptions: an
agent recovers from a JSON body, not from a transport error (ADR-034 reasoning
boundary, ADR-007 contract stability). The shapes here are the resolver's own
outcomes (``not-found``, ``duplicate``) rendered for the tool surface, matching
``ResolutionResult.to_dict`` byte-for-byte so a Guide error is the same error
``rac resolve --json`` emits.

The server layer constructs these from a :class:`~rac.services.resolve.ResolutionResult`
rather than re-deriving them, keeping resolution semantics in Core (ADR-031).
"""

from __future__ import annotations

from rac.services.resolve import ResolutionResult

# Stable error tokens (part of the pinned tool output contract). These mirror
# the resolver's OUTCOME_NOT_FOUND / OUTCOME_DUPLICATE values.
ERROR_NOT_FOUND = "not-found"
ERROR_DUPLICATE = "duplicate"


def not_found(artifact_id: str) -> dict:
    """The structured not-found result for ``artifact_id``."""
    return {"schema_version": "1", "error": ERROR_NOT_FOUND, "id": artifact_id}


def duplicate(artifact_id: str, paths: list[str]) -> dict:
    """The structured duplicate result for ``artifact_id`` and its paths."""
    return {
        "schema_version": "1",
        "error": ERROR_DUPLICATE,
        "id": artifact_id,
        "paths": list(paths),
    }


def from_resolution(result: ResolutionResult) -> dict:
    """Render a non-resolved :class:`ResolutionResult` as a structured error.

    The result must be a failure (not-found or duplicate); a resolved result
    has no error shape and is a programming error here. The output is exactly
    ``ResolutionResult.to_dict()`` for the failure outcomes — the same body the
    CLI emits — so tool errors cannot drift from CLI errors.
    """
    return result.to_dict()
