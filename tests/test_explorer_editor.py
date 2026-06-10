"""Tests for external editor integration (v0.8.4)."""

from __future__ import annotations

import rac.explorer.editor as editor_mod
from rac.explorer.editor import open_in_editor, resolve_editor


def test_resolve_prefers_visual_then_editor(monkeypatch):
    monkeypatch.setenv("VISUAL", "code")
    monkeypatch.setenv("EDITOR", "vim")
    assert resolve_editor() == "code"
    monkeypatch.delenv("VISUAL")
    assert resolve_editor() == "vim"


def test_resolve_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    assert resolve_editor() is None


def test_open_launches_resolved_editor_with_path(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(editor_mod, "_RUNNER", lambda cmd: calls.append(list(cmd)))
    monkeypatch.setenv("VISUAL", "code --wait")
    monkeypatch.delenv("EDITOR", raising=False)

    outcome = open_in_editor("rac/decisions/adr-001.md")
    assert outcome.launched
    assert calls == [["code", "--wait", "rac/decisions/adr-001.md"]]
    assert "adr-001.md" in outcome.message


def test_open_without_editor_offers_guidance(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    outcome = open_in_editor("x.md")
    assert not outcome.launched
    assert "$EDITOR" in outcome.message


def test_open_handles_launch_failure(monkeypatch):
    def boom(cmd):
        raise OSError("no such file")

    monkeypatch.setattr(editor_mod, "_RUNNER", boom)
    monkeypatch.setenv("EDITOR", "ghost-editor")
    outcome = open_in_editor("x.md")
    assert not outcome.launched
    assert "Could not launch" in outcome.message
