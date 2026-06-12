"""RAC Guide MCP server — the four-tool surface (v0.10.0).

This module is the FastMCP application: it builds a server bound to a
repository root and registers the four read-only tools the
``guide-tool-surface`` design pins (``get_artifact``, ``search_artifacts``,
``get_related``, ``get_summary``). Tool descriptions ship verbatim from that
design; changing them is a contract change (ADR-030).

The server is a *consumer* of RAC Core (ADR-015, ADR-031): every tool calls
read-only service functions — resolution, search, relationships, portfolio —
and shapes their results for the wire. It re-implements no parsing, resolution,
relationship extraction, or scoring, and imports no write-capable service. The
isolation battery (``tests/test_mcp_isolation.py``) enforces both.

Every tool call re-reads the repository from disk (ADR-032): there is no cache,
no file watcher, and no session state. Identical repository bytes and identical
input produce identical output, within the per-response character budget
(ADR-033, see :mod:`rac.mcp.budget`).

Failed lookups return structured error data, never protocol exceptions
(ADR-034, :mod:`rac.mcp.errors`): an agent recovers from a JSON body.

Startup diagnostics (v0.10.1): ``run_server`` writes a one-line notice to
stderr when the repository root contains no recognized artifacts, so the first
run against a misconfigured or empty root fails helpfully rather than silently.
stdout belongs to the MCP protocol; only stderr carries diagnostics.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from rac.core.corpus import walk_corpus
from rac.mcp import errors
from rac.mcp.budget import DEFAULT_BUDGET, serialize
from rac.services.index import build_repository_index, index_from_corpus
from rac.services.portfolio import build_portfolio_summary
from rac.services.relationships import relationships_from_corpus
from rac.services.resolve import (
    OUTCOME_RESOLVED,
    ResolutionResult,
    resolve_in_index,
    search_index,
)

SERVER_NAME = "lore"

# --- Verbatim tool descriptions (pinned by guide-tool-surface; ADR-030) ------
#
# These strings are a designed product surface: the only interface an agent
# sees when deciding whether to call. They ship character-for-character as the
# design artifact pins them. Editing this text is a contract change.

DESC_GET_ARTIFACT = (
    "Retrieve one artifact from this repository's recorded product knowledge — "
    "a requirement, decision (ADR), design, roadmap, or prompt — by its "
    "identifier. Call this whenever an artifact ID is mentioned (for example "
    "REQ-001, ADR-012, or a RAC-prefixed ID), and before relying on or changing "
    "anything a known requirement or decision covers. Returns the artifact's "
    "metadata and full Markdown content."
)

DESC_SEARCH_ARTIFACTS = (
    "Search this repository's recorded product knowledge — requirements, "
    "decisions (ADRs), designs, roadmaps, and prompts — by keyword. Call this "
    "before designing or implementing anything that an existing requirement or "
    "prior decision might cover, and whenever the user mentions a feature area, "
    "so recorded decisions are respected instead of rediscovered. Returns "
    "matching artifact IDs, types, titles, and paths; use get_artifact to read "
    "a match."
)

DESC_GET_RELATED = (
    "List the artifacts connected to one artifact in this repository's product "
    "knowledge: the references it declares and the artifacts that reference "
    "it. Call this after retrieving an artifact, and before changing anything "
    "it covers, to find the decisions, requirements, designs, and roadmaps the "
    "change could affect."
)

DESC_GET_SUMMARY = (
    "Get an overview of this repository's recorded product knowledge: artifact "
    "counts by type, validation state, relationship health, and items needing "
    "attention. Call this once at the start of a session, before exploring or "
    "changing the repository, to learn what recorded knowledge exists and "
    "where it needs care."
)


def _read_content(path: str) -> str:
    """Read an artifact file's text exactly as stored, frontmatter included.

    Presentation-only: the resolver owns *which* file answers an ID; the server
    only reads that file's bytes for the ``content`` field (ADR-031).
    """
    return Path(path).read_text(encoding="utf-8")


def _resolve(root: str, artifact_id: str) -> ResolutionResult:
    """Resolve ``artifact_id`` against a fresh read of ``root`` (ADR-032).

    Uses the repository index and the resolver's in-index semantics so a single
    walk serves both resolution and any follow-on shaping the tool needs.
    """
    entries = build_repository_index(root, recursive=True).artifacts
    return resolve_in_index(entries, artifact_id)


def _outgoing_from(relationships: list, path: str) -> dict[str, list[str]]:
    """The resolved artifact's own relationship sections, references as stored.

    Filters the Core-computed relationship list for references *declared by*
    ``path`` (ADR-031, presentation-only). Keys are snake_case section names in
    the artifact's own spec order; ``relationships_from_corpus`` yields
    references in that order, so a first-seen-wins dict preserves it. References
    are the raw stored text — the source of truth (ADR-016).
    """
    outgoing: dict[str, list[str]] = {}
    for rel in relationships:
        if rel.source_path == path:
            outgoing.setdefault(rel.relationship, []).append(rel.target)
    return outgoing


def _incoming_from(relationships: list, by_path: dict, target_path: str) -> list[dict]:
    """Artifacts whose declared references resolve to ``target_path``.

    Filters the Core-computed relationship list for references whose
    ``resolved_path`` is the target — resolution stays Core-owned (ADR-031): a
    reference is an incoming edge exactly when Core resolved it uniquely to the
    target. Self-references are excluded. Entries are ordered by source path,
    then section, matching the deterministic ordering the design pins.
    """
    incoming: list[dict] = []
    for rel in relationships:
        if rel.resolved_path != target_path:
            continue
        if rel.source_path == target_path:
            continue  # self-references are not incoming edges
        source = by_path.get(rel.source_path)
        if source is None:  # pragma: no cover — every relationship source is indexed
            continue
        incoming.append(
            {
                "id": source.id,
                "type": source.type,
                "title": source.title,
                "path": source.path,
                "section": rel.relationship,
            }
        )
    incoming.sort(key=lambda e: (e["path"], e["section"]))
    return incoming


def build_server(root: str, budget: int = DEFAULT_BUDGET) -> FastMCP:
    """Build the Guide MCP server bound to repository ``root``.

    ``budget`` is the per-response character cap (ADR-033), configurable here at
    startup; there is no per-call override. The returned :class:`FastMCP`
    instance has the four pinned tools registered and is ready to run over any
    transport — the CLI runs it over stdio.
    """
    server: FastMCP = FastMCP(SERVER_NAME)

    @server.tool(name="get_artifact", description=DESC_GET_ARTIFACT)
    def get_artifact(id: str) -> str:
        result = _resolve(root, id)
        if result.outcome != OUTCOME_RESOLVED or result.artifact is None:
            return serialize(errors.from_resolution(result), budget)
        try:
            content = _read_content(result.artifact.path)
        except (OSError, UnicodeDecodeError):
            # The artifact resolved, but its file could not be read (deleted
            # between walk and read, permissions, non-UTF-8). Return the failure
            # as data, never a protocol exception (ADR-034).
            return serialize(errors.unreadable(result.artifact.id, result.artifact.path), budget)
        payload = {
            "schema_version": "1",
            **result.artifact.to_dict(),
            "content": content,
        }
        return serialize(payload, budget)

    @server.tool(name="search_artifacts", description=DESC_SEARCH_ARTIFACTS)
    def search_artifacts(query: str, type: str | None = None) -> str:
        entries = build_repository_index(root, recursive=True).artifacts
        result = search_index(entries, query, artifact_type=type)
        return serialize(result.to_dict(), budget)

    @server.tool(name="get_related", description=DESC_GET_RELATED)
    def get_related(id: str) -> str:
        # One corpus walk feeds resolution, outgoing, and incoming, so the whole
        # response reflects a single atomic snapshot of the repository (ADR-032):
        # there is no window in which the relationship view drifts mid-call.
        # Caching across calls remains forbidden — the snapshot lives and dies
        # inside this call.
        entries = list(walk_corpus(root, recursive=True))
        index = index_from_corpus(root, entries, recursive=True).artifacts
        result = resolve_in_index(index, id)
        if result.outcome != OUTCOME_RESOLVED or result.artifact is None:
            return serialize(errors.from_resolution(result), budget)
        artifact = result.artifact
        relationships = relationships_from_corpus(entries)
        by_path = {entry.path: entry for entry in index}
        payload = {
            "schema_version": "1",
            **artifact.to_dict(),
            "outgoing": _outgoing_from(relationships, artifact.path),
            "incoming": _incoming_from(relationships, by_path, artifact.path),
        }
        return serialize(payload, budget)

    @server.tool(name="get_summary", description=DESC_GET_SUMMARY)
    def get_summary() -> str:
        summary = build_portfolio_summary(root, recursive=True)
        return serialize(summary.to_dict(), budget)

    return server


def _check_corpus(root: str) -> None:
    """Emit a helpful stderr notice when the repository root has no artifacts.

    Called once at startup — after the validity check for the root directory
    (which lives in the CLI layer) but before the server begins serving.
    stdout belongs to the MCP protocol; this function only writes to stderr.
    Absence of a corpus is not an error (the server runs and ``get_summary``
    reports zero artifacts), but silence on the first misconfigured run would
    obscure the problem.
    """
    try:
        index = build_repository_index(root, recursive=True)
        known = [e for e in index.artifacts if e.type != "unknown"]
        if not known:
            print(
                f"rac mcp: no RAC artifacts found under {root!r}. "
                "Point --root at a directory containing RAC Markdown artifacts, "
                "or run 'rac init' to initialize a new repository. "
                "The server is running; get_summary will report the empty state.",
                file=sys.stderr,
            )
    except Exception:  # pragma: no cover — defensive; corpus walk is stable
        pass


def run_server(root: str, budget: int = DEFAULT_BUDGET) -> int:
    """Run the Guide server over stdio until the client disconnects.

    Returns ``0`` on clean shutdown. stdout belongs to the MCP protocol; any
    diagnostics a caller emits go to stderr (the CLI owns that channel).

    Emits a one-line notice to stderr when the repository root contains no
    recognized artifacts (v0.10.1 startup hardening).
    """
    _check_corpus(root)
    build_server(root, budget=budget).run(transport="stdio")
    return 0
