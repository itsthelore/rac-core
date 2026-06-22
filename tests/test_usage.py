"""CLI usage telemetry tests (v0.24, WS-E; ADR-046).

Recording is consent-gated, content-free, and write-only: the named absent
fields (argv, paths, ids) are a test, not a comment.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rac import consent, usage
from rac.cli import main

EVENT_KEYS = {"schema_version", "ts", "session", "command", "outcome", "duration_ms"}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


def _enable(consent_dir: Path) -> None:
    consent.opt_in()  # records share_usage=True at $XDG_CONFIG_HOME/rac/telemetry.json


def test_no_recording_without_consent(isolated):
    usage.record_command("validate", usage.OUTCOME_OK, 5)
    assert not usage.usage_path().exists()


def test_records_one_event_with_consent(isolated):
    _enable(isolated)
    usage.record_command("validate", usage.OUTCOME_OK, 5)
    events = usage.read_usage()
    assert len(events) == 1
    assert set(events[0]) == EVENT_KEYS
    assert events[0]["command"] == "validate"
    assert events[0]["outcome"] == "ok"


def test_event_is_content_free_through_real_dispatch(isolated, capsys):
    # Run a real command whose args carry a path; the recorded event must not
    # leak the path, argv, or any id — only the pinned fields (ADR-046).
    _enable(isolated)
    secret_path = str(Path(__file__))  # a real path passed as the positional
    main(["validate", secret_path])
    raw = usage.usage_path().read_text(encoding="utf-8")
    assert secret_path not in raw
    event = json.loads(raw.splitlines()[-1])
    assert set(event) == EVENT_KEYS
    assert event["command"] == "validate"


def test_recording_does_not_change_exit_code(isolated):
    _enable(isolated)
    # A non-existent file makes validate exit non-zero (SystemExit); recording in
    # the finally clause must still happen and must not swallow or alter the exit.
    with pytest.raises(SystemExit) as exc:
        main(["validate", str(isolated / "nope.md")])
    assert exc.value.code != 0
    event = json.loads(usage.usage_path().read_text(encoding="utf-8").splitlines()[-1])
    assert event["command"] == "validate"
    assert event["outcome"] in ("error", "exception")


def test_empty_log_summarizes_without_error(isolated):
    summary = usage.summarize_usage()
    assert summary.total == 0 and summary.sessions == 0 and summary.commands == []


def test_summary_counts_per_command_and_sessions(isolated):
    _enable(isolated)
    for _ in range(3):
        usage.record_command("validate", usage.OUTCOME_OK, 1)
    usage.record_command("review", usage.OUTCOME_ERROR, 1)
    summary = usage.summarize_usage()
    assert summary.total == 4
    assert summary.sessions == 1  # one process == one session
    by_command = {c.command: (c.calls, c.errors) for c in summary.commands}
    assert by_command == {"validate": (3, 0), "review": (1, 1)}
    assert sum(summary.recent.values()) == 4  # the recent-activity trend


def test_usage_command_renders_and_is_advisory(isolated, capsys):
    _enable(isolated)
    usage.record_command("validate", usage.OUTCOME_OK, 1)
    rc = main(["usage"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CLI commands" in out and "validate" in out


def test_usage_command_json(isolated, capsys):
    _enable(isolated)
    usage.record_command("validate", usage.OUTCOME_OK, 1)
    main(["usage", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["cli"]["total"] == 1
    assert "guide" in data  # unified read-back covers both logs


def test_usage_share_url_is_local_only(isolated, capsys):
    _enable(isolated)
    usage.record_command("validate", usage.OUTCOME_OK, 1)
    main(["usage", "--share"])
    url = capsys.readouterr().out.strip()
    assert url.startswith("https://github.com/itsthelore/rac-core/issues/new")
    assert str(isolated) not in url  # no local path in the shared payload
