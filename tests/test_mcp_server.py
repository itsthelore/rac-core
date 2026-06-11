"""Guide server wiring — factory, CLI registration, exit codes (v0.10.0).

Covers the construction and CLI surface of ``rac mcp``: that the factory builds
a server with the four pinned tools and verbatim descriptions, that the
subcommand is registered and defaults ``--root`` to the current directory, and
that a bad ``--root`` exits with the usage code without ever starting the
server. The tool *contracts* (output shapes, truncation, errors) live in
``test_mcp_tools``.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import fixture_path

from rac import cli
from rac.mcp import server as mcp_server
from rac.mcp.budget import DEFAULT_BUDGET
from rac.mcp.server import build_server, run_server

CORPUS = fixture_path("mcp", "corpus")

# The exact four tool names the surface pins (ADR-030); order-independent.
EXPECTED_TOOLS = {"get_artifact", "search_artifacts", "get_related", "get_summary"}


def _tools(root: str):
    server = build_server(root)
    return {t.name: t for t in asyncio.run(server.list_tools())}


def test_factory_registers_exactly_the_four_tools():
    assert set(_tools(CORPUS)) == EXPECTED_TOOLS


def test_factory_returns_a_fresh_server_each_call():
    # No shared/global server state — statelessness starts at construction.
    assert build_server(CORPUS) is not build_server(CORPUS)


def test_tool_descriptions_ship_verbatim():
    tools = _tools(CORPUS)
    assert tools["get_artifact"].description == mcp_server.DESC_GET_ARTIFACT
    assert tools["search_artifacts"].description == mcp_server.DESC_SEARCH_ARTIFACTS
    assert tools["get_related"].description == mcp_server.DESC_GET_RELATED
    assert tools["get_summary"].description == mcp_server.DESC_GET_SUMMARY


def test_descriptions_name_the_trigger_moment():
    # The design's grounding behaviour lives in "Call this …" trigger phrasing;
    # guard against an accidental rewrite that drops it.
    assert "Call this whenever an artifact ID is mentioned" in mcp_server.DESC_GET_ARTIFACT
    assert "Call this before designing or implementing" in mcp_server.DESC_SEARCH_ARTIFACTS
    assert "Call this after retrieving an artifact" in mcp_server.DESC_GET_RELATED
    assert "Call this once at the start of a session" in mcp_server.DESC_GET_SUMMARY


def test_cli_registers_the_mcp_subcommand():
    parser = cli.build_parser()
    args = parser.parse_args(["mcp", "--root", CORPUS])
    assert args.func is cli.cmd_mcp
    assert args.root == CORPUS


def test_cli_root_defaults_to_current_directory():
    parser = cli.build_parser()
    args = parser.parse_args(["mcp"])
    assert args.root == "."


def test_cli_bad_root_exits_usage_without_serving(monkeypatch):
    called = False

    def _should_not_run(*_args, **_kwargs):  # pragma: no cover - must not run
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr("rac.mcp.server.run_server", _should_not_run)
    parser = cli.build_parser()
    args = parser.parse_args(["mcp", "--root", "/no/such/directory"])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    assert exc.value.code == cli.EXIT_USAGE
    assert called is False


def test_cli_valid_root_runs_server_and_returns_zero(monkeypatch):
    captured = {}

    def _fake_run(root: str) -> int:
        captured["root"] = root
        return 0

    monkeypatch.setattr("rac.mcp.server.run_server", _fake_run)
    parser = cli.build_parser()
    args = parser.parse_args(["mcp", "--root", CORPUS])
    assert args.func(args) == cli.EXIT_OK
    assert captured["root"] == CORPUS


def test_run_server_returns_zero_on_clean_shutdown(monkeypatch):
    # run_server delegates to FastMCP.run over stdio; stub the transport so the
    # clean-shutdown exit code (0) is exercised without a real client.
    ran = {}

    def _fake_run(self, transport="stdio", mount_path=None):
        ran["transport"] = transport

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", _fake_run)
    assert run_server(CORPUS) == 0
    assert ran["transport"] == "stdio"


def test_default_budget_is_ten_thousand():
    assert DEFAULT_BUDGET == 10_000


# --- Empty-corpus startup hardening (v0.10.1) ---------------------------------


def test_empty_corpus_startup_emits_helpful_stderr(tmp_path, capsys):
    # An empty directory (no RAC artifacts) must produce a diagnostic on stderr
    # so the first misconfigured run fails visibly, not silently.
    from rac.mcp.server import _check_corpus

    _check_corpus(str(tmp_path))
    captured = capsys.readouterr()
    assert captured.out == "", "diagnostics must not go to stdout (protocol channel)"
    assert "no RAC artifacts found" in captured.err
    assert "get_summary" in captured.err


def test_empty_corpus_get_summary_returns_zero_artifacts(tmp_path):
    # get_summary must work and report zero artifacts on an empty root, never fail.
    import asyncio
    import json

    server = build_server(str(tmp_path))
    result, _ = asyncio.run(server.call_tool("get_summary", {}))
    payload = json.loads(result[0].text)
    assert payload["schema_version"] == "1"
    assert payload["artifacts"]["total"] == 0


def test_non_empty_corpus_startup_emits_no_stderr(capsys):
    # A root with known artifacts must produce no startup diagnostic.
    from rac.mcp.server import _check_corpus

    _check_corpus(CORPUS)
    captured = capsys.readouterr()
    assert captured.err == "", "no diagnostic expected for a populated corpus"


def test_run_server_empty_corpus_exits_zero(tmp_path, monkeypatch):
    # run_server on an empty root must still start (and exit 0) after emitting
    # the helpful stderr notice — the empty state is not a fatal error.
    ran = {}

    def _fake_run(self, transport="stdio", mount_path=None):
        ran["transport"] = transport

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", _fake_run)
    assert run_server(str(tmp_path)) == 0
    assert ran["transport"] == "stdio"
