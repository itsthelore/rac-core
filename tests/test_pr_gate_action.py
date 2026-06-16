"""Structural tests for the RAC PR-gate composite action (v0.21.14).

The action is a thin wrapper that runs a single `rac gate <path> --sarif` — one
command that composes validation, relationship integrity, and review under the
corpus enforcement policy — uploads the single SARIF document, and re-surfaces
the CLI exit code. Its analysis is owned by the (separately tested) CLI; these
tests pin the action's *contract* so the wiring cannot silently drift (ADR-063:
the action computes nothing).
"""

from __future__ import annotations

from pathlib import Path

import yaml

ACTION = Path(__file__).parent.parent / "pr-gate-action" / "action.yml"


def _action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_is_composite():
    a = _action()
    assert a["runs"]["using"] == "composite"
    assert a["name"] == "RAC PR gate"


def test_action_declares_expected_inputs():
    inputs = _action()["inputs"]
    for name in ("path", "upload-sarif", "sarif-dir", "rac-version", "install-from"):
        assert name in inputs, f"missing input: {name}"
    assert inputs["path"]["default"] == "rac"
    assert inputs["upload-sarif"]["default"] == "true"


def test_action_runs_single_gate_command():
    run_steps = " ".join(s.get("run", "") for s in _action()["runs"]["steps"])
    assert "rac gate" in run_steps
    assert "--sarif" in run_steps
    # The three separate checks are now collapsed into the one gate command.
    assert "rac validate" not in run_steps
    assert "rac relationships" not in run_steps
    assert "rac review" not in run_steps


def test_action_uploads_single_sarif_once():
    steps = _action()["runs"]["steps"]
    uploads = [s for s in steps if "upload-sarif" in str(s.get("uses", ""))]
    assert len(uploads) == 1, "the gate uploads exactly one SARIF document"
    # Upload even on failure so findings still annotate the PR.
    assert "always()" in uploads[0]["if"]
    assert uploads[0]["with"]["category"] == "rac-gate"


def test_action_resurfaces_exit_code():
    run_steps = " ".join(s.get("run", "") for s in _action()["runs"]["steps"])
    assert 'exit "$EXIT_CODE"' in run_steps


def test_action_install_supports_source_for_dogfood():
    # `install-from: source` lets the repo dogfood the action with uses: ./pr-gate-action.
    run_steps = " ".join(s.get("run", "") for s in _action()["runs"]["steps"])
    assert "GITHUB_ACTION_PATH" in run_steps
