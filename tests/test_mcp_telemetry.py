"""Guide telemetry contracts — opt-in, local-only, content-free (v0.10.4).

The battery pins ADR-040's shape: nothing is recorded without the explicit
opt-in; events carry the pinned field set and never tool arguments or
repository content; tool responses are byte-identical with a recorder attached
and without one (the ADR-032 guard); a recorder that cannot write disables
itself and never breaks a call; and the read-back surface tolerates a
corrupted log. The share flow is pinned as string formatting: the URL decodes
back to the JSON summary (minus the local log path) and RAC transmits nothing.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from pathlib import Path

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.mcp import telemetry
from rac.mcp.budget import DEFAULT_BUDGET
from rac.mcp.server import build_server, run_server
from rac.mcp.telemetry import (
    MAX_LOG_BYTES,
    SHARE_ISSUE_URL,
    SHARE_TEMPLATE,
    TelemetryRecorder,
    create_recorder,
    observe,
    read_events,
    share_url,
    summarize,
    telemetry_path,
)

CORPUS = fixture_path("mcp", "corpus")

DEC = "RAC-MCPDEC000001"

# The pinned event field set, in emission order (ADR-040). ``error`` appears
# only on error outcomes, between ``outcome`` and ``duration_ms``.
EVENT_FIELDS = ["schema_version", "ts", "session", "tool", "outcome", "duration_ms", "truncated"]
EVENT_FIELDS_ERROR = [
    "schema_version",
    "ts",
    "session",
    "tool",
    "outcome",
    "error",
    "duration_ms",
    "truncated",
]

TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def call_text(
    root: str,
    tool: str,
    args: dict,
    budget: int = DEFAULT_BUDGET,
    recorder: TelemetryRecorder | None = None,
) -> str:
    """Invoke a tool and return its raw serialized payload (for byte compare)."""
    server = build_server(root, budget=budget, recorder=recorder)
    contents, _structured = asyncio.run(server.call_tool(tool, args))
    assert len(contents) == 1
    return contents[0].text


def make_recorder(tmp_path: Path) -> TelemetryRecorder:
    return TelemetryRecorder(tmp_path / "guide-telemetry.jsonl")


def events_in(recorder: TelemetryRecorder) -> list[dict]:
    events, skipped = read_events(recorder.path)
    assert skipped == 0
    return events


# --- Opt-in: default off ------------------------------------------------------


def test_default_off_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    for tool, args in [
        ("get_artifact", {"id": DEC}),
        ("search_artifacts", {"query": "event"}),
        ("get_related", {"id": DEC}),
        ("get_summary", {}),
    ]:
        call_text(CORPUS, tool, args)
    assert not telemetry_path().exists()
    assert list(tmp_path.rglob("*")) == []


def test_run_server_without_flag_builds_no_recorder(monkeypatch):
    built = []
    monkeypatch.setattr(telemetry, "create_recorder", lambda: built.append(1))
    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", lambda self, **kw: None)
    assert run_server(CORPUS) == 0
    assert built == []


def test_run_server_with_flag_announces_on_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", lambda self, **kw: None)
    assert run_server(CORPUS, telemetry_enabled=True) == 0
    captured = capsys.readouterr()
    assert captured.out == "", "diagnostics must not go to stdout (protocol channel)"
    assert "telemetry on" in captured.err
    assert "no arguments, no content" in captured.err
    assert str(telemetry_path()) in captured.err


# --- Event schema --------------------------------------------------------------


def test_each_tool_records_exactly_one_pinned_event(tmp_path):
    recorder = make_recorder(tmp_path)
    tools = [
        ("get_artifact", {"id": DEC}),
        ("search_artifacts", {"query": "event"}),
        ("get_related", {"id": DEC}),
        ("get_summary", {}),
    ]
    for tool, args in tools:
        call_text(CORPUS, tool, args, recorder=recorder)
    events = events_in(recorder)
    assert [ev["tool"] for ev in events] == [tool for tool, _ in tools]
    for ev in events:
        assert list(ev) == EVENT_FIELDS
        assert ev["schema_version"] == "1"
        assert TS_PATTERN.match(ev["ts"])
        assert ev["session"] == recorder.session
        assert ev["outcome"] == "ok"
        assert isinstance(ev["duration_ms"], int)
        assert ev["truncated"] is False


def test_events_never_carry_arguments_or_content(tmp_path):
    # The content-free guarantee is a test, not a comment (ADR-040): the
    # artifact ID argument and the repository content the call returned must
    # not appear anywhere in the log.
    recorder = make_recorder(tmp_path)
    payload = call_text(CORPUS, "get_artifact", {"id": DEC}, recorder=recorder)
    call_text(CORPUS, "search_artifacts", {"query": "event bus"}, recorder=recorder)
    log_text = recorder.path.read_text(encoding="utf-8")
    assert DEC not in log_text
    assert "event bus" not in log_text
    assert json.loads(payload)["content"] not in log_text


def test_error_outcome_carries_the_structured_error_token(tmp_path):
    recorder = make_recorder(tmp_path)
    call_text(CORPUS, "get_artifact", {"id": "RAC-ZZZZZZZZZZZZ"}, recorder=recorder)
    (event,) = events_in(recorder)
    assert list(event) == EVENT_FIELDS_ERROR
    assert event["outcome"] == "error"
    assert event["error"] == "not-found"


def test_truncated_response_is_recorded_as_truncated(tmp_path):
    recorder = make_recorder(tmp_path)
    text = call_text(CORPUS, "get_artifact", {"id": DEC}, budget=200, recorder=recorder)
    assert json.loads(text)["truncated"] is True
    (event,) = events_in(recorder)
    assert event["outcome"] == "ok"
    assert event["truncated"] is True


# --- Payload stability (the ADR-032 guard) -------------------------------------


@pytest.mark.parametrize(
    "tool,args,budget",
    [
        ("get_artifact", {"id": DEC}, DEFAULT_BUDGET),  # ok
        ("get_artifact", {"id": "RAC-ZZZZZZZZZZZZ"}, DEFAULT_BUDGET),  # error
        ("get_artifact", {"id": DEC}, 200),  # truncated
        ("search_artifacts", {"query": "event"}, DEFAULT_BUDGET),
        ("get_related", {"id": DEC}, DEFAULT_BUDGET),
        ("get_summary", {}, DEFAULT_BUDGET),
    ],
)
def test_payloads_byte_identical_with_and_without_recorder(tmp_path, tool, args, budget):
    bare = call_text(CORPUS, tool, args, budget=budget)
    recorded = call_text(CORPUS, tool, args, budget=budget, recorder=make_recorder(tmp_path))
    assert recorded == bare


# --- Failure posture ------------------------------------------------------------


def test_write_failure_never_breaks_a_call_and_disables_the_recorder(tmp_path):
    recorder = TelemetryRecorder(tmp_path / "no" / "such" / "dir" / "log.jsonl")
    payload = call_text(CORPUS, "get_summary", {}, recorder=recorder)
    assert json.loads(payload)["schema_version"] == "1"
    assert recorder._disabled is True
    recorder.record({"schema_version": "1"})  # disabled: a no-op, never raises
    assert not recorder.path.exists()


def test_exception_is_recorded_then_reraised(tmp_path):
    recorder = make_recorder(tmp_path)

    def boom() -> str:
        raise RuntimeError("tool failure")

    with pytest.raises(RuntimeError):
        observe(recorder, "get_summary", boom)
    (event,) = events_in(recorder)
    assert event["outcome"] == "exception"
    assert "error" not in event


def test_observe_without_recorder_is_the_bare_call():
    assert observe(None, "get_summary", lambda: "payload") == "payload"


def test_create_recorder_rotates_an_oversized_log(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    log = telemetry_path()
    log.parent.mkdir(parents=True)
    log.write_text("x" * (MAX_LOG_BYTES + 1), encoding="utf-8")
    recorder = create_recorder()
    rotated = log.with_suffix(log.suffix + ".1")
    assert rotated.exists()
    assert not log.exists()
    recorder.record({"schema_version": "1"})
    events, _ = read_events(log)
    assert len(events) == 1


# --- Read-back -------------------------------------------------------------------


def test_read_events_tolerates_corruption_and_counts_skips(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(
        '{"schema_version": "1", "tool": "get_summary"}\n'
        "not json at all\n"
        "[1, 2, 3]\n"
        "\n"
        '{"schema_version": "1", "tool": "get_artifact"}\n',
        encoding="utf-8",
    )
    events, skipped = read_events(log)
    assert [ev["tool"] for ev in events] == ["get_summary", "get_artifact"]
    assert skipped == 2


def test_read_events_missing_file_is_an_empty_log(tmp_path):
    assert read_events(tmp_path / "absent.jsonl") == ([], 0)


def test_summarize_aggregates_per_tool(tmp_path):
    recorder = make_recorder(tmp_path)
    call_text(CORPUS, "get_summary", {}, recorder=recorder)
    call_text(CORPUS, "get_summary", {}, recorder=recorder)
    call_text(CORPUS, "get_artifact", {"id": "RAC-ZZZZZZZZZZZZ"}, recorder=recorder)
    summary = summarize(recorder.path)
    assert summary.event_count == 3
    assert summary.session_count == 1
    assert summary.skipped_lines == 0
    assert summary.first_ts is not None and summary.last_ts is not None
    by_tool = {usage.tool: usage for usage in summary.tools}
    assert sorted(by_tool) == ["get_artifact", "get_summary"]
    assert by_tool["get_summary"].calls == 2
    assert by_tool["get_summary"].errors == 0
    assert by_tool["get_artifact"].errors == 1


def test_summarize_empty_log_is_a_valid_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    summary = summarize()
    assert summary.event_count == 0
    assert summary.session_count == 0
    assert summary.first_ts is None and summary.last_ts is None
    assert summary.tools == []


# --- Share flow ------------------------------------------------------------------


def test_share_url_round_trips_the_summary_without_the_path(tmp_path):
    recorder = make_recorder(tmp_path)
    call_text(CORPUS, "get_summary", {}, recorder=recorder)
    summary = summarize(recorder.path)
    url = share_url(summary)
    base, _, query = url.partition("?")
    assert base == SHARE_ISSUE_URL
    params = urllib.parse.parse_qs(query)
    assert params["template"] == [SHARE_TEMPLATE]
    report = json.loads(params["report"][0])
    expected = summary.to_dict()
    del expected["path"]  # the local log path stays out of the shared report
    assert report == expected


# --- CLI surface -----------------------------------------------------------------


def test_cli_mcp_stats_missing_log_exits_zero_with_guidance(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert main(["mcp-stats"]) == 0
    out = capsys.readouterr().out
    assert "No telemetry recorded." in out
    assert "rac mcp --telemetry" in out


def test_cli_mcp_stats_json_shape(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    recorder = create_recorder()
    call_text(CORPUS, "get_summary", {}, recorder=recorder)
    assert main(["mcp-stats", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["event_count"] == 1
    assert payload["tools"][0]["tool"] == "get_summary"


def test_cli_mcp_stats_share_prints_the_url(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert main(["mcp-stats", "--share"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith(SHARE_ISSUE_URL + "?")


def test_cli_mcp_stats_share_and_json_are_mutually_exclusive(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        main(["mcp-stats", "--json", "--share"])
    assert exc.value.code == 2


def test_cli_mcp_telemetry_flag_defaults_off():
    from rac.cli import build_parser

    args = build_parser().parse_args(["mcp"])
    assert args.telemetry is False
