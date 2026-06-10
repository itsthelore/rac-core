"""Tests for the `rac explorer` CLI wiring (v0.8.0)."""

from __future__ import annotations

import pytest

import rac.explorer.launch as launch
from rac.cli import main
from rac.explorer.launch import MISSING_EXTRA_HINT, ExplorerUnavailable, run_explorer


class _AppSpy:
    """Stands in for ExplorerApp: records construction, runs without a TTY."""

    instances: list[_AppSpy] = []

    def __init__(self, directory: str, recursive: bool = True) -> None:
        self.directory = directory
        self.recursive = recursive
        self.ran = False
        _AppSpy.instances.append(self)

    def run(self) -> None:
        self.ran = True


@pytest.fixture(autouse=True)
def _reset_spy():
    _AppSpy.instances = []


def test_explorer_launches_app_over_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "_import_app", lambda: _AppSpy)
    assert main(["explorer", str(tmp_path)]) == 0
    [app] = _AppSpy.instances
    assert app.directory == str(tmp_path)
    assert app.recursive is True
    assert app.ran


def test_explorer_defaults_to_rac_root_when_present(tmp_path, monkeypatch):
    # ADR-018: rac/ is the conventional knowledge root.
    monkeypatch.setattr(launch, "_import_app", lambda: _AppSpy)
    (tmp_path / "rac").mkdir()
    monkeypatch.chdir(tmp_path)
    assert main(["explorer"]) == 0
    [app] = _AppSpy.instances
    assert app.directory == "rac"


def test_explorer_defaults_to_current_directory_without_rac_root(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "_import_app", lambda: _AppSpy)
    monkeypatch.chdir(tmp_path)
    assert main(["explorer"]) == 0
    [app] = _AppSpy.instances
    assert app.directory == "."


def test_explorer_explicit_path_wins_over_rac_root(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "_import_app", lambda: _AppSpy)
    (tmp_path / "rac").mkdir()
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path)
    assert main(["explorer", "docs"]) == 0
    [app] = _AppSpy.instances
    assert app.directory == "docs"


def test_explorer_top_level_disables_recursion(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "_import_app", lambda: _AppSpy)
    assert main(["explorer", str(tmp_path), "--top-level"]) == 0
    [app] = _AppSpy.instances
    assert app.recursive is False


def test_explorer_rejects_missing_directory(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["explorer", str(tmp_path / "nope")])
    assert excinfo.value.code == 2
    assert "not a directory" in capsys.readouterr().err


def test_missing_extra_exits_2_with_install_hint(tmp_path, monkeypatch, capsys):
    def import_fails() -> type:
        raise ModuleNotFoundError("No module named 'textual'", name="textual")

    monkeypatch.setattr(launch, "_import_app", import_fails)
    with pytest.raises(SystemExit) as excinfo:
        main(["explorer", str(tmp_path)])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "pip install 'requirements-as-code[explorer]'" in err


def test_unavailable_error_carries_the_hint(monkeypatch):
    def import_fails() -> type:
        raise ModuleNotFoundError("No module named 'textual.app'", name="textual.app")

    monkeypatch.setattr(launch, "_import_app", import_fails)
    with pytest.raises(ExplorerUnavailable, match="explorer extra"):
        run_explorer(".")
    assert "requirements-as-code[explorer]" in MISSING_EXTRA_HINT


def test_other_import_errors_are_real_bugs(monkeypatch):
    def import_fails() -> type:
        raise ModuleNotFoundError("No module named 'nonexistent'", name="nonexistent")

    monkeypatch.setattr(launch, "_import_app", import_fails)
    with pytest.raises(ModuleNotFoundError, match="nonexistent"):
        run_explorer(".")
