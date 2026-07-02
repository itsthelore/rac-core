"""RAC Guide MCP server — the read-tool surface (ADR-030, ADR-031).

This module is the FastMCP application: it binds a server to a repository root
and registers the five read-only tools an agent queries. Four are the original
``guide-tool-surface`` tools (``get_artifact``, ``search_artifacts``,
``get_related``, ``get_summary``); the fifth, ``find_decisions``, is the live
decision query (ADR-067) — deterministic retrieval of the Accepted, non-retired
decisions binding a topic, so an agent consults what the team settled rather
than re-litigating it. Every tool description ships verbatim from the design;
editing that text is a contract change (ADR-030).

Guide is a *consumer* of RAC Core (ADR-015, ADR-031): each tool calls read-only
services — resolution, search, relationships, portfolio — and shapes their
results for the wire. It re-implements no parsing, resolution, relationship
extraction, or scoring, and imports no write-capable service. The isolation
battery (``tests/test_mcp_isolation.py``) enforces both by construction.

Every call re-reads the repository from disk (ADR-032): no cache, no file
watcher, no session state. Identical repository bytes and identical input yield
identical output, within the per-response character budget (ADR-033, see
:mod:`rac.mcp.budget`). A failed lookup returns structured error data, never a
protocol exception (ADR-034, :mod:`rac.mcp.errors`).

Two out-of-band recorders may wrap each call, both default-off and both
payload-transparent: opt-in usage telemetry (ADR-040, content-free) and the
config-driven read-access audit log (ADR-084, content-bearing). With neither
present, a tool call is exactly its bare body and the response is byte-identical.
Anonymous daily usage sharing (ADR-041) is a third, independent opt-in that
``run_server`` may start. stdout belongs to the MCP protocol; every diagnostic
goes to stderr.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from rac import consent as consent_record
from rac.core.corpus import walk_corpus
from rac.core.limits import MAX_TRAVERSAL_DEPTH
from rac.core.markdown import parse
from rac.mcp import audit, errors, ping, telemetry
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
from rac.services.recency import artifact_provenance
from rac.services.relationships import (
    incoming_references,
    neighborhood,
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
# These strings are the designed product surface: the only interface an agent
# reads when deciding whether to call a tool. They ship character-for-character
# as the design artifact pins them, "Call this ..." trigger phrasing included.
# Editing this text is a contract change, guarded by test_mcp_server.

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
    "change could affect. Pass depth>1 (up to 5) to also return a `neighborhood` "
    "of artifacts two or more hops out, each tagged with its hop distance, when "
    "you need transitive context rather than immediate neighbours."
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


# --- Tool bodies -------------------------------------------------------------
#
# Each returns the serialized JSON string a tool hands back. They take an
# explicit ``budget`` so the same body serves any startup cap. ``_read_content``
# and the module-level ``walk_corpus`` binding are deliberate monkeypatch seams
# (see the unreadable-artifact and one-walk tests) — keep them module-level.


def _read_content(path: str) -> str:
    """Read an artifact file's text exactly as stored, frontmatter included.

    Presentation-only: the resolver owns *which* file answers an ID; the server
    only reads that file's bytes for the ``content`` field (ADR-031).
    """
    return Path(path).read_text(encoding="utf-8")


def _resolve(root: str, artifact_id: str) -> ResolutionResult:
    """Resolve ``artifact_id`` against a fresh read of ``root`` (ADR-032).

    Resolution runs over the repository index so a single walk answers both the
    ID and any shaping the tool does next.
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
        # Resolved, but its file could not be read (deleted between walk and
        # read, permissions, non-UTF-8). Return the failure as data, never a
        # protocol exception (ADR-034).
        return serialize(errors.unreadable(result.artifact.id, result.artifact.path), budget)
    payload = {
        "schema_version": "1",
        **result.artifact.to_dict(),
        "content": content,
        # Provenance (WS11 + WS5, ADR-065/ADR-045): the single additive object
        # get_artifact's review and accountability fields share. ``status`` is
        # the reviewed ``## Status`` parsed from the same bytes (present-but-empty
        # when none); the rest is git-derived authorship and the reconstructed
        # status history, each null/[] when git cannot answer. Reported facts
        # only — never a trust verdict or score (ADR-034).
        "provenance": {
            "status": artifact_status(parse(content)),
            **artifact_provenance(root, result.artifact.path).to_dict(),
        },
    }
    return serialize(payload, budget)


