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
from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

from rac import consent as consent_record
from rac.core.corpus import walk_corpus
from rac.core.limits import MAX_TRAVERSAL_DEPTH
from rac.core.markdown import parse
from rac.mcp import audit, errors, ping, telemetry, transport
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
from rac.services.derived_cache import DerivedIndexCache
from rac.services.index import IndexEntry, build_repository_index, index_from_corpus
from rac.services.portfolio import build_portfolio_summary
from rac.services.recency import annotate_search_recency, artifact_provenance
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
    find_decisions_in,
    resolve_in_index,
    search_index,
)
from rac.services.scope import decisions_for_path

SERVER_NAME = "lore"

# The per-request attribution carrier the serving ADR fixes (ADR-098): a caller
# on the shared HTTP endpoint asserts who it is with this header, and the audit
# recorder records the assertion as the per-request principal
# (rac-shared-server-audit-identity). Case-insensitive, like all HTTP headers.
# Attribution, not authentication — the engine never verifies it (ADR-085).
PRINCIPAL_HEADER = "x-lore-principal"


def _request_principal(ctx: Context) -> str | None:
    """The caller's asserted principal from the ``X-Lore-Principal`` header, or None.

    HTTP only: the header rides the request the streamable transport carries. On
    stdio there is no HTTP request, so this is always ``None`` and attribution
    stays the recorder's locally resolved identity (stdio is byte-unchanged,
    ADR-007). Defensive throughout — a missing request context or header is just
    "no assertion", never an error.
    """
    try:
        request = ctx.request_context.request
    except (ValueError, AttributeError):
        return None
    if request is None:
        return None
    try:
        return request.headers.get(PRINCIPAL_HEADER)
    except AttributeError:
        return None


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
    "change could affect. Pass depth>1 (up to 5) to also return a `neighborhood` "
    "of artifacts two or more hops out, each tagged with its hop distance, when "
    "you need transitive context rather than immediate neighbours."
)

DESC_FIND_DECISIONS = (
    "Find the team's already-settled decisions about a topic — or the decisions "
    "that govern a specific code path. Call this whenever the user (or you) asks "
    "'what did we decide about X', 'is X ruled out', 'did we already decide this', "
    "'what's our policy on X', or before proposing, changing, or arguing for "
    "anything a prior decision might have settled — so you respect recorded "
    "decisions instead of re-litigating them. Pass `topic` for a keyword query, or "
    "pass `path` (a repository file or directory) to get the decisions whose "
    "declared scope governs that code — the recorded decisions that constrain an "
    "edit there. Returns the live (Accepted, non-retired) decisions, each with its "
    "identifier, title, and path; a topic query ranks by relevance with category "
    "and a snippet, a path query reports each decision's status and the matching "
    "declared scope. It tells you which decisions bind; read them and judge for "
    "yourself — it does not decide whether a change contradicts them. Use "
    "get_artifact to read a decision's full text."
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


def _index_entries(root: str, cache: DerivedIndexCache | None) -> list[IndexEntry]:
    """The repository index rows, from the derived-index cache or a fresh walk.

    With ``cache`` set (ADR-099) the rows come from the content-addressed cache —
    byte-identical to the fresh build, only the walk/index is skipped under an
    unchanged corpus key. With ``cache`` None the serving path is exactly as
    before (ADR-032): a fresh read every call.
    """
    if cache is not None:
        return cache.load_or_build(root).index_entries
    return build_repository_index(root, recursive=True).artifacts


def _resolve(
    root: str, artifact_id: str, cache: DerivedIndexCache | None = None
) -> ResolutionResult:
    """Resolve ``artifact_id`` against the repository index (ADR-032).

    Uses the repository index and the resolver's in-index semantics so a single
    walk serves both resolution and any follow-on shaping the tool needs.
    """
    return resolve_in_index(_index_entries(root, cache), artifact_id)


def _get_artifact(
    root: str, artifact_id: str, budget: int, cache: DerivedIndexCache | None = None
) -> str:
    result = _resolve(root, artifact_id, cache)
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
        # Provenance (WS11 + WS5, ADR-065/ADR-045): the one additive object
        # get_artifact's review/accountability fields share. ``status`` is the
        # reviewed ``## Status`` from parsed bytes (WS11 trust signal,
        # present-but-empty when none); the rest is git-derived authorship and
        # the reconstructed status history (WS5), each ``null``/``[]`` when git
        # cannot answer. All reported facts sourced from the repository, never a
        # trust verdict or score (ADR-034).
        "provenance": {
            "status": artifact_status(parse(content)),
            **artifact_provenance(root, result.artifact.path).to_dict(),
        },
    }
    return serialize(payload, budget)


def _search_artifacts(
    root: str,
    query: str,
    artifact_type: str | None,
    budget: int,
    cache: DerivedIndexCache | None = None,
) -> str:
    if cache is not None:
        derived = cache.load_or_build(root)
        result = search_index(
            derived.index_entries,
            query,
            artifact_type=artifact_type,
            field_tokens_by_path=derived.field_tokens_by_path,
        )
    else:
        entries = build_repository_index(root, recursive=True).artifacts
        result = search_index(entries, query, artifact_type=artifact_type)
    # Freshness phase 1 (ADR-045): join git-derived staleness after ranking, so
    # search order is unchanged and the fields degrade to null outside git.
    annotate_search_recency(result.matches, root)
    return serialize(result.to_dict(), budget)


