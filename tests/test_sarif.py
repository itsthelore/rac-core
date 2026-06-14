"""Tests for SARIF validation output — CI code scanning (ADR-054).

Structural and determinism checks rather than a committed byte-golden (the tool
version is build-derived). Covers the SARIF 2.1.0 envelope, that core validation
and OKF findings both appear, the severity->level mapping, region presence only
for line-anchored findings, and that suppressed (`off`) findings never render.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.output import render_validate_sarif
from rac.services.validate import validate_directory

BAD_DECISION = """\
---
schema_version: 1
id: RAC-KTQ63DPSMF19
type: decision
---
# Bad Status

## Context
c

## Decision
d

## Consequences
x

## Status
Bogus
"""


def _sarif_for(tmp_path) -> dict:
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    # index.md (typed) also yields an OKF reserved-filename finding.
    (tmp_path / "index.md").write_text(BAD_DECISION.replace("Bogus", "Accepted"), encoding="utf-8")
    result = validate_directory(str(tmp_path))
    return json.loads(render_validate_sarif(result))


def test_sarif_envelope(tmp_path):
    doc = _sarif_for(tmp_path)
    assert doc["version"] == "2.1.0"
    assert "$schema" in doc
    driver = doc["runs"][0]["tool"]["driver"]
    assert driver["name"] == "rac"
    assert isinstance(driver["version"], str) and driver["version"]


def test_sarif_covers_core_and_okf_findings(tmp_path):
    doc = _sarif_for(tmp_path)
    rule_ids = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert "invalid-decision-status" in rule_ids  # core validation
    assert "okf-reserved-filename-collision" in rule_ids  # OKF conformance
    # Declared rules mirror the observed codes.
    declared = {r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
    assert rule_ids <= declared


def test_sarif_levels_and_regions(tmp_path):
    doc = _sarif_for(tmp_path)
    for r in doc["runs"][0]["results"]:
        assert r["level"] in ("error", "warning")
        loc = r["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"]
        # OKF findings are file-level (no region); core findings may carry a line.
        if "region" in loc:
            assert loc["region"]["startLine"] >= 1


def test_sarif_deterministic(tmp_path):
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    result = validate_directory(str(tmp_path))
    assert render_validate_sarif(result) == render_validate_sarif(result)


def test_sarif_omits_suppressed_findings(tmp_path):
    (tmp_path / ".rac").mkdir()
    (tmp_path / ".rac" / "config.yaml").write_text(
        "repository_key: RAC\nvalidation:\n  rules:\n    invalid-decision-status: off\n",
        encoding="utf-8",
    )
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    doc = json.loads(render_validate_sarif(validate_directory(str(tmp_path))))
    rule_ids = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert "invalid-decision-status" not in rule_ids


def test_cli_sarif_directory(tmp_path, capsys):
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    rc = main(["validate", str(tmp_path), "--sarif"])
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0"


def test_cli_sarif_rejected_for_single_file(tmp_path, capsys):
    f = tmp_path / "d.md"
    f.write_text(BAD_DECISION, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["validate", str(f), "--sarif"])
    assert exc.value.code == 2  # EXIT_USAGE
    assert "directory validation" in capsys.readouterr().err


def test_cli_json_and_sarif_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        main(["validate", str(tmp_path), "--json", "--sarif"])
