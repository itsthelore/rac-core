"""Read-access audit recorder contracts — content-bearing, local-only, fail-loud.

The battery pins ADR-084's shape: default-ABSENT (no recorder, no file, and the
response byte-identical to bare — the strict-superset guarantee); one pinned line
per read-tool call carrying the principal, the query verbatim, and the returned
artifact IDs but never a body; the principal is attributable (git identity / env /
``unattributed``); the ``audit:`` config stanza parses or raises; and a write
failure is fail-loud, refusing the call under ``on_write_error: block``.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

import pytest
from conftest import fixture_path

from rac.mcp import audit
from rac.mcp.audit import AuditConfig, AuditRecorder, MalformedAuditConfig
from rac.mcp.budget import DEFAULT_BUDGET
from rac.mcp.server import build_server

CORPUS = fixture_path("mcp", "corpus")

DEC = "RAC-MCPDEC000001"
RDM = "RAC-MCPRDM000001"
REQ = "RAC-MCPREQ000001"

# The pinned audit event field set, in emission order (ADR-084).
AUDIT_FIELDS = [
    "schema_version",
    "ts",
    "session",
    "principal",
    "tool",
    "query",
    "returned",
    "outcome",
    "duration_ms",
]

TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def make_recorder(
    tmp_path: Path, principal: str = "Tester <t@example.com>", on_write_error: str = "warn"
) -> AuditRecorder:
    return AuditRecorder(tmp_path / "audit.jsonl", principal, on_write_error)


def call_text(
    root: str,
    tool: str,
    args: dict,
    budget: int = DEFAULT_BUDGET,
    audit_recorder: AuditRecorder | None = None,
) -> str:
    server = build_server(root, budget=budget, audit_recorder=audit_recorder)
    contents, _structured = asyncio.run(server.call_tool(tool, args))
    assert len(contents) == 1
    return contents[0].text


def events_in(recorder: AuditRecorder) -> list[dict]:
    return [json.loads(line) for line in recorder.path.read_text().splitlines() if line.strip()]


# --- Default-absent: the strict-superset guarantee ------------------------------


def test_default_absent_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    for tool, args in [
        ("get_artifact", {"id": DEC}),
        ("search_artifacts", {"query": "event"}),
        ("get_related", {"id": DEC}),
        ("get_summary", {}),
    ]:
        call_text(CORPUS, tool, args)  # no audit_recorder
    assert not audit.audit_path().exists()


@pytest.mark.parametrize(
    "tool,args,budget",
    [
        ("get_artifact", {"id": DEC}, DEFAULT_BUDGET),
        ("get_artifact", {"id": "RAC-DOESNOTEXIST1"}, DEFAULT_BUDGET),  # error
        ("get_artifact", {"id": DEC}, 200),  # truncated
        ("search_artifacts", {"query": "event"}, DEFAULT_BUDGET),
        ("find_decisions", {"topic": "event"}, DEFAULT_BUDGET),
        ("get_related", {"id": DEC}, DEFAULT_BUDGET),
        ("get_summary", {}, DEFAULT_BUDGET),
    ],
)
def test_payload_byte_identical_with_and_without_recorder(tmp_path, tool, args, budget):
    bare = call_text(CORPUS, tool, args, budget=budget)
    recorded = call_text(CORPUS, tool, args, budget=budget, audit_recorder=make_recorder(tmp_path))
    assert recorded == bare


# --- The recorded contract ------------------------------------------------------


def test_each_tool_records_one_pinned_event(tmp_path):
    recorder = make_recorder(tmp_path)
    tools = [
        ("get_artifact", {"id": DEC}),
        ("search_artifacts", {"query": "event"}),
        ("get_summary", {}),
    ]
    for tool, args in tools:
        call_text(CORPUS, tool, args, audit_recorder=recorder)
    events = events_in(recorder)
    assert [ev["tool"] for ev in events] == [tool for tool, _ in tools]
    for ev in events:
        assert list(ev) == AUDIT_FIELDS
        assert ev["schema_version"] == "1"
        assert TS_PATTERN.match(ev["ts"])
        assert ev["session"] == recorder.session
        assert ev["principal"] == "Tester <t@example.com>"
        assert ev["outcome"] == "ok"
        assert isinstance(ev["duration_ms"], int)


def test_query_is_recorded_verbatim(tmp_path):
    recorder = make_recorder(tmp_path)
    call_text(CORPUS, "search_artifacts", {"query": "soft delete"}, audit_recorder=recorder)
    event = events_in(recorder)[0]
    assert event["query"] == {"query": "soft delete", "type": None}


@pytest.mark.parametrize(
    "tool,args,expected",
    [
        ("get_artifact", {"id": DEC}, [DEC]),
        ("search_artifacts", {"query": "event"}, [DEC, RDM]),
        ("find_decisions", {"topic": "event"}, [DEC]),
        ("get_related", {"id": DEC}, [DEC, RDM, REQ]),
        ("get_summary", {}, []),
    ],
)
def test_returned_ids_per_tool(tmp_path, tool, args, expected):
    recorder = make_recorder(tmp_path)
    call_text(CORPUS, tool, args, audit_recorder=recorder)
    assert events_in(recorder)[0]["returned"] == expected


def test_no_artifact_body_is_recorded(tmp_path):
    recorder = make_recorder(tmp_path)
    payload = json.loads(call_text(CORPUS, "get_artifact", {"id": DEC}, audit_recorder=recorder))
    body = payload["content"]
    assert body  # the tool really did return the body...
    raw = recorder.path.read_text()
    assert body not in raw  # ...but the audit line records only the ID, never it


def test_not_found_records_error_outcome_and_empty_returned(tmp_path):
    recorder = make_recorder(tmp_path)
    call_text(CORPUS, "get_artifact", {"id": "RAC-DOESNOTEXIST1"}, audit_recorder=recorder)
    event = events_in(recorder)[0]
    assert event["outcome"] == "error"
    assert event["returned"] == []


def test_exception_is_recorded_and_reraised(tmp_path):
    recorder = make_recorder(tmp_path)

    def boom() -> str:
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError):
        audit.observe(recorder, "get_artifact", {"id": "X"}, boom)
    event = events_in(recorder)[0]
    assert event["outcome"] == "exception"
    assert event["returned"] == []


# --- Principal: attributable, not authenticated ---------------------------------


def test_principal_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("RAC_AUDIT_PRINCIPAL", "CI Bot <ci@example.com>")
    assert audit.resolve_principal(str(tmp_path)) == "CI Bot <ci@example.com>"


def test_principal_defaults_to_git_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("RAC_AUDIT_PRINCIPAL", raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Ada Lovelace"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "ada@example.com"], check=True
    )
    assert audit.resolve_principal(str(tmp_path)) == "Ada Lovelace <ada@example.com>"


def test_principal_unattributed_without_git_or_env(tmp_path, monkeypatch):
    monkeypatch.delenv("RAC_AUDIT_PRINCIPAL", raising=False)
    monkeypatch.setattr(audit, "_git_identity", lambda root: None)
    assert audit.resolve_principal(str(tmp_path)) == "unattributed"


# --- Config + path resolution ---------------------------------------------------


def _write_config(tmp_path: Path, body: str) -> None:
    (tmp_path / ".rac").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".rac" / "config.yaml").write_text(body, encoding="utf-8")


def test_load_audit_config_absent_is_disabled(tmp_path):
    assert audit.load_audit_config(str(tmp_path)).enabled is False


def test_load_audit_config_parses_the_stanza(tmp_path):
    _write_config(
        tmp_path,
        "audit:\n  enabled: true\n  path: /var/log/lore/audit.jsonl\n  on_write_error: block\n",
    )
    config = audit.load_audit_config(str(tmp_path))
    assert config.enabled is True
    assert config.path == "/var/log/lore/audit.jsonl"
    assert config.on_write_error == "block"


@pytest.mark.parametrize(
    "body",
    [
        "audit: not-a-mapping\n",
        "audit:\n  enabled: yes-please\n",
        "audit:\n  enabled: true\n  on_write_error: shout\n",
        "audit:\n  enabled: true\n  path: 42\n",
    ],
)
def test_load_audit_config_malformed_raises(tmp_path, body):
    _write_config(tmp_path, body)
    with pytest.raises(MalformedAuditConfig):
        audit.load_audit_config(str(tmp_path))


def test_audit_path_resolution_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("RAC_AUDIT_PATH", raising=False)
    # Default: XDG state dir.
    assert audit.audit_path(None) == tmp_path / "state" / "rac" / "audit.jsonl"
    # Config path beats the default.
    configured = AuditConfig(enabled=True, path=str(tmp_path / "c.jsonl"), on_write_error="warn")
    assert audit.audit_path(configured) == tmp_path / "c.jsonl"
    # Env beats the config path.
    monkeypatch.setenv("RAC_AUDIT_PATH", str(tmp_path / "env.jsonl"))
    assert audit.audit_path(configured) == tmp_path / "env.jsonl"


def test_create_recorder_disabled_returns_none(tmp_path):
    config = AuditConfig(enabled=False, path="", on_write_error="warn")
    assert audit.create_recorder(config, str(tmp_path)) is None


# --- Fail-loud write handling ---------------------------------------------------


def test_warn_mode_keeps_serving_and_warns_on_write_failure(tmp_path, capsys):
    # Point the log at a directory so every append raises OSError.
    blocked = tmp_path / "audit.jsonl"
    blocked.mkdir()
    recorder = AuditRecorder(blocked, "Tester <t@example.com>", "warn")
    out = audit.observe(recorder, "get_summary", {}, lambda: '{"ok": true}')
    assert out == '{"ok": true}'  # warn mode still serves the payload
    assert "audit write failed" in capsys.readouterr().err


def test_block_mode_refuses_the_call_on_write_failure(tmp_path, capsys):
    blocked = tmp_path / "audit.jsonl"
    blocked.mkdir()
    recorder = AuditRecorder(blocked, "Tester <t@example.com>", "block")
    out = audit.observe(recorder, "get_artifact", {"id": DEC}, lambda: '{"id": "X"}')
    data = json.loads(out)
    assert data["error"] == "audit-unavailable"
    assert data["tool"] == "get_artifact"
    assert "refusing tool calls" in capsys.readouterr().err
