"""Structural tests for the RAC PR-gate composite action (v0.21.13).

The action is a thin wrapper that runs `rac validate`, `rac relationships
--validate`, and `rac review` — each with `--sarif` — uploads all three SARIF
documents, and re-surfaces the worst CLI exit code. Its analysis is owned by the
(separately tested) CLI; these tests pin the action's *contract* so the wiring
cannot silently drift (ADR-063: the action computes nothing).
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


def test_action_runs_all_three_contract_checks():
    run_steps = " ".join(s.get("run", "") for s in _action()["runs"]["steps"])
    assert "rac validate" in run_steps
    assert "rac relationships" in run_steps and "--validate" in run_steps
    assert "rac review" in run_steps
    assert "--sarif" in run_steps


def test_action_uploads_sarif():
    steps = _action()["runs"]["steps"]
    uploads = [s for s in steps if "upload-sarif" in str(s.get("uses", ""))]
    assert uploads, "no SARIF upload step"
    # Upload even on failure so findings still annotate the PR.
    assert "always()" in uploads[0]["if"]


def test_action_resurfaces_worst_exit_code():
    run_steps = " ".join(s.get("run", "") for s in _action()["runs"]["steps"])
    assert 'exit "$EXIT_CODE"' in run_steps


def test_action_install_supports_source_for_dogfood():
    # `install-from: source` lets the repo dogfood the action with uses: ./pr-gate-action.
    run_steps = " ".join(s.get("run", "") for s in _action()["runs"]["steps"])
    assert "GITHUB_ACTION_PATH" in run_steps