def _search_artifacts(root: str, query: str, artifact_type: str | None, budget: int) -> str:
    entries = build_repository_index(root, recursive=True).artifacts
    result = search_index(entries, query, artifact_type=artifact_type)
    # The service already supplies the pinned envelope (schema_version, query,
    # type, match_count, matches); the server adds nothing (one source of truth).
    return serialize(result.to_dict(), budget)


def _find_decisions(root: str, topic: str, budget: int) -> str:
    """Ranked live decisions binding ``topic`` (ADR-067, deterministic retrieval).

    Delegates to the same ``find_decisions`` service the CLI uses — structural
    search restricted to live decisions, no semantic verdict — and adds only the
    additive ``filter`` marker (ADR-007) so a reader sees the result is the
    *settled* decisions, not every match.
    """
    payload = find_decisions(root, topic, recursive=True).to_dict()
    payload["filter"] = "live-decisions"
    return serialize(payload, budget)


def _get_related(root: str, artifact_id: str, budget: int, depth: int = 1) -> str:
    # One corpus walk feeds resolution, outgoing, incoming, and the neighborhood,
    # so the whole response reflects a single atomic snapshot (ADR-032): the view
    # cannot drift mid-call, and the snapshot dies with the call (no caching).
    # The walk seam is spied by test_get_related_performs_exactly_one_corpus_walk.
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
            # Edge evidence (WS2, additive): the relationship that surfaced this
            # artifact, named rather than recomputed (REQ-002). A relationship is
            # not a text match, so it carries direction/relationship/target.
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

    # Bounded multi-hop (WS-D): depth>1 adds an additive `neighborhood` of
    # artifacts two-or-more hops out, each tagged with its hop distance (ADR-007).
    # depth=1 leaves the payload byte-identical to the pre-multihop shape.
    neighborhood_truncated = False
    if depth > 1:
        hood = neighborhood(relationships, identity_by_path, artifact.path, depth=depth)
        payload["neighborhood"] = [
            {"id": n.id, "type": n.type, "title": n.title, "path": n.path, "hops": n.hops}
            for n in hood.nodes
            if n.hops > 1
        ]
        payload["depth"] = min(depth, MAX_TRAVERSAL_DEPTH)
        neighborhood_truncated = hood.truncated

    # Per-call edge-cap overflow (WS4, REQ-007): when edge collection hit the cap,
    # mark the response up front with the overflow count. The ADR-033 budget then
    # caps characters on top; if it must drop further incoming entries it
    # recomputes the marker inside serialize, so the response is always bounded.
    edge_overflow = (incoming_result.total - len(incoming_result.items)) + (
        outgoing.total - outgoing.kept
    )
    if edge_overflow > 0 or neighborhood_truncated:
        payload[MARKER_TRUNCATED] = True
        payload[MARKER_OMITTED] = edge_overflow
        payload[MARKER_HINT] = HINT_RELATED
    return serialize(payload, budget)


def _get_summary(root: str, budget: int) -> str:
    summary = build_portfolio_summary(root, recursive=True)
    payload = summary.to_dict()
    # Additive empty-state pointer (ADR-007): a cold session against a fresh
    # repository is told how the user starts authoring, not just shown zeros.
    if summary.total_artifacts == 0:
        payload["guidance"] = (
            "This repository has no RAC artifacts yet. The user can create the "
            "first one with `rac quickstart`, or with `rac init` then "
            "`rac new <type> <path>`. Once artifacts exist, search_artifacts "
            "and get_artifact will return them."
        )
    return serialize(payload, budget)