def _find_decisions(
    root: str,
    topic: str,
    path: str | None,
    budget: int,
    cache: DerivedIndexCache | None = None,
) -> str:
    """Live decisions binding a ``topic`` — or governing a code ``path``.

    Two modes over one tool (additive, ADR-007). With ``path`` set, this is the
    path→decisions lookup (``decisions_for_path``, the same core the ``rac
    decisions-for`` CLI uses, ADR-031): the live decisions whose declared
    ``## Applies To`` scope covers the path, each with its status and matching
    entry. Without ``path`` it is the existing topic query (``find_decisions``):
    structural search restricted to live decisions, byte-identical to before.
    Neither mode returns a verdict — the agent reads and judges (ADR-034/067).
    """
    if path:
        return serialize(decisions_for_path(root, path, recursive=True).to_dict(), budget)
    if cache is not None:
        derived = cache.load_or_build(root)
        result = find_decisions_in(
            derived.index_entries,
            derived.live_decision_paths,
            topic,
            field_tokens_by_path=derived.field_tokens_by_path,
        )
    else:
        result = find_decisions(root, topic, recursive=True)
    payload = result.to_dict()
    # Make the live-decision intent explicit on the wire (additive, ADR-007): the
    # type is always "decision" and the result is filtered to live decisions.
    payload["filter"] = "live-decisions"
    return serialize(payload, budget)


def _get_related(
    root: str, artifact_id: str, budget: int, depth: int = 1, cache: DerivedIndexCache | None = None
) -> str:
    # One corpus snapshot feeds resolution, outgoing, and incoming, so the whole
    # response reflects a single atomic view of the repository (ADR-032): there
    # is no window in which the relationship view drifts mid-call. With the
    # derived-index cache (ADR-099) the index and relationship graph come from
    # one content-addressed snapshot; without it, one fresh walk feeds both.
    # Either way the two are from the same snapshot and the output is identical.
    if cache is not None:
        derived = cache.load_or_build(root)
        index = derived.index_entries
        relationships = derived.relationships
    else:
        entries = list(walk_corpus(root, recursive=True))
        index = index_from_corpus(root, entries, recursive=True).artifacts
        relationships = relationships_from_corpus(entries)
    result = resolve_in_index(index, artifact_id)
    if result.outcome != OUTCOME_RESOLVED or result.artifact is None:
        return serialize(errors.from_resolution(result), budget)
    artifact = result.artifact
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
    # Bounded multi-hop (v0.24, WS-D): depth>1 adds an additive `neighborhood`
    # field listing artifacts two-or-more hops out, each tagged with its hop
    # distance (ADR-007). depth=1 leaves the payload byte-identical to before.
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
    # Per-call edge cap overflow (WS4, REQ-007): when collection hit the cap, mark
    # the response truncated up front. The ADR-033 response budget then enforces
    # the character cap on top; if it must drop further incoming entries it
    # recomputes the marker (budget.serialize), so the response is always bounded
    # and carries the additive truncated/omitted/hint signal (REQ-006).
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
    root: str,
    budget: int = DEFAULT_BUDGET,
    recorder: TelemetryRecorder | None = None,
    audit_recorder: audit.AuditRecorder | None = None,
    cache: DerivedIndexCache | None = None,
) -> FastMCP:
    """Build the Guide MCP server bound to repository ``root``.

    ``budget`` is the per-response character cap (ADR-033), configurable here at
    startup; there is no per-call override. ``recorder`` enables opt-in usage
    telemetry (ADR-040) and ``audit_recorder`` enables the read-access audit log
    (ADR-084): with both ``None`` — the default — nothing is recorded and every
    call is exactly the bare tool body. ``cache`` enables the derived-index cache
    (ADR-099): with ``None`` — the default — every tool re-reads and rebuilds from
    disk (ADR-032); with a cache, the expensive derived structures are reused
    under an unchanged corpus content hash, byte-identically. The returned
    :class:`FastMCP` instance has the five pinned tools registered and is ready to
    run over any transport — the CLI runs it over stdio.
    """
    server: FastMCP = FastMCP(SERVER_NAME)

    def observed(
        tool: str, args: dict, call: Callable[[], str], principal: str | None = None
    ) -> str:
        # Audit (content-bearing, ADR-084) runs innermost so its duration is the
        # pure call time; telemetry (content-free, ADR-040) wraps it and still
        # sees the unchanged payload. Each is a no-op when its recorder is None,
        # so the default response stays byte-identical. ``principal`` is the
        # caller's per-request assertion (ADR-098); it reaches only the audit
        # record, never the tool body — attribution, not authorization.
        return telemetry.observe(
            recorder,
            tool,
            lambda: audit.observe(audit_recorder, tool, args, call, request_principal=principal),
        )

    @server.tool(name="get_artifact", description=DESC_GET_ARTIFACT)
    def get_artifact(id: str, ctx: Context) -> str:
        return observed(
            "get_artifact",
            {"id": id},
            lambda: _get_artifact(root, id, budget, cache),
            _request_principal(ctx),
        )

    @server.tool(name="search_artifacts", description=DESC_SEARCH_ARTIFACTS)
    def search_artifacts(query: str, ctx: Context, type: str | None = None) -> str:
        return observed(
            "search_artifacts",
            {"query": query, "type": type},
            lambda: _search_artifacts(root, query, type, budget, cache),
            _request_principal(ctx),
        )

    @server.tool(name="find_decisions", description=DESC_FIND_DECISIONS)
    def find_decisions_tool(ctx: Context, topic: str = "", path: str | None = None) -> str:
        # ``path`` only rides the audit args when supplied, so a topic query's
        # recorded shape is byte-identical to before (additive, ADR-007).
        args = {"topic": topic} if path is None else {"topic": topic, "path": path}
        return observed(
            "find_decisions",
            args,
            lambda: _find_decisions(root, topic, path, budget, cache),
            _request_principal(ctx),
        )

    @server.tool(name="get_related", description=DESC_GET_RELATED)
    def get_related(id: str, ctx: Context, depth: int = 1) -> str:
        return observed(
            "get_related",
            {"id": id, "depth": depth},
            lambda: _get_related(root, id, budget, depth, cache),
            _request_principal(ctx),
        )

    @server.tool(name="get_summary", description=DESC_GET_SUMMARY)
    def get_summary(ctx: Context) -> str:
        return observed(
            "get_summary", {}, lambda: _get_summary(root, budget), _request_principal(ctx)
        )

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


