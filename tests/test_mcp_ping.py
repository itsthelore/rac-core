"""Anonymous usage ping contracts — consented, pinned, one module wide (v0.10.6).

The battery pins ADR-041's shape: nothing sends without recorded consent and a
configured key; the payload is the entire transmission, asserted key-for-key
at both levels with no path, salt, or content anywhere in it; failures are
swallowed with exactly one attempt per 24 hours and no retries; the
active-repo file holds salted digests only; and the consent record tolerates
corruption by meaning No. The server hook is announced on stderr and is
independent of the local ``--telemetry`` flag.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from rac import __version__, consent
from rac.cli import main
from rac.consent import (
    Consent,
    consent_path,
    consent_recorded,
    load_consent,
    opt_in,
    opt_out,
    save_consent,
)
from rac.mcp import ping, server
from rac.mcp.ping import (
    ACTIVE_REPOS_FILENAME,
    PING_EVENT,
    SOCKET_TIMEOUT_SECONDS,
    _tick,
    active_repo_count,
    build_payload,
    mark_pinged,
    record_active_repo,
    repo_digest,
    send_ping,
    should_ping,
    start_ping_thread,
)

# The pinned payload key sets (ADR-041). Adding a key is a recorded decision.
PAYLOAD_KEYS = {"api_key", "event", "timestamp", "properties"}
PROPERTY_KEYS = {
    "distinct_id",
    "$process_person_profile",
    "schema_version",
    "rac_version",
    "active_repos",
}

NOW = datetime(2026, 6, 12, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def consented() -> Consent:
    return opt_in()


# --- Consent record -------------------------------------------------------------


def test_consent_round_trip_preserves_all_fields():
    saved = Consent(share_usage=True, install_id="a" * 32, salt="b" * 32, consented_at="t")
    save_consent(saved)
    assert load_consent() == saved


@pytest.mark.parametrize("content", ["", "not json", "[1, 2]", '"a string"'])
def test_corrupt_or_non_dict_consent_means_no_consent(content):
    consent_path().parent.mkdir(parents=True, exist_ok=True)
    consent_path().write_text(content, encoding="utf-8")
    assert load_consent() == Consent()


def test_missing_consent_file_means_no_consent_and_not_recorded():
    assert load_consent() == Consent()
    assert consent_recorded() is False


def test_save_over_unwritable_directory_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-file"))
    (tmp_path / "config-file").write_text("a file, not a directory", encoding="utf-8")
    save_consent(Consent(share_usage=True))  # must not raise


def test_opt_in_mints_ids_and_preserves_them_across_toggles():
    first = opt_in()
    assert len(first.install_id) == 32 and len(first.salt) == 32
    assert first.share_usage is True
    opt_out()
    again = opt_in()
    assert again.install_id == first.install_id
    assert again.salt == first.salt


def test_opt_out_keeps_the_record_and_flips_the_choice():
    first = opt_in()
    record = opt_out()
    assert record.share_usage is False
    assert record.install_id == first.install_id
    assert consent_recorded() is True


# --- rac telemetry CLI ------------------------------------------------------------


def test_cli_telemetry_on_records_consent_and_prints_install_id(capsys):
    assert main(["telemetry", "on"]) == 0
    out = capsys.readouterr().out
    record = load_consent()
    assert record.share_usage is True
    assert record.install_id in out
    assert "Never paths, queries, or content" in out
    assert "no PostHog key configured" not in out  # the key ships configured


def test_cli_telemetry_on_names_the_kill_switch_when_key_is_empty(monkeypatch, capsys):
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "")
    assert main(["telemetry", "on"]) == 0
    assert "no PostHog key configured" in capsys.readouterr().out


def test_cli_telemetry_off_and_default_status(capsys):
    main(["telemetry", "on"])
    capsys.readouterr()
    assert main(["telemetry", "off"]) == 0
    assert "Nothing will be sent" in capsys.readouterr().out
    assert main(["telemetry"]) == 0  # default action is status
    out = capsys.readouterr().out
    assert "Sharing: off" in out
    assert "not configured" not in out  # the key ships configured


def test_cli_telemetry_status_names_the_kill_switch_when_key_is_empty(monkeypatch, capsys):
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "")
    assert main(["telemetry"]) == 0
    assert "not configured" in capsys.readouterr().out


def test_cli_telemetry_invalid_action_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        main(["telemetry", "bogus"])
    assert exc.value.code == 2


# --- Payload (the entire transmission, pinned) --------------------------------------


def test_payload_pinned_key_for_key():
    payload = build_payload("c" * 32, 2, NOW)
    assert set(payload) == PAYLOAD_KEYS
    assert set(payload["properties"]) == PROPERTY_KEYS
    assert payload["event"] == PING_EVENT
    assert payload["timestamp"] == "2026-06-12T12:00:00Z"
    assert payload["properties"]["distinct_id"] == "c" * 32
    # Anonymous events: PostHog must create no person profile (ADR-041).
    assert payload["properties"]["$process_person_profile"] is False
    assert payload["properties"]["schema_version"] == "1"
    assert payload["properties"]["rac_version"] == __version__
    assert payload["properties"]["active_repos"] == 2


def test_payload_carries_no_path_salt_or_content(tmp_path):
    record = consented()
    record_active_repo(str(tmp_path), record.salt)
    payload = build_payload(record.install_id, active_repo_count(), NOW)
    text = json.dumps(payload)
    assert str(tmp_path) not in text
    assert record.salt not in text
    # No value is a filesystem path; the endpoint URL lives outside the body.
    for value in (*payload.values(), *payload["properties"].values()):
        assert "/" not in str(value)


# --- Wire behavior -----------------------------------------------------------------


def test_send_ping_posts_the_payload_to_the_endpoint(monkeypatch):
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.get_header("Content-type")
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    payload = build_payload("d" * 32, 0, NOW)
    send_ping(payload)
    assert captured["url"] == consent.POSTHOG_ENDPOINT
    assert captured["body"] == payload
    assert captured["content_type"] == "application/json"
    assert captured["timeout"] == SOCKET_TIMEOUT_SECONDS


@pytest.mark.parametrize("error", [OSError("refused"), ValueError("odd"), Exception("boom")])
def test_failures_swallowed_with_exactly_one_attempt(monkeypatch, error):
    calls = []

    def _raise(request, timeout=None):
        calls.append(request)
        raise error

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    _tick("e" * 32)  # must not raise
    assert len(calls) == 1
    # The marker is written after the failed attempt: no retry within 24h.
    _tick("e" * 32)
    assert len(calls) == 1


def test_tick_sends_once_per_24_hours(monkeypatch):
    calls = []
    monkeypatch.setattr(ping, "send_ping", lambda payload: calls.append(payload))
    _tick("f" * 32)
    _tick("f" * 32)
    assert len(calls) == 1


def test_should_ping_honors_the_marker():
    now = datetime.now(UTC)
    assert should_ping(now) is True  # no marker
    mark_pinged(now - timedelta(hours=1))
    assert should_ping(now) is False
    mark_pinged(now - timedelta(hours=25))
    assert should_ping(now) is True


def test_corrupt_marker_means_never_pinged(monkeypatch, tmp_path):
    marker = ping._state_dir() / ping.LAST_PING_FILENAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("not a timestamp", encoding="utf-8")
    assert should_ping(datetime.now(UTC)) is True


# --- Thread gating ------------------------------------------------------------------


def test_no_thread_without_consent_or_install_id_or_key(monkeypatch):
    assert start_ping_thread(Consent()) is None
    assert start_ping_thread(Consent(share_usage=True)) is None  # no install id
    record = consented()
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "")
    assert start_ping_thread(record) is None  # empty-key kill switch


def test_thread_is_daemon_when_everything_is_configured(monkeypatch):
    record = consented()
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "phc_test")
    monkeypatch.setattr(ping, "_tick", lambda install_id: None)
    thread = start_ping_thread(record)
    assert thread is not None
    assert thread.daemon is True


# --- Active repos --------------------------------------------------------------------


def test_active_repo_digests_are_salted_and_paths_never_stored(tmp_path):
    root = str(tmp_path / "repo")
    assert repo_digest(root, "salt-a") == repo_digest(root, "salt-a")
    assert repo_digest(root, "salt-a") != repo_digest(root, "salt-b")
    record_active_repo(root, "salt-a")
    record_active_repo(root, "salt-a")  # idempotent
    assert active_repo_count() == 1
    stored = (ping._state_dir() / ACTIVE_REPOS_FILENAME).read_text(encoding="utf-8")
    assert root not in stored
    assert "salt-a" not in stored


def test_active_repos_prune_past_the_window(tmp_path):
    path = ping._state_dir() / ACTIVE_REPOS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    stale = (datetime.now(UTC).date() - timedelta(days=31)).isoformat()
    path.write_text(json.dumps({"old" * 16: stale}), encoding="utf-8")
    assert active_repo_count() == 0
    record_active_repo(str(tmp_path), "salt")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 1  # the stale entry was pruned on write


def test_corrupt_active_repo_file_counts_zero_and_recovers(tmp_path):
    path = ping._state_dir() / ACTIVE_REPOS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("garbage", encoding="utf-8")
    assert active_repo_count() == 0
    record_active_repo(str(tmp_path), "salt")
    assert active_repo_count() == 1


# --- Server hook ----------------------------------------------------------------------


def test_sharing_off_is_silent(capsys):
    server._maybe_start_sharing(".")
    assert capsys.readouterr().err == ""


def test_sharing_on_with_key_announces_and_records_the_repo(monkeypatch, tmp_path, capsys):
    record = consented()
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "phc_test")
    monkeypatch.setattr(ping, "_tick", lambda install_id: None)
    server._maybe_start_sharing(str(tmp_path))
    captured = capsys.readouterr()
    assert captured.out == "", "stdout belongs to the MCP protocol"
    assert "anonymous usage sharing on" in captured.err
    assert "rac telemetry off" in captured.err
    assert repo_digest(str(tmp_path), record.salt) in (
        (ping._state_dir() / ACTIVE_REPOS_FILENAME).read_text(encoding="utf-8")
    )


def test_sharing_on_without_key_says_nothing_will_be_sent(monkeypatch, capsys):
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "")
    consented()
    server._maybe_start_sharing(".")
    captured = capsys.readouterr()
    assert "no PostHog key configured" in captured.err
    assert "nothing will be sent" in captured.err


# --- Enterprise hard-lock (ADR-086) ---------------------------------------------


def test_off_enterprise_records_lock_and_turns_sharing_off(capsys):
    main(["telemetry", "on"])
    capsys.readouterr()
    assert main(["telemetry", "off", "--enterprise"]) == 0
    assert "enterprise-locked" in capsys.readouterr().out
    record = load_consent()
    assert record.enterprise_locked is True
    assert record.share_usage is False
    # The install id survives so a later unlock-and-opt-in stays continuous.
    assert record.install_id


def test_on_is_refused_while_enterprise_locked(capsys):
    main(["telemetry", "on"])
    main(["telemetry", "off", "--enterprise"])
    capsys.readouterr()
    assert main(["telemetry", "on"]) == 2
    assert "enterprise telemetry lock" in capsys.readouterr().err
    # Refusal does not flip the record back on.
    record = load_consent()
    assert record.share_usage is False
    assert record.enterprise_locked is True


def test_ping_thread_suppressed_while_locked(monkeypatch):
    # Even with consent, an install id, and a configured key, the lock wins.
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "phc_test")
    locked = Consent(share_usage=True, install_id="d" * 32, salt="e" * 32, enterprise_locked=True)
    assert start_ping_thread(locked) is None


def test_server_does_not_start_sharing_while_locked(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(consent, "POSTHOG_API_KEY", "phc_test")
    monkeypatch.setattr(ping, "_tick", lambda install_id: None)
    # A hand-edited record with sharing on but locked: the lock still wins.
    save_consent(
        Consent(share_usage=True, install_id="d" * 32, salt="e" * 32, enterprise_locked=True)
    )
    server._maybe_start_sharing(str(tmp_path))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""  # nothing announced, nothing started


def test_unlock_removes_lock_and_allows_opt_in(capsys):
    main(["telemetry", "off", "--enterprise"])
    capsys.readouterr()
    assert main(["telemetry", "off", "--enterprise", "--unlock"]) == 0
    assert "lock removed" in capsys.readouterr().out.lower()
    assert load_consent().enterprise_locked is False
    assert main(["telemetry", "on"]) == 0
    assert load_consent().share_usage is True


def test_plain_off_preserves_enterprise_lock(capsys):
    main(["telemetry", "off", "--enterprise"])
    capsys.readouterr()
    # A plain 'off' must never silently clear the lock.
    assert main(["telemetry", "off"]) == 0
    assert load_consent().enterprise_locked is True


def test_status_reports_locked_enterprise(capsys):
    main(["telemetry", "off", "--enterprise"])
    capsys.readouterr()
    assert main(["telemetry"]) == 0
    out = capsys.readouterr().out
    assert "Sharing: locked (enterprise)" in out
    assert "Enterprise lock: on" in out


def test_unlock_requires_enterprise(capsys):
    assert main(["telemetry", "off", "--unlock"]) == 2
    assert "--unlock requires --enterprise" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["on", "status"])
def test_enterprise_flags_rejected_outside_off(action, capsys):
    assert main(["telemetry", action, "--enterprise"]) == 2
    assert "only valid with 'rac telemetry off'" in capsys.readouterr().err


def test_consent_round_trip_preserves_enterprise_lock():
    saved = Consent(
        share_usage=False,
        install_id="a" * 32,
        salt="b" * 32,
        consented_at="t",
        enterprise_locked=True,
    )
    save_consent(saved)
    assert load_consent() == saved
