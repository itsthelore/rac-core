"""Structured error shapes for Guide tools (v0.10.0).

Failed lookups are returned as data, never raised as protocol exceptions: an
agent recovers from a JSON body, not from a transport error (ADR-034 reasoning
boundary, ADR-007 contract stability). The shapes here are the resolver's own
outcomes (``not-found``, ``duplicate``) rendered for the tool surface, matching
``ResolutionResult.to_dict`` byte-for-byte so a Guide error is the same error
``decided resolve --json`` emits.

The server layer constructs these from a :class:`~asdecided.services.resolve.ResolutionResult`
rather than re-deriving them, keeping resolution semantics in Core (ADR-031).
"""

from __future__ import annotations

from asdecided.services.resolve import ResolutionResult

# Stable error tokens (part of the pinned tool output contract). These mirror
# the resolver's OUTCOME_NOT_FOUND / OUTCOME_DUPLICATE values.
ERROR_NOT_FOUND = "not-found"
ERROR_DUPLICATE = "duplicate"

# Server-layer error: the artifact resolved, but its file could not be read
# (deleted between walk and read, permissions, non-UTF-8). Returned as data so
# the agent recovers from a JSON body rather than a protocol exception.
ERROR_UNREADABLE = "unreadable"


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


def unreadable(artifact_id: str, path: str) -> dict:
    """The structured unreadable result for a resolved artifact whose file fails to read.

    ``id`` is the resolved canonical identifier and ``path`` is the resolved
    file path; the artifact exists in the index but its bytes could not be
    read. The agent should retry or report (the file may reappear on a later,
    stateless re-read).
    """
    return {
        "schema_version": "1",
        "error": ERROR_UNREADABLE,
        "id": artifact_id,
        "path": path,
    }


def from_resolution(result: ResolutionResult) -> dict:
    """Render a non-resolved :class:`ResolutionResult` as a structured error.

    The result must be a failure (not-found or duplicate); a resolved result
    has no error shape and is a programming error here. The output is exactly
    ``ResolutionResult.to_dict()`` for the failure outcomes — the same body the
    CLI emits — so tool errors cannot drift from CLI errors.
    """
    return result.to_dict()