def run_server(
    root: str,
    budget: int = DEFAULT_BUDGET,
    telemetry_enabled: bool = False,
    transport_name: str = transport.TRANSPORT_STDIO,
    host: str = transport.DEFAULT_HOST,
    port: int = transport.DEFAULT_PORT,
    path: str = transport.DEFAULT_PATH,
    cache_enabled: bool = False,
) -> int:
    """Run the Guide server over stdio (default) or streamable HTTP.

    Returns ``0`` on clean shutdown. stdout belongs to the MCP protocol; any
    diagnostics a caller emits go to stderr (the CLI owns that channel).

    ``transport_name`` selects the transport (ADR-098): ``"stdio"`` is the
    default and byte-unchanged; ``"http"`` fronts an always-current
    ``main``-backed checkout for the whole team over one endpoint, configured by
    ``host``/``port``/``path`` and served statelessly (ADR-032). HTTP serving is
    mandatory-audit-on: it refuses to start without a working audit sink
    (ADR-084), asserted before the endpoint opens.

    ``cache_enabled`` turns on the derived-index cache (ADR-099): the expensive
    derived structures are persisted content-addressed and reused under an
    unchanged corpus hash, byte-identically to the uncached path. Off by default —
    the serving path is exactly ADR-032's re-read-per-call otherwise.

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
    # The read-access audit log is config-driven (ADR-084), not a flag: enabled
    # by an ``audit:`` stanza in .rac/config.yaml. Default-absent — no stanza,
    # no recorder, no file, and the response stays byte-identical. The transport
    # shapes the shared-server posture (ADR-098): HTTP skips the host git identity
    # and blocks on write failure (rac-shared-server-audit-identity).
    audit_recorder = audit.create_recorder(
        audit.load_audit_config(root), root, transport=transport_name
    )
    if audit_recorder is not None:
        print(
            "rac mcp: audit on — appending one line per read-tool call "
            "(principal, query, returned artifact ids; never content) to "
            f"{audit_recorder.path}",
            file=sys.stderr,
        )
    cache: DerivedIndexCache | None = None
    if cache_enabled:
        cache = DerivedIndexCache()
        print(
            "rac mcp: derived-index cache on — reusing content-addressed derived "
            f"structures under {cache.cache_dir} (disposable; byte-identical to the "
            "uncached path, ADR-099).",
            file=sys.stderr,
        )
    server = build_server(
        root, budget=budget, recorder=recorder, audit_recorder=audit_recorder, cache=cache
    )
    if transport_name == transport.TRANSPORT_HTTP:
        # Mandatory-audit-on entry condition (ADR-084): a shared endpoint
        # without a working auditor refuses to start rather than serving reads
        # no one can attribute. Checked before the port opens, and before the
        # daily-sharing daemon starts, so a refused start is inert.
        transport.ensure_audit_sink(audit_recorder)
        print(
            f"rac mcp: serving over HTTP at http://{host}:{port}{path} "
            "(read-only, stateless per call; authentication belongs to the "
            "deployment proxy, ADR-085).",
            file=sys.stderr,
        )
        _maybe_start_sharing(root)
        transport.serve_http(server, host=host, port=port, path=path)
        return 0
    _maybe_start_sharing(root)
    server.run(transport="stdio")
    return 0
