"""Tests for org endpoint wiring — `rac init --org-endpoint <url>` (ADR-117).

Org wiring is an explicit operator action, not creation-time configuration: it
applies on fresh and already-initialized repositories alike, merges into an
existing client config touching only the `lore-org` key, is idempotent, and
without the flag `rac init` is byte-identical to the previous engine
(`rac-org-endpoint-wiring`).
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.init import InvalidOrgEndpoint, init_repository
from rac.services.profiles import (
    ORG_SERVER_KEY,
    MalformedClientConfig,
    org_server_entry,
    write_org_endpoint,
)

_URL = "https://lore.example.com/mcp"
_ENTRY = {"type": "http", "url": _URL}


def _mcp(tmp_path, name=".mcp.json") -> dict:
    return json.loads((tmp_path / name).read_text(encoding="utf-8"))


# --- the entry shape ----------------------------------------------------------


def test_org_server_entry_is_the_streamable_http_shape():
    assert ORG_SERVER_KEY == "lore-org"
    assert org_server_entry(_URL) == _ENTRY


# --- fresh init ---------------------------------------------------------------


def test_fresh_init_writes_both_client_configs(tmp_path):
    result = init_repository(str(tmp_path), key="ACME", org_endpoint=_URL)
    assert result.created
    assert result.org_endpoint == _URL
    assert _mcp(tmp_path) == {"mcpServers": {ORG_SERVER_KEY: _ENTRY}}
    assert json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8")) == {
        "mcpServers": {ORG_SERVER_KEY: _ENTRY}
    }
    assert {str(tmp_path / ".mcp.json"), str(tmp_path / ".cursor" / "mcp.json")} == set(
        result.files_written
    )


def test_profile_and_org_endpoint_compose(tmp_path):
    # The local `lore` server (profile wiring) and the org endpoint side by side.
    result = init_repository(str(tmp_path), key="ACME", profile="enterprise", org_endpoint=_URL)
    servers = _mcp(tmp_path)["mcpServers"]
    assert servers["lore"] == {"command": "rac", "args": ["mcp", "--root", "."]}
    assert servers[ORG_SERVER_KEY] == _ENTRY
    # Each path reported once even though profile wrote and org merge rewrote it.
    assert sorted(result.files_written) == sorted(
        {str(tmp_path / ".mcp.json"), str(tmp_path / ".cursor" / "mcp.json")}
    )


# --- already-initialized repositories (the fleet rollout path) ----------------


def test_org_endpoint_applies_to_initialized_repo(tmp_path):
    init_repository(str(tmp_path), key="ACME")
    result = init_repository(str(tmp_path), key="ACME", org_endpoint=_URL)
    assert not result.created
    assert result.org_endpoint == _URL
    assert _mcp(tmp_path)["mcpServers"][ORG_SERVER_KEY] == _ENTRY
    # .rac/config.yaml is untouched by org wiring.
    config = (tmp_path / ".rac" / "config.yaml").read_text(encoding="utf-8")
    assert config == "repository_key: ACME\n"


def test_merge_preserves_user_content(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {"mine": {"command": "other"}},
                "custom": {"kept": True},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    written = write_org_endpoint(str(tmp_path), _URL)
    data = _mcp(tmp_path)
    assert data["mcpServers"]["mine"] == {"command": "other"}
    assert data["custom"] == {"kept": True}
    assert data["mcpServers"][ORG_SERVER_KEY] == _ENTRY
    assert str(tmp_path / ".mcp.json") in written


def test_differing_org_url_is_updated_in_place(tmp_path):
    write_org_endpoint(str(tmp_path), "https://old.example.com/mcp")
    write_org_endpoint(str(tmp_path), _URL)
    assert _mcp(tmp_path)["mcpServers"][ORG_SERVER_KEY]["url"] == _URL


# --- idempotency --------------------------------------------------------------


def test_second_run_writes_nothing(tmp_path):
    first = write_org_endpoint(str(tmp_path), _URL)
    assert len(first) == 2
    before = (tmp_path / ".mcp.json").stat().st_mtime_ns
    second = write_org_endpoint(str(tmp_path), _URL)
    assert second == []
    assert (tmp_path / ".mcp.json").stat().st_mtime_ns == before


def test_idempotent_init_reports_no_files(tmp_path):
    init_repository(str(tmp_path), key="ACME", org_endpoint=_URL)
    result = init_repository(str(tmp_path), key="ACME", org_endpoint=_URL)
    assert result.files_written == ()


# --- failure modes ------------------------------------------------------------


def test_non_http_url_rejected_before_any_write(tmp_path):
    with pytest.raises(InvalidOrgEndpoint):
        init_repository(str(tmp_path), key="ACME", org_endpoint="lore.example.com/mcp")
    assert not (tmp_path / ".rac").exists()
    assert not (tmp_path / ".mcp.json").exists()


def test_unparseable_config_errors_with_no_partial_writes(tmp_path):
    (tmp_path / ".mcp.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(MalformedClientConfig) as exc:
        write_org_endpoint(str(tmp_path), _URL)
    assert ".mcp.json" in str(exc.value)
    # No partial writes: the parseable-but-unwritten Cursor target stays absent.
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == "{not json"
    assert not (tmp_path / ".cursor").exists()


def test_non_object_mcp_servers_rejected(tmp_path):
    (tmp_path / ".mcp.json").write_text('{"mcpServers": []}\n', encoding="utf-8")
    with pytest.raises(MalformedClientConfig):
        write_org_endpoint(str(tmp_path), _URL)


# --- without the flag: byte-identical to the previous engine ------------------


def test_plain_init_is_unchanged(tmp_path):
    result = init_repository(str(tmp_path), key="ACME")
    assert result.org_endpoint is None
    assert result.files_written == ()
    assert not (tmp_path / ".mcp.json").exists()


# --- CLI ----------------------------------------------------------------------


def test_cli_init_org_endpoint(tmp_path, capsys):
    rc = main(["init", str(tmp_path), "--key", "ACME", "--org-endpoint", _URL])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"Org endpoint: {_URL}" in out
    assert _mcp(tmp_path)["mcpServers"][ORG_SERVER_KEY] == _ENTRY


def test_cli_init_org_endpoint_json_contract(tmp_path, capsys):
    rc = main(["init", str(tmp_path), "--key", "ACME", "--org-endpoint", _URL, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["org_endpoint"] == _URL
    assert len(payload["files_written"]) == 2


def test_cli_json_org_endpoint_null_without_flag(tmp_path, capsys):
    rc = main(["init", str(tmp_path), "--key", "ACME", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["org_endpoint"] is None


def test_cli_rejects_bad_org_endpoint(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["init", str(tmp_path), "--key", "ACME", "--org-endpoint", "lore.example.com"])
    assert exc.value.code == 2
    assert "invalid org endpoint" in capsys.readouterr().err


def test_cli_malformed_client_config_is_operational_error(tmp_path, capsys):
    (tmp_path / ".mcp.json").write_text("{not json", encoding="utf-8")
    rc = main(["init", str(tmp_path), "--key", "ACME", "--org-endpoint", _URL])
    assert rc == 1
    assert "malformed MCP client config" in capsys.readouterr().err