def build_server(
    root: str,
    budget: int = DEFAULT_BUDGET,
    recorder: TelemetryRecorder | None = None,
    audit_recorder: audit.AuditRecorder | None = None,
) -> FastMCP:
    """Build a fresh Guide MCP server bound to repository ``root``.

    ``budget`` is the per-response character cap (ADR-033), fixed here at
    startup with no per-call override. ``recorder`` enables opt-in usage
    telemetry (ADR-040) and ``audit_recorder`` the read-access audit log
    (ADR-084); with both ``None`` — the default — nothing is recorded and every
    call is exactly its bare tool body. Each invocation returns a new
    :class:`FastMCP` with the five pinned tools registered, holding no corpus
    snapshot (statelessness starts at construction, ADR-032). The CLI runs it
    over stdio.
    """
    server: FastMCP = FastMCP(SERVER_NAME)

    def observed(tool: str, args: dict, call: Callable[[], str]) -> str:
        # Audit (content-bearing, ADR-084) runs innermost, so its duration is the
        # pure call time; telemetry (content-free, ADR-040) wraps it and still
        # sees the unchanged payload. Each is a no-op when its recorder is None,
        # keeping the default response byte-identical.
        return telemetry.observe(
            recorder, tool, lambda: audit.observe(audit_recorder, tool, args, call)
        )

    # FastMCP derives each tool's wire schema by introspecting the handler
    # signature, so the handlers keep their exact names, parameters, and
    # annotations. Each handler is a thin adapter: capture args for the audit
    # log, then delegate to the matching tool body.

    @server.tool(name="get_artifact", description=DESC_GET_ARTIFACT)
    def get_artifact(id: str) -> str:
        return observed("get_artifact", {"id": id}, lambda: _get_artifact(root, id, budget))

    @server.tool(name="search_artifacts", description=DESC_SEARCH_ARTIFACTS)
    def search_artifacts(query: str, type: str | None = None) -> str:
        return observed(
            "search_artifacts",
            {"query": query, "type": type},
            lambda: _search_artifacts(root, query, type, budget),
        )

    @server.tool(name="find_decisions", description=DESC_FIND_DECISIONS)
    def find_decisions_tool(topic: str) -> str:
        return observed(
            "find_decisions", {"topic": topic}, lambda: _find_decisions(root, topic, budget)
        )

    @server.tool(name="get_related", description=DESC_GET_RELATED)
    def get_related(id: str, depth: int = 1) -> str:
        return observed(
            "get_related", {"id": id, "depth": depth}, lambda: _get_related(root, id, budget, depth)
        )

    @server.tool(name="get_summary", description=DESC_GET_SUMMARY)
    def get_summary() -> str:
        return observed("get_summary", {}, lambda: _get_summary(root, budget))

    return server


# --- Process lifecycle -------------------------------------------------------


def _check_corpus(root: str) -> None:
    """Warn on stderr when the repository root holds no recognized artifacts.

    Called once at startup, after the CLI has validated the root directory but
    before serving. An empty corpus is not an error — the server runs and
    ``get_summary`` reports zero artifacts — but a silent first run against a
    misconfigured root would hide the problem. stdout belongs to the MCP
    protocol, so this notice goes only to stderr.
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
    except Exception:  # pragma: no cover — defensive; the corpus walk is stable
        pass


def _maybe_start_sharing(root: str) -> None:
    """Start the consented daily ping; without consent it costs nothing (ADR-041).

    Independent of ``--telemetry`` — each is its own opt-in. The enablement
    notice goes to stderr (stdout is the protocol channel), so sharing is
    announced, never silent. An enterprise lock (ADR-086) forces it off.
    """
    consent = consent_record.load_consent()
    if consent.enterprise_locked or not consent.share_usage:
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
    """Run the Guide server over stdio until the client disconnects; return 0.

    Startup order is fixed: warn on an empty corpus, build the opt-in telemetry
    recorder (with a stderr notice) if requested, build the config-driven audit
    recorder (with a stderr notice) if a stanza enables it, start consented
    usage sharing, then serve. Recording is always announced on stderr, never
    silent (ADR-040, ADR-084). stdout belongs to the MCP protocol.
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

    # The read-access audit log is config-driven (ADR-084), not a flag: an
    # ``audit:`` stanza in .rac/config.yaml turns it on. Default-absent — no
    # stanza, no recorder, no file, and the response stays byte-identical.
    audit_recorder = audit.create_recorder(audit.load_audit_config(root), root)
    if audit_recorder is not None:
        print(
            "rac mcp: audit on — appending one line per read-tool call "
            "(principal, query, returned artifact ids; never content) to "
            f"{audit_recorder.path}",
            file=sys.stderr,
        )

    _maybe_start_sharing(root)
    build_server(root, budget=budget, recorder=recorder, audit_recorder=audit_recorder).run(
        transport="stdio"
    )
    return 0
