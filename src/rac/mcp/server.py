"""RAC Guide MCP server — the read-tool surface (v0.10.0; v0.21.16).

This module is the FastMCP application: it builds a server bound to a
repository root and registers the read-only tools the agent queries. The
original four the ``guide-tool-surface`` design pins (``get_artifact``,
``search_artifacts``, ``get_related``, ``get_summary``) ship their descriptions
verbatim from that design; changing them is a contract change (ADR-030).
v0.21.16 adds ``find_decisions`` — the live decision query (ADR-067):
deterministic retrieval of the Accepted, non-retired decisions binding a topic,
so an agent consults what the team already settled instead of re-litigating it.

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

Opt-in telemetry (v0.10.4, ADR-040): when serving with a recorder, each tool
call routes through :func:`rac.mcp.telemetry.observe`, which times the call,
classifies the structured payload, and returns it unchanged — tool responses
are byte-identical with telemetry on and off, and the log is never an input
to a response. Default is off; nothing is recorded without ``--telemetry``.

Anonymous usage sharing (v0.10.6, ADR-041): with consent recorded via
``rac telemetry on`` (or the ``rac init`` prompt), ``run_server`` starts the
daily-ping daemon thread (:mod:`rac.mcp.ping`) — at most one pinned,
content-free ping per 24 hours, independent of ``--telemetry``, announced on
stderr. Without consent or without a configured key, nothing sends.

Startup diagnostics (v0.10.1): ``run_server`` writes a one-line notice to
stderr when the repository root contains no recognized artifacts, so the first
run against a misconfigured or empty root fails helpfully rather than silently.
stdout belongs to the MCP protocol; only stderr carries diagnostics.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from rac import consent as consent_record
from rac.core.corpus import walk_corpus
from rac.core.markdown import parse
from rac.mcp import errors, ping, telemetry
from rac.mcp.budget import (
    DEFAULT_BUDGET,
    HINT_RELATED,
    MARKER_HINT,
    MARKER_OMITTED,
    MARKER_TRUNCATED,
    serialize,
)
from rac.mcp.telemetry import TelemetryRecorder
from rac.services.agent_rules import artifact_status
from rac.services.index import build_repository_index, index_from_corpus
from rac.services.portfolio import build_portfolio_summary
from rac.services.relationships import (
    incoming_references,
    outgoing_references,
    relationships_from_corpus,
)
from rac.services.resolve import (
    OUTCOME_RESOLVED,
    ResolutionResult,
    find_decisions,
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

DESC_FIND_DECISIONS = (
    "Find the team's already-settled decisions about a topic. Call this whenever "
    "the user (or you) asks 'what did we decide about X', 'is X ruled out', 'did "
    "we already decide this', 'what's our policy on X', or before proposing, "
    "changing, or arguing for anything a prior decision might have settled — so "
    "you respect recorded decisions instead of re-litigating them. Returns the "
    "live (Accepted, non-retired) decisions ranked by relevance to the topic, "
    "each with its identifier, title, path, category, and a snippet. It tells you "
    "which decisions bind the topic; read them and judge for yourself — it does "
    "not decide whether a change contradicts them. Use get_artifact to read a "
    "decision's full text."
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


def _get_artifact(root: str, artifact_id: str, budget: int) -> str:
    result = _resolve(root, artifact_id)
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
        # Trust signal (WS11, ADR-065): the artifact's reviewed ``## Status``,
        # nested under ``provenance`` — the one object get_artifact's additive
        # fields share (WS5 adds author/date/status-history here later). It is a
        # reported fact sourced from repository bytes, never a trust verdict
        # (ADR-034); present-but-empty when the artifact declares no status.
        "provenance": {"status": artifact_status(parse(content))},
    }
    return serialize(payload, budget)


def _search_artifacts(root: str, query: str, artifact_type: str | None, budget: int) -> str:
    entries = build_repository_index(root, recursive=True).artifacts
    result = search_index(entries, query, artifact_type=artifact_type)
    return serialize(result.to_dict(), budget)


def _find_decisions(root: str, topic: str, budget: int) -> str:
    """Ranked live decisions binding ``topic`` (ADR-067, deterministic retrieval).

    Calls the same ``find_decisions`` service the CLI ``--decisions`` face uses
    (one source of truth): structural search restricted to live decisions, no
    semantic verdict. The payload is the search contract plus the live-filter
    intent in ``type``/``filter`` so a reader knows the result is the *settled*
    decisions, not every match.
    """
    result = find_decisions(root, topic, recursive=True)
    payload = result.to_dict()
    # Make the live-decision intent explicit on the wire (additive, ADR-007): the
    # type is always "decision" and the result is filtered to live decisions.
    payload["filter"] = "live-decisions"
    return serialize(payload, budget)


def _get_related(root: str, artifact_id: str, budget: int) -> str:
    # One corpus walk feeds resolution, outgoing, and incoming, so the whole
    # response reflects a single atomic snapshot of the repository (ADR-032):
    # there is no window in which the relationship view drifts mid-call.
    # Caching across calls remains forbidden — the snapshot lives and dies
    # inside this call.
    entries = list(walk_corpus(root, recursive=True))
    index = index_from_corpus(root, entries, recursive=True).artifacts
    result = resolve_in_index(index, artifact_id)
    if result.outcome != OUTCOME_RESOLVED or result.artifact is None:
        return serialize(errors.from_resolution(result), budget)
    artifact = result.artifact
    relationships = relationships_from_corpus(entries)
    identity_by_path = {entry.path: (entry.id, entry.type, entry.title) for entry in index}
    outgoing = outgoing_references(relationships, artifact.path)
    incoming_result = incoming_references(relationships, identity_by_path, artifact.path)
    incoming = [
        {
            "id": ref.id,
            "type": ref.type,
            "title": ref.title,
            "path": ref.path,
            "section": ref.section,
            # Edge evidence (WS2, additive): the relationship edge that surfaced
            # this artifact, named rather than recomputed (REQ-002). A relationship
            # is not a text match, so it carries direction/relationship/target,
            # not field/terms/tier.
            "evidence": {
                "direction": "incoming",
                "relationship": ref.section,
                "target": ref.target,
            },
        }
        for ref in incoming_result.items
    ]
    payload = {
        "schema_version": "1",
        **artifact.to_dict(),
        "outgoing": outgoing.by_section,
        "incoming": incoming,
    }
    # Per-call edge cap overflow (WS4, REQ-007): when collection hit the cap, mark
    # the response truncated up front. The ADR-033 response budget then enforces
    # the character cap on top; if it must drop further incoming entries it
    # recomputes the marker (budget.serialize), so the response is always bounded
    # and carries the additive truncated/omitted/hint signal (REQ-006).
    edge_overflow = (incoming_result.total - len(incoming_result.items)) + (
        outgoing.total - outgoing.kept
    )
    if edge_overflow > 0:
        payload[MARKER_TRUNCATED] = True
        payload[MARKER_OMITTED] = edge_overflow
        payload[MARKER_HINT] = HINT_RELATED
    return serialize(payload, budget)


def _get_summary(root: str, budget: int) -> str:
    summary = build_portfolio_summary(root, recursive=True)
    payload = summary.to_dict()
    # Additive empty-state pointer (v0.13.1, ADR-007): a cold agent session
    # against a fresh repository is told how the user begins authoring, rather
    # than just seeing zeros.
    if summary.total_artifacts == 0:
        payload["guidance"] = (
            "This repository has no RAC artifacts yet. The user can create the "
            "first one with `rac quickstart`, or with `rac init` then "
            "`rac new <type> <path>`. Once artifacts exist, search_artifacts "
            "and get_artifact will return them."
        )
    return serialize(payload, budget)


def build_server(
    root: str, budget: int = DEFAULT_BUDGET, recorder: TelemetryRecorder | None = None
) -> FastMCP:
    """Build the Guide MCP server bound to repository ``root``.

    ``budget`` is the per-response character cap (ADR-033), configurable here at
    startup; there is no per-call override. ``recorder`` enables opt-in usage
    telemetry (ADR-040): with ``None`` — the default — nothing is recorded and
    every call is exactly the bare tool body. The returned :class:`FastMCP`
    instance has the five pinned tools registered and is ready to run over any
    transport — the CLI runs it over stdio.
    """
    server: FastMCP = FastMCP(SERVER_NAME)

    @server.tool(name="get_artifact", description=DESC_GET_ARTIFACT)
    def get_artifact(id: str) -> str:
        return telemetry.observe(recorder, "get_artifact", lambda: _get_artifact(root, id, budget))

    @server.tool(name="search_artifacts", description=DESC_SEARCH_ARTIFACTS)
    def search_artifacts(query: str, type: str | None = None) -> str:
        return telemetry.observe(
            recorder, "search_artifacts", lambda: _search_artifacts(root, query, type, budget)
        )

    @server.tool(name="find_decisions", description=DESC_FIND_DECISIONS)
    def find_decisions_tool(topic: str) -> str:
        return telemetry.observe(
            recorder, "find_decisions", lambda: _find_decisions(root, topic, budget)
        )

    @server.tool(name="get_related", description=DESC_GET_RELATED)
    def get_related(id: str) -> str:
        return telemetry.observe(recorder, "get_related", lambda: _get_related(root, id, budget))

    @server.tool(name="get_summary", description=DESC_GET_SUMMARY)
    def get_summary() -> str:
        return telemetry.observe(recorder, "get_summary", lambda: _get_summary(root, budget))

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


def _maybe_start_sharing(root: str) -> None:
    """Start the consented daily ping; absence of consent costs nothing (ADR-041).

    Independent of ``--telemetry`` — each is its own opt-in. stdout belongs to
    the MCP protocol; the enablement notice goes to stderr, so sharing is
    announced, never silent.
    """
    consent = consent_record.load_consent()
    if not consent.share_usage:
        return
    ping.record_active_repo(root, consent.salt)
    thread = ping.start_ping_thread(consent)
    if thread is not None:
        print(
            "rac mcp: anonymous usage sharing on — at most one daily ping "
            "(random install id, rac version, active-repo count; never paths, "
            "queries, or content). Disable with 'rac telemetry off' (ADR-041).",
            file=sys.stderr,
        )
    else:
        print(
            "rac mcp: usage sharing is enabled but this build has no "
            "PostHog key configured; nothing will be sent.",
            file=sys.stderr,
        )


def run_server(root: str, budget: int = DEFAULT_BUDGET, telemetry_enabled: bool = False) -> int:
    """Run the Guide server over stdio until the client disconnects.

    Returns ``0`` on clean shutdown. stdout belongs to the MCP protocol; any
    diagnostics a caller emits go to stderr (the CLI owns that channel).

    Emits a one-line notice to stderr when the repository root contains no
    recognized artifacts (v0.10.1 startup hardening), and another when
    telemetry is enabled — opt-in recording is announced, never silent
    (ADR-040).
    """
    _check_corpus(root)
    recorder: TelemetryRecorder | None = None
    if telemetry_enabled:
        recorder = telemetry.create_recorder()
        print(
            "rac mcp: telemetry on — appending tool-call events "
            f"(no arguments, no content) to {recorder.path}",
            file=sys.stderr,
        )
    _maybe_start_sharing(root)
    build_server(root, budget=budget, recorder=recorder).run(transport="stdio")
    return 0
