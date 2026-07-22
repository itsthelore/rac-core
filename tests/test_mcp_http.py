"""Shared HTTP MCP transport — parity, mandatory audit, CLI wiring (ADR-098).

Initiative 1 of ``lore-at-team-scale`` (itsthelore/rac-core#263): ``decided mcp``
gains a streamable HTTP transport. These tests hold the requirement's contract
(``rac-mcp-http-transport``):

- **Parity (REQ-006):** an HTTP round-trip returns payloads byte-identical to
  the direct handler output for the same fixture corpus, for all five tools —
  the transport changes the wire, never the answer (ADR-002, ADR-032).
- **Mandatory audit-on (REQ-007):** HTTP serving refuses to start without a
  working audit sink (ADR-084 fail-loud); stdio is unchanged.
- **Additive CLI (REQ-001):** stdio stays the default and the new flags are
  wired; the CLI defaults are pinned to the transport module's constants so the
  two never drift.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from contextlib import closing

import pytest
from conftest import fixture_path

from asdecided import cli
from asdecided.mcp import audit
from asdecided.mcp import transport as transport_mod
from asdecided.mcp.server import build_server, run_server
from asdecided.mcp.transport import AuditSinkUnavailable

CORPUS = fixture_path("mcp", "corpus")

DEC = "RAC-MCPDEC000001"
REQ = "RAC-MCPREQ000001"

# One representative call per pinned tool, plus both find_decisions modes
# (topic and the additive path lookup), so parity holds across the surface.
# Each is labelled because find_decisions appears twice.
CALLS: tuple[tuple[str, str, dict], ...] = (
    ("get_artifact", "get_artifact", {"id": DEC}),
    ("search_artifacts", "search_artifacts", {"query": "RAC-MCP"}),
    ("find_decisions:topic", "find_decisions", {"topic": "RAC"}),
    ("find_decisions:path", "find_decisions", {"topic": "", "path": "src/asdecided/mcp/server.py"}),
    ("get_related", "get_related", {"id": REQ}),
    ("get_summary", "get_summary", {}),
)


# --- helpers -----------------------------------------------------------------


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"HTTP server never bound {host}:{port}")


def _direct_payloads() -> dict[str, str]:
    """The tool payloads served over stdio: the direct handler return text."""

    async def _run() -> dict[str, str]:
        server = build_server(str(CORPUS))
        out: dict[str, str] = {}
        for label, name, args in CALLS:
            content, _structured = await server.call_tool(name, args)
            out[label] = content[0].text
        return out

    return asyncio.run(_run())


def _http_payloads(port: int, path: str) -> dict[str, str]:
    """The same tool payloads fetched over the streamable HTTP transport."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _run() -> dict[str, str]:
        url = f"http://127.0.0.1:{port}{path}"
        async with streamable_http_client(url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                out: dict[str, str] = {}
                for label, name, args in CALLS:
                    result = await session.call_tool(name, args)
                    out[label] = result.content[0].text
                return out

    return asyncio.run(_run())


# --- parity (REQ-006) --------------------------------------------------------


def test_http_payloads_are_identical_to_stdio():
    port = _free_port()
    path = "/mcp"

    def _serve() -> None:
        transport_mod.serve_http(build_server(str(CORPUS)), host="127.0.0.1", port=port, path=path)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    _wait_for_port("127.0.0.1", port)

    http_payloads = _http_payloads(port, path)
    direct_payloads = _direct_payloads()

    assert set(http_payloads) == {label for label, _, _ in CALLS}
    for label, _name, _args in CALLS:
        assert http_payloads[label] == direct_payloads[label], f"payload drift on {label}"


# --- mandatory audit-on (REQ-007) --------------------------------------------


def test_ensure_audit_sink_refuses_when_audit_disabled():
    # No recorder means audit is not enabled: HTTP must not start.
    with pytest.raises(AuditSinkUnavailable) as excinfo:
        transport_mod.ensure_audit_sink(None)
    assert "audit" in str(excinfo.value).lower()


def test_ensure_audit_sink_refuses_when_path_unwritable(tmp_path):
    # A configured-but-unwritable sink is not a *working* sink (REQ-007).
    unwritable = tmp_path / "nodir" / "audit.jsonl"
    recorder = audit.AuditRecorder(unwritable, principal="x <x@example.com>")
    # Make the parent un-creatable: turn the grandparent into a file.
    (tmp_path / "nodir").write_text("not a directory", encoding="utf-8")
    with pytest.raises(AuditSinkUnavailable):
        transport_mod.ensure_audit_sink(recorder)


def test_ensure_audit_sink_accepts_a_writable_sink(tmp_path):
    recorder = audit.AuditRecorder(tmp_path / "audit.jsonl", principal="x <x@example.com>")
    transport_mod.ensure_audit_sink(recorder)  # must not raise


def test_http_without_audit_exits_usage(capsys):
    # The fixture corpus has no `audit:` stanza, so an HTTP start must be refused
    # with the usage exit code and an actionable message — never a silent serve.
    parser = cli.build_parser()
    args = parser.parse_args(["mcp", "--root", CORPUS, "--transport", "http"])
    with pytest.raises(SystemExit) as excinfo:
        args.func(args)
    assert excinfo.value.code == cli.EXIT_USAGE
    err = capsys.readouterr().err
    assert "audit" in err.lower()


def test_run_server_http_without_audit_raises(monkeypatch):
    # Below the CLI: run_server itself refuses the HTTP start. serve_http must
    # never be reached when the sink is missing.
    served: list[str] = []
    monkeypatch.setattr(transport_mod, "serve_http", lambda *a, **k: served.append("served"))
    with pytest.raises(AuditSinkUnavailable):
        run_server(CORPUS, transport_name="http")
    assert served == [], "serve_http must not run without a working audit sink"


# --- additive CLI (REQ-001) --------------------------------------------------


def test_bare_mcp_defaults_to_stdio():
    parser = cli.build_parser()
    args = parser.parse_args(["mcp", "--root", CORPUS])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"


def test_http_flags_parse():
    parser = cli.build_parser()
    args = parser.parse_args(
        ["mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "9100", "--path", "/lore"]
    )
    assert args.transport == "http"
    assert args.host == "0.0.0.0"
    assert args.port == 9100
    assert args.path == "/lore"


def test_cli_transport_defaults_match_transport_module():
    # The CLI hardcodes the choices/defaults to stay SDK-free at parser build;
    # this guard pins them to the transport module's source of truth (no drift).
    parser = cli.build_parser()
    args = parser.parse_args(["mcp"])
    assert args.transport == transport_mod.TRANSPORT_STDIO
    assert args.host == transport_mod.DEFAULT_HOST
    assert args.port == transport_mod.DEFAULT_PORT
    assert args.path == transport_mod.DEFAULT_PATH
    # The choice set the parser accepts is exactly the transport module's, so a
    # future third transport can't be added to one and forgotten in the other.
    assert set(transport_mod.TRANSPORTS) == {"stdio", "http"}
    parser.parse_args(["mcp", "--transport", transport_mod.TRANSPORT_HTTP])


def test_run_server_stdio_default_does_not_require_audit(monkeypatch):
    # The default stdio path must not gain the HTTP audit precondition: a
    # fixture with no audit config still serves. Stub the blocking run.
    calls: list[str] = []

    class _FakeServer:
        def run(self, transport: str) -> None:
            calls.append(transport)

    monkeypatch.setattr("asdecided.mcp.server.build_server", lambda *a, **k: _FakeServer())
    monkeypatch.setattr("asdecided.mcp.server._maybe_start_sharing", lambda *a, **k: None)
    monkeypatch.setattr("asdecided.mcp.server._check_corpus", lambda *a, **k: None)
    assert run_server(CORPUS) == 0
    assert calls == ["stdio"]


def test_serve_http_configures_stateless_settings(monkeypatch):
    # serve_http must set the transport up statelessly (no server-held state,
    # REQ-002/REQ-008) and dispatch the SDK's streamable-http transport.
    server = build_server(str(CORPUS))
    ran: list[str] = []
    monkeypatch.setattr(type(server), "run", lambda self, transport: ran.append(transport))
    transport_mod.serve_http(server, host="127.0.0.1", port=8123, path="/lore")
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8123
    assert server.settings.streamable_http_path == "/lore"
    assert server.settings.stateless_http is True
    assert server.settings.json_response is True
    assert ran == ["streamable-http"]


# --- shared-server audit identity over HTTP (#265) ---------------------------


def _serve_with_audit(port: int, path: str, audit_recorder) -> threading.Thread:
    from asdecided.mcp.server import build_server

    def _serve() -> None:
        server = build_server(str(CORPUS), audit_recorder=audit_recorder)
        transport_mod.serve_http(server, host="127.0.0.1", port=port, path=path)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    _wait_for_port("127.0.0.1", port)
    return thread


async def _call_as(port: int, path: str, principal: str | None, count: int) -> None:
    import httpx
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"X-AsDecided-Principal": principal} if principal is not None else {}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as http_client:
        async with streamable_http_client(
            f"http://127.0.0.1:{port}{path}", http_client=http_client
        ) as (read, write, _sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for _ in range(count):
                    await session.call_tool("get_summary", {})


def test_concurrent_clients_are_attributed_distinctly(tmp_path):
    from asdecided.mcp.audit import AuditRecorder

    recorder = AuditRecorder(tmp_path / "audit.jsonl", "host <h@example.com>", transport="http")
    port, path = _free_port(), "/mcp"
    _serve_with_audit(port, path, recorder)

    async def _both() -> None:
        await asyncio.gather(
            _call_as(port, path, "alice <a@example.com>", 3),
            _call_as(port, path, "bob <b@example.com>", 3),
        )

    asyncio.run(_both())

    events = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text().splitlines()
        if line.strip()
    ]
    principals = {ev["principal"] for ev in events}
    assert "alice <a@example.com>" in principals
    assert "bob <b@example.com>" in principals
    assert "host <h@example.com>" not in principals  # host identity never leaks
    for ev in events:
        assert ev["transport"] == "http"
        assert ev["attribution"] == "asserted"


def test_unasserted_http_call_is_not_the_host_identity(tmp_path):
    from asdecided.mcp.audit import AuditRecorder

    # A shared recorder resolves its construction principal without git; an
    # unasserted call is recorded with that fallback, never the host's identity.
    recorder = AuditRecorder(tmp_path / "audit.jsonl", "unattributed", transport="http")
    port, path = _free_port(), "/mcp"
    _serve_with_audit(port, path, recorder)

    asyncio.run(_call_as(port, path, None, 1))

    events = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(events) == 1
    assert events[0]["principal"] == "unattributed"
    assert events[0]["attribution"] == "local"
    assert events[0]["transport"] == "http"


def test_tool_output_is_identical_across_principals(tmp_path):
    # Attribution never becomes authorization (REQ-005): two callers asserting
    # different principals get byte-identical tool payloads.
    import httpx
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from asdecided.mcp.audit import AuditRecorder

    recorder = AuditRecorder(tmp_path / "audit.jsonl", "unattributed", transport="http")
    port, path = _free_port(), "/mcp"
    _serve_with_audit(port, path, recorder)

    async def _get(principal: str) -> str:
        async with httpx.AsyncClient(headers={"X-AsDecided-Principal": principal}, timeout=30.0) as hc:
            async with streamable_http_client(f"http://127.0.0.1:{port}{path}", http_client=hc) as (
                read,
                write,
                _sid,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("get_summary", {})
                    return result.content[0].text

    alice = asyncio.run(_get("alice"))
    bob = asyncio.run(_get("bob"))
    assert alice == bob
