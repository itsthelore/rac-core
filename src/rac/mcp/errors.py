"""Structured error shapes for Guide tools (ADR-034, ADR-007).

A failed lookup is returned as data, never raised as a protocol exception: the
consuming agent recovers from a JSON body, not from a transport error (ADR-034,
the reasoning boundary). The lookup failures — ``not-found`` and ``duplicate``
— are the resolver's own outcomes, rendered here so a Guide error is
byte-for-byte the error ``rac resolve --json`` emits. The server builds them
from a :class:`~rac.services.resolve.ResolutionResult` rather than re-deriving
them, keeping resolution semantics in Core (ADR-031).

Only two of these shapes are live on the server path: :func:`unreadable` (a
server-layer failure Core has no outcome for) and :func:`from_resolution`.
:func:`not_found` and :func:`duplicate` are retained as the documented module
surface — a failed ``ResolutionResult`` already serializes to the same bodies
through :func:`from_resolution`.
"""

from __future__ import annotations

from rac.services.resolve import ResolutionResult

# Stable error tokens (part of the pinned tool output contract). The first two
# mirror the resolver's OUTCOME_NOT_FOUND / OUTCOME_DUPLICATE values.
ERROR_NOT_FOUND = "not-found"
ERROR_DUPLICATE = "duplicate"

# A server-layer failure with no Core outcome: the artifact resolved, but its
# file could not be read (deleted between walk and read, permissions, non-UTF-8).
ERROR_UNREADABLE = "unreadable"


def not_found(artifact_id: str) -> dict:
    """The structured not-found body for ``artifact_id``."""
    return {"schema_version": "1", "error": ERROR_NOT_FOUND, "id": artifact_id}


def duplicate(artifact_id: str, paths: list[str]) -> dict:
    """The structured duplicate body for ``artifact_id`` and its clashing paths."""
    return {
        "schema_version": "1",
        "error": ERROR_DUPLICATE,
        "id": artifact_id,
        "paths": list(paths),
    }


def unreadable(artifact_id: str, path: str) -> dict:
    """The structured body for a resolved artifact whose file fails to read.

    ``id`` is the resolved canonical identifier and ``path`` the resolved file
    path: the artifact is in the index, but its bytes could not be read. The
    agent can retry or report — a later stateless re-read may succeed.
    """
    return {
        "schema_version": "1",
        "error": ERROR_UNREADABLE,
        "id": artifact_id,
        "path": path,
    }


def from_resolution(result: ResolutionResult) -> dict:
    """Render a non-resolved :class:`ResolutionResult` as its structured body.

    The output is exactly ``ResolutionResult.to_dict()`` for the failure
    outcomes — the same body the CLI emits — so a tool error can never drift
    from a CLI error.
    """
    return result.to_dict()
