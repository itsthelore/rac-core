"""Characterization pins for JSON envelopes that embed a variable field.

Three machine-facing surfaces carry a stable JSON contract (ADR-007) that no
golden byte-pins, because each embeds one host-variable value:

* ``rac export`` (default viewer JSON) embeds ``corpus.rac_version``.
* ``rac gate --sarif`` embeds ``runs[0].tool.driver.version``.
* ``rac usage --json`` embeds the absolute Guide telemetry log path.

The rebuild will reimplement these serializers; everything *except* the
variable field is a frozen contract. Following the pattern in
``tests/test_golden.py`` (which excises git-derived recency before comparison),
these tests normalize only the variable field to a placeholder and compare the
rest byte-for-byte against a committed expected file.
"""

from __future__ import annotations

import json
from pathlib import Path

from rac.cli import main

REPO_ROOT = Path(__file__).parent.parent
EXPECTED_DIR = Path(__file__).parent / "fixtures" / "characterization"
VERSION_PLACEHOLDER = "<VERSION>"


def _run(argv, capsys, monkeypatch, expected_rc):
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr("rac.output.human._USE_COLOR", False)
    rc = main(argv)
    assert rc == expected_rc
    return capsys.readouterr().out


def _reserialize(data) -> str:
    return json.dumps(data, indent=2) + "\n"


def test_export_viewer_json_contract(capsys, monkeypatch):
    out = _run(
        ["export", "tests/fixtures/portfolio_summary/all_types"],
        capsys,
        monkeypatch,
        0,
    )
    data = json.loads(out)
    # The only host-variable field is the setuptools-scm package version.
    assert data["corpus"]["rac_version"]  # present and non-empty (unpinned value)
    data["corpus"]["rac_version"] = VERSION_PLACEHOLDER
    expected = (EXPECTED_DIR / "export_viewer_json.txt").read_text(encoding="utf-8")
    assert _reserialize(data) == expected


def test_gate_sarif_contract(capsys, monkeypatch):
    out = _run(["gate", "tests/fixtures/portfolio", "--sarif"], capsys, monkeypatch, 1)
    data = json.loads(out)
    driver = data["runs"][0]["tool"]["driver"]
    assert driver["version"]  # present and non-empty (unpinned value)
    driver["version"] = VERSION_PLACEHOLDER
    expected = (EXPECTED_DIR / "gate_sarif_json.txt").read_text(encoding="utf-8")
    assert _reserialize(data) == expected


def test_usage_json_empty_contract(capsys, monkeypatch):
    # conftest points XDG_STATE_HOME at a fresh temp dir, so no usage is
    # recorded — this pins the empty-telemetry envelope. Only the absolute
    # Guide log path varies by host; normalize it.
    out = _run(["usage", "--json"], capsys, monkeypatch, 0)
    data = json.loads(out)
    assert data["guide"]["path"].endswith("rac/guide-telemetry.jsonl")
    data["guide"]["path"] = "<STATE>/rac/guide-telemetry.jsonl"
    expected = (EXPECTED_DIR / "usage_json.txt").read_text(encoding="utf-8")
    assert _reserialize(data) == expected
