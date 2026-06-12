"""Tests for rac.services.init and the `rac init` CLI (v0.7.11).

`rac init` establishes the repository identity namespace: fresh init writes
.rac/config.yaml, re-running with the same key is idempotent, a different key
is an error (never a silent rewrite), and discovery walks upward.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.init import (
    InvalidRepositoryKey,
    MalformedRepositoryConfig,
    RepositoryKeyConflict,
    init_repository,
    load_repository_config,
)

# --- service -----------------------------------------------------------------


def test_fresh_init_writes_config(tmp_path):
    result = init_repository(str(tmp_path), key="PROJ")
    assert result.created
    assert result.repository_key == "PROJ"
    config = tmp_path / ".rac" / "config.yaml"
    assert config.read_text(encoding="utf-8") == "repository_key: PROJ\n"


def test_reinit_same_key_is_idempotent(tmp_path):
    init_repository(str(tmp_path), key="RAC")
    result = init_repository(str(tmp_path), key="RAC")
    assert not result.created
    assert result.repository_key == "RAC"


def test_reinit_different_key_conflicts(tmp_path):
    init_repository(str(tmp_path), key="RAC")
    with pytest.raises(RepositoryKeyConflict):
        init_repository(str(tmp_path), key="OTHER")
    # The established key is untouched.
    assert load_repository_config(str(tmp_path)).repository_key == "RAC"


@pytest.mark.parametrize("key", ["", "R", "lowercase", "1LEADING", "TOOLONGKEY1", "BAD-CHARS"])
def test_invalid_keys_rejected(tmp_path, key):
    with pytest.raises(InvalidRepositoryKey):
        init_repository(str(tmp_path), key=key)


def test_malformed_config_is_reported(tmp_path):
    config_dir = tmp_path / ".rac"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("nonsense: true\n", encoding="utf-8")
    with pytest.raises(MalformedRepositoryConfig):
        init_repository(str(tmp_path), key="RAC")


def test_discovery_walks_upward(tmp_path):
    init_repository(str(tmp_path), key="RAC")
    nested = tmp_path / "docs" / "decisions"
    nested.mkdir(parents=True)
    config = load_repository_config(str(nested))
    assert config is not None
    assert config.repository_key == "RAC"


def test_discovery_returns_none_when_uninitialized(tmp_path):
    assert load_repository_config(str(tmp_path)) is None


# --- CLI ----------------------------------------------------------------------


def test_cli_init_defaults(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["init"])
    assert rc == 0
    assert "Initialized repository key RAC" in capsys.readouterr().out


def test_cli_init_json(tmp_path, capsys):
    rc = main(["init", str(tmp_path), "--key", "PROJ", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["repository_key"] == "PROJ"
    assert payload["created"] is True


def test_cli_init_idempotent_exit_0(tmp_path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    assert main(["init", str(tmp_path)]) == 0
    assert "Already initialized" in capsys.readouterr().out


def test_cli_init_conflict_exit_1(tmp_path, capsys):
    main(["init", str(tmp_path), "--key", "RAC"])
    rc = main(["init", str(tmp_path), "--key", "OTHER"])
    assert rc == 1
    assert "refusing to change" in capsys.readouterr().err


def test_cli_init_invalid_key_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["init", str(tmp_path), "--key", "bad"])
    assert exc.value.code == 2
    assert "invalid repository key" in capsys.readouterr().err


def test_cli_init_missing_directory_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["init", str(tmp_path / "nope")])
    assert exc.value.code == 2


# --- usage-sharing prompt (v0.10.5, ADR-041) ----------------------------------


def _tty(monkeypatch, stdin: bool, stdout: bool) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: stdin)
    monkeypatch.setattr("sys.stdout.isatty", lambda: stdout)


@pytest.fixture()
def _consent_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_init_prompt_yes_records_consent(tmp_path, _consent_home, monkeypatch, capsys):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, True, True)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert main(["init", str(tmp_path / "repo")]) == 0
    record = consent.load_consent()
    assert record.share_usage is True
    assert len(record.install_id) == 32
    assert "rac telemetry status" in capsys.readouterr().out


def test_init_prompt_default_no_is_persisted_and_asked_once(tmp_path, _consent_home, monkeypatch):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, True, True)
    asked = []

    def _input(prompt: str) -> str:
        asked.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", _input)
    assert main(["init", str(tmp_path / "repo")]) == 0
    assert len(asked) == 1
    assert "[y/N]" in asked[0]
    assert consent.consent_recorded() is True
    assert consent.load_consent().share_usage is False
    # The question is never asked twice on the same machine.
    assert main(["init", str(tmp_path / "repo")]) == 0
    assert len(asked) == 1


def test_init_prompt_eof_means_no(tmp_path, _consent_home, monkeypatch):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, True, True)

    def _eof(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    assert main(["init", str(tmp_path / "repo")]) == 0
    assert consent.load_consent().share_usage is False


def test_init_never_prompts_without_a_tty(tmp_path, _consent_home, monkeypatch):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, False, False)

    def _forbidden(prompt: str) -> str:  # pragma: no cover - must not run
        raise AssertionError("input() must not be called without a TTY")

    monkeypatch.setattr("builtins.input", _forbidden)
    assert main(["init", str(tmp_path / "repo")]) == 0
    assert consent.consent_recorded() is False


def test_init_json_never_prompts(tmp_path, _consent_home, monkeypatch, capsys):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, True, True)

    def _forbidden(prompt: str) -> str:  # pragma: no cover - must not run
        raise AssertionError("input() must not be called with --json")

    monkeypatch.setattr("builtins.input", _forbidden)
    assert main(["init", str(tmp_path / "repo"), "--json"]) == 0
    json.loads(capsys.readouterr().out)  # machine output stays pure JSON
    assert consent.consent_recorded() is False
