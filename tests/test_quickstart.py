"""Tests for rac.services.quickstart and the `rac quickstart` CLI (v0.13.0).

Pins the guided first-run contract: one command establishes identity and
scaffolds a single starter artifact under rac/<family>/, only into an empty
corpus (ADR-044), never overwriting; a populated corpus is refused (exit 1),
a bad key or type is a usage error (exit 2), and the created artifact is a
valid, classifiable artifact like any `rac new` output.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.core.classification import classify
from rac.core.markdown import parse_file
from rac.core.templates import TemplateNotFound
from rac.core.validation import has_errors, validate
from rac.services.init import InvalidRepositoryKey, RepositoryKeyConflict, init_repository
from rac.services.quickstart import CorpusNotEmpty, quickstart

# Deterministic generator for tests: a fixed, syntactically canonical suffix.
FIXED_SUFFIX = "01JY4M8X2QZ7"


def fixed_generator(repository_key: str) -> str:
    return f"{repository_key}-{FIXED_SUFFIX}"


# --- service -----------------------------------------------------------------


def test_quickstart_establishes_identity_and_scaffolds(tmp_path):
    result = quickstart(str(tmp_path), id_generator=fixed_generator)
    assert result.created
    assert result.repository_key == "RAC"
    assert result.artifact.artifact_type == "requirement"
    starter = tmp_path / "rac" / "requirements" / "first-requirement.md"
    assert starter.is_file()
    assert result.artifact.path == str(starter)
    # The config namespace exists too.
    assert (tmp_path / ".rac" / "config.yaml").is_file()


def test_quickstart_artifact_is_valid_and_classifies(tmp_path):
    quickstart(str(tmp_path), id_generator=fixed_generator)
    starter = tmp_path / "rac" / "requirements" / "first-requirement.md"
    product = parse_file(str(starter))
    assert not has_errors(validate(product))
    assert classify(product).type == "requirement"


def test_quickstart_respects_key_and_type(tmp_path):
    result = quickstart(
        str(tmp_path), key="PROJ", artifact_type="decision", id_generator=fixed_generator
    )
    assert result.repository_key == "PROJ"
    starter = tmp_path / "rac" / "decisions" / "first-decision.md"
    assert starter.is_file()
    assert result.artifact.id == "PROJ-01JY4M8X2QZ7"


def test_quickstart_refuses_non_empty_corpus(tmp_path):
    # Seed one real artifact via init + create, then quickstart must refuse.
    init_repository(str(tmp_path), key="RAC")
    rac_dir = tmp_path / "rac" / "requirements"
    rac_dir.mkdir(parents=True)
    from rac.services.create import create_artifact

    create_artifact("requirement", str(rac_dir / "existing.md"), id_generator=fixed_generator)
    with pytest.raises(CorpusNotEmpty):
        quickstart(str(tmp_path), id_generator=fixed_generator)


def test_quickstart_refuses_before_writing_into_populated_corpus(tmp_path):
    # A recognised artifact present but no .rac yet: refusal must not write
    # config or a starter file.
    rac_dir = tmp_path / "rac" / "decisions"
    rac_dir.mkdir(parents=True)
    init_repository(str(tmp_path), key="RAC")
    from rac.services.create import create_artifact

    create_artifact("decision", str(rac_dir / "d.md"), id_generator=fixed_generator)
    (tmp_path / ".rac").rename(tmp_path / ".rac-stashed")  # remove identity again
    with pytest.raises(CorpusNotEmpty):
        quickstart(str(tmp_path), id_generator=fixed_generator)
    assert not (tmp_path / ".rac").exists()
    assert not (tmp_path / "rac" / "requirements").exists()


def test_quickstart_unknown_type_raises_before_any_write(tmp_path):
    with pytest.raises(TemplateNotFound):
        quickstart(str(tmp_path), artifact_type="nonsense")
    assert not (tmp_path / ".rac").exists()
    assert not (tmp_path / "rac").exists()


def test_quickstart_invalid_key_raises(tmp_path):
    with pytest.raises(InvalidRepositoryKey):
        quickstart(str(tmp_path), key="bad")


def test_quickstart_key_conflict_raises(tmp_path):
    init_repository(str(tmp_path), key="RAC")
    with pytest.raises(RepositoryKeyConflict):
        quickstart(str(tmp_path), key="OTHER", id_generator=fixed_generator)


# --- CLI ----------------------------------------------------------------------


def test_cli_quickstart_human_exit_0(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No TTY so the usage-sharing prompt never fires.
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    rc = main(["quickstart"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Initialized repository key RAC" in out
    assert "rac validate" in out
    assert (tmp_path / "rac" / "requirements" / "first-requirement.md").is_file()


def test_cli_quickstart_then_validate_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert main(["quickstart"]) == 0
    assert main(["validate", "rac/requirements/first-requirement.md"]) == 0


def test_cli_quickstart_json_shape(tmp_path, capsys):
    rc = main(["quickstart", str(tmp_path), "--key", "PROJ", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["repository_key"] == "PROJ"
    assert payload["created"] is True
    assert payload["artifact"]["type"] == "requirement"
    assert payload["artifact"]["path"].endswith("first-requirement.md")
    assert payload["artifact"]["id"].startswith("PROJ-")


def test_cli_quickstart_refuses_non_empty_exit_1(tmp_path, capsys):
    assert main(["quickstart", str(tmp_path)]) == 0
    rc = main(["quickstart", str(tmp_path)])
    assert rc == 1
    assert "only scaffolds an empty corpus" in capsys.readouterr().err


def test_cli_quickstart_bad_type_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["quickstart", str(tmp_path), "--type", "nonsense"])
    assert exc.value.code == 2
    assert "unsupported artifact type" in capsys.readouterr().err


def test_cli_quickstart_bad_key_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["quickstart", str(tmp_path), "--key", "bad"])
    assert exc.value.code == 2
    assert "invalid repository key" in capsys.readouterr().err


def test_cli_quickstart_missing_directory_exit_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["quickstart", str(tmp_path / "nope")])
    assert exc.value.code == 2


# --- usage-sharing prompt parity with `rac init` (ADR-041) --------------------
#
# quickstart is the new first-run entry point, so it carries the same one-time
# consent question as `rac init`: TTY-gated, default No, never with --json,
# asked at most once per machine.


def _tty(monkeypatch, stdin: bool, stdout: bool) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: stdin)
    monkeypatch.setattr("sys.stdout.isatty", lambda: stdout)


@pytest.fixture()
def _consent_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_quickstart_prompt_yes_records_consent(tmp_path, _consent_home, monkeypatch, capsys):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, True, True)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert main(["quickstart", str(tmp_path / "repo")]) == 0
    record = consent.load_consent()
    assert record.share_usage is True
    assert "rac telemetry status" in capsys.readouterr().out


def test_quickstart_prompt_default_no_is_persisted_and_asked_once(
    tmp_path, _consent_home, monkeypatch
):
    from rac import consent

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _tty(monkeypatch, True, True)
    asked: list[str] = []

    def _input(prompt: str) -> str:
        asked.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", _input)
    assert main(["quickstart", str(tmp_path / "a")]) == 0
    assert len(asked) == 1
    assert "[y/N]" in asked[0]
    assert consent.consent_recorded() is True
    assert consent.load_consent().share_usage is False
    # The question is never asked twice on the same machine.
    assert main(["quickstart", str(tmp_path / "b")]) == 0
    assert len(asked) == 1


def test_quickstart_never_prompts_without_a_tty(tmp_path, _consent_home, monkeypatch):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, False, False)

    def _forbidden(prompt: str) -> str:  # pragma: no cover - must not run
        raise AssertionError("input() must not be called without a TTY")

    monkeypatch.setattr("builtins.input", _forbidden)
    assert main(["quickstart", str(tmp_path / "repo")]) == 0
    assert consent.consent_recorded() is False


def test_quickstart_json_never_prompts(tmp_path, _consent_home, monkeypatch, capsys):
    from rac import consent

    (tmp_path / "repo").mkdir()
    _tty(monkeypatch, True, True)

    def _forbidden(prompt: str) -> str:  # pragma: no cover - must not run
        raise AssertionError("input() must not be called with --json")

    monkeypatch.setattr("builtins.input", _forbidden)
    assert main(["quickstart", str(tmp_path / "repo"), "--json"]) == 0
    json.loads(capsys.readouterr().out)  # machine output stays pure JSON
    assert consent.consent_recorded() is False
