"""Tests for built-in init profiles — `rac init --profile <name>` (ADR-088).

A profile writes *configuration only* (never prose): the `.mcp.json` client wiring
and, for `enterprise`, an enforcement-policy stanza. It applies on a fresh init,
never overwrites an existing file, and leaves plain `rac init` unchanged.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.init import (
    InvalidProfile,
    init_repository,
    load_enforcement_policy,
    load_overrides,
)
from rac.services.profiles import MCP_JSON, PROFILE_NAMES, get_profile

_LORE_MCP = {"mcpServers": {"lore": {"command": "rac", "args": ["mcp", "--root", "."]}}}


def _config(tmp_path) -> str:
    return (tmp_path / ".rac" / "config.yaml").read_text(encoding="utf-8")


# --- the profile definitions -------------------------------------------------


def test_built_in_profile_names():
    assert PROFILE_NAMES == ("default", "enterprise")
    assert get_profile("nope") is None


def test_mcp_json_is_the_lore_server_wiring():
    # The emitted .mcp.json mirrors examples/cursor/mcp.example.json exactly.
    assert json.loads(MCP_JSON) == _LORE_MCP


# --- default profile: client wiring only -------------------------------------


def test_default_profile_writes_mcp_configs_only(tmp_path):
    result = init_repository(str(tmp_path), key="ACME", profile="default")
    assert result.created
    assert result.profile == "default"
    # Both client configs written; no policy stanza in .rac/config.yaml.
    assert (tmp_path / ".mcp.json").exists()
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8")) == _LORE_MCP
    assert _config(tmp_path) == "repository_key: ACME\n"
    assert load_enforcement_policy(str(tmp_path)).blocking == frozenset()
    assert {str(tmp_path / ".mcp.json"), str(tmp_path / ".cursor" / "mcp.json")} == set(
        result.files_written
    )


# --- enterprise profile: wiring + enforcement policy -------------------------


def test_enterprise_profile_writes_enforcement_policy(tmp_path):
    result = init_repository(str(tmp_path), key="ACME", profile="enterprise")
    assert result.profile == "enterprise"
    assert (tmp_path / ".mcp.json").exists()
    # The committed enforcement stanza loads as a policy (ADR-049): relationship
    # integrity findings block the gate.
    policy = load_enforcement_policy(str(tmp_path))
    assert "relationship-target-superseded" in policy.blocking
    assert "duplicate-artifact-identifier" in policy.blocking
    assert len(policy.blocking) == 8
    # Moderate preset: no validation-severity escalation.
    overrides = load_overrides(str(tmp_path))
    assert overrides.rules == {} and overrides.types == {}


def test_enterprise_config_is_valid_yaml_with_key_preserved(tmp_path):
    init_repository(str(tmp_path), key="ACME", profile="enterprise")
    body = _config(tmp_path)
    assert body.startswith("repository_key: ACME\n")
    assert "enforcement:" in body


def test_profile_and_ticketing_compose(tmp_path):
    init_repository(str(tmp_path), key="ACME", ticketing="jira", profile="enterprise")
    body = _config(tmp_path)
    assert "ticketing:\n  provider: jira\n" in body
    assert "enforcement:" in body


# --- plain init is unchanged -------------------------------------------------


def test_plain_init_writes_no_mcp_configs(tmp_path):
    result = init_repository(str(tmp_path), key="ACME")
    assert result.profile is None
    assert result.files_written == ()
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".cursor").exists()
    assert _config(tmp_path) == "repository_key: ACME\n"


# --- never overwrites, creation-time only ------------------------------------


def test_profile_never_overwrites_existing_mcp_json(tmp_path):
    (tmp_path / ".mcp.json").write_text('{"mine": true}\n', encoding="utf-8")
    result = init_repository(str(tmp_path), key="ACME", profile="default")
    # The user's file is preserved; only the absent Cursor config is written.
    assert json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8")) == {"mine": True}
    assert result.files_written == (str(tmp_path / ".cursor" / "mcp.json"),)


def test_profile_applies_only_on_fresh_init(tmp_path):
    init_repository(str(tmp_path), key="ACME")  # plain, no profile
    result = init_repository(str(tmp_path), key="ACME", profile="enterprise")
    assert not result.created
    # An already-initialized repo is left untouched — no policy, no client wiring.
    assert not (tmp_path / ".mcp.json").exists()
    assert "enforcement:" not in _config(tmp_path)


def test_unknown_profile_rejected(tmp_path):
    with pytest.raises(InvalidProfile):
        init_repository(str(tmp_path), key="ACME", profile="bespoke")


# --- CLI ---------------------------------------------------------------------


def test_cli_init_profile_enterprise(tmp_path, capsys):
    rc = main(["init", str(tmp_path), "--key", "ACME", "--profile", "enterprise"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Profile: enterprise" in out
    assert (tmp_path / ".mcp.json").exists()


def test_cli_init_profile_json_reports_files(tmp_path, capsys):
    rc = main(["init", str(tmp_path), "--key", "ACME", "--profile", "default", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "default"
    assert len(payload["files_written"]) == 2


def test_cli_init_rejects_unknown_profile(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["init", str(tmp_path), "--key", "ACME", "--profile", "bespoke"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
