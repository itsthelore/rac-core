"""HTTP serving layer for the Guide MCP server (ADR-098).

This is the fenced *transport layer* the serving ADR (ADR-098) names: the one
module besides ``ping`` permitted to reach network/serving machinery, kept
apart from the read-only tool logic in :mod:`rac.mcp.server`. The serving ADR
resolves the ADR-091 stdio-only premise against ADR-080's recorded
shared-``main``-backed-server intent — the shared HTTP endpoint is a transport
feature, not a datastore. The isolation battery
(``tests/test_mcp_isolation.py``) enforces the split: tool-logic modules stay
network-import-free; only ``ping`` and this module may reach network code.

The engine grows no authentication (ADR-085): identity stays the attributable
principal (ADR-084), and authentication belongs to the deployment proxy. HTTP
serving is stateless per call (ADR-032) — no sessions, no server-held state
(``stateless_http``, ``json_response``) — so an HTTP response is payload-
identical to stdio for identical corpus bytes (ADR-002).

HTTP serving is mandatory-audit-on (ADR-084, this roadmap's entry condition):
a shared endpoint without a *working* audit sink refuses to start rather than
serving reads no auditor can attribute. :func:`ensure_audit_sink` proves the
sink writable at startup and fails loud otherwise.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from rac.errors import RACError
from rac.mcp import audit

# CLI transport choices. ``stdio`` is the default and byte-unchanged; ``http``
# selects the SDK's streamable-HTTP transport below.
TRANSPORT_STDIO = "stdio"
TRANSPORT_HTTP = "http"
TRANSPORTS: tuple[str, ...] = (TRANSPORT_STDIO, TRANSPORT_HTTP)

# The MCP SDK transport identifier the ``http`` choice maps to.
_SDK_STREAMABLE_HTTP: Literal["streamable-http"] = "streamable-http"

# Transport-layer defaults (mirrored from the SDK so the CLI can advertise
# them). Loopback by default: exposing the endpoint to a network is the
# operator's deliberate act via the deployment proxy (ADR-085).
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_PATH = "/mcp"


class AuditSinkUnavailable(RACError):
    """HTTP serving was requested without a working audit sink (ADR-084).

    A shared HTTP endpoint is mandatory-audit-on: without an auditor every
    caller's reads would be un-attributable, so the server refuses to start
    rather than serving them. The message names the fix — configure an
    ``audit:`` stanza in ``.rac/config.yaml``.
    """


def ensure_audit_sink(recorder: audit.AuditRecorder | None) -> None:
    """Prove the audit sink exists and is writable, or raise (ADR-084 fail-loud).

    The HTTP entry condition: no recorder means audit is not enabled, and an
    unwritable path means the sink is configured but not *working*. Either way
    the shared endpoint must not start. A stdio server never calls this — audit
    stays config-driven and default-absent there (ADR-084's strict superset).
    """
    if recorder is None:
        raise AuditSinkUnavailable(
            "HTTP serving requires the read-access audit log, but it is not "
            "enabled. Add an `audit:` stanza with `enabled: true` to "
            ".rac/config.yaml before serving over HTTP (ADR-084)."
        )
    try:
        recorder.path.parent.mkdir(parents=True, exist_ok=True)
        with open(recorder.path, "a", encoding="utf-8"):
            pass
    except OSError as exc:
        raise AuditSinkUnavailable(
            f"HTTP serving requires a writable audit log, but {recorder.path} "
            f"could not be opened for append ({exc}). Fix the audit path or "
            "permissions before serving over HTTP (ADR-084)."
        ) from None


def serve_http(
    server: FastMCP,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    path: str = DEFAULT_PATH,
) -> None:
    """Serve ``server`` over streamable HTTP until interrupted.

    Configures the transport on the server's settings and runs the SDK's
    streamable-HTTP transport statelessly (ADR-032): no session store, a single
    JSON response per request, so the payload matches stdio byte-for-byte for
    identical corpus bytes (REQ-006). The tools themselves are untouched — this
    is serving-layer only (REQ-002).
    """
    server.settings.host = host
    server.settings.port = port
    server.settings.streamable_http_path = path
    server.settings.stateless_http = True
    server.settings.json_response = True
    server.run(transport=_SDK_STREAMABLE_HTTP)
