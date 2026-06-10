"""Tests for Explorer preferences, workspace, and mascot (v0.8.6)."""

from __future__ import annotations

import json

import pytest

from rac.explorer import mascot
from rac.explorer.preferences import (
    GROUPING_FLAT,
    Preferences,
    load_preferences,
    preferences_path,
    save_preferences,
)
from rac.explorer.workspace import load_workspace, save_workspace, workspace_path


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


# --- preferences ---------------------------------------------------------------


def test_defaults_when_no_file():
    prefs = load_preferences()
    assert prefs == Preferences()
    assert prefs.mascot and prefs.animations


def test_round_trip():
    save_preferences(Preferences(theme="custom", mascot=False, artifact_grouping=GROUPING_FLAT))
    loaded = load_preferences()
    assert loaded.theme == "custom"
    assert loaded.mascot is False
    assert loaded.artifact_grouping == GROUPING_FLAT


def test_corrupt_file_falls_back_to_defaults():
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json{", encoding="utf-8")
    assert load_preferences() == Preferences()


def test_unknown_grouping_falls_back():
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"artifact_grouping": "spirals"}), encoding="utf-8")
    assert load_preferences().artifact_grouping == "type"


# --- workspace -----------------------------------------------------------------


def test_records_recent_and_resumes_last_artifact():
    ws = load_workspace()
    ws.record_open("rac/")
    ws.record_open("other/")
    ws.record_artifact("rac/", "rac/decisions/adr-001.md")
    save_workspace(ws)

    reloaded = load_workspace()
    assert reloaded.recent[0] == "other/"  # most recent first
    assert "rac/" in reloaded.recent
    assert reloaded.resume_artifact("rac/") == "rac/decisions/adr-001.md"
    assert reloaded.resume_artifact("unknown/") is None


def test_recent_is_deduped_and_capped():
    ws = load_workspace()
    for i in range(15):
        ws.record_open(f"repo-{i}/")
    ws.record_open("repo-0/")  # re-opening moves it to the front, no dupe
    assert ws.recent[0] == "repo-0/"
    assert len(ws.recent) <= 10
    assert ws.recent.count("repo-0/") == 1


def test_corrupt_workspace_falls_back():
    path = workspace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("}{", encoding="utf-8")
    assert load_workspace().recent == []


# --- mascot --------------------------------------------------------------------


def test_every_state_has_text_equivalent():
    for state in (
        mascot.IDLE,
        mascot.SEARCHING,
        mascot.DISCOVERY,
        mascot.SUCCESS,
        mascot.EMPTY,
        mascot.ERROR,
    ):
        assert mascot.label(state)
        assert mascot.label(state) in mascot.figure(state)


def test_animations_off_uses_steady_frame_but_keeps_meaning():
    animated = mascot.figure(mascot.SEARCHING, animations=True)
    static = mascot.figure(mascot.SEARCHING, animations=False)
    # The label (meaning) is identical; only the lantern glyph differs.
    assert mascot.label(mascot.SEARCHING) in animated
    assert mascot.label(mascot.SEARCHING) in static
