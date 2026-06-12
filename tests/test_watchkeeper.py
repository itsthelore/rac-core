"""Tests for the watchkeeper review surface (v0.12.2).

Pins the recommendation mapping, the --fail-on exit matrix, the github
format (Markdown on stdout, workflow-command annotations on stderr), and
the JSON review block.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.output import render_watchkeeper_json
from rac.services.watchkeeper import (
    REASON_BROKEN_RELATIONSHIP,
    REASON_VALIDATION_REGRESSION,
    build_watchkeeper_report,
)

REPO_ROOT = Path(__file__).parent.parent
BASE = "tests/fixtures/watchkeeper/base"
HEAD = "tests/fixtures/watchkeeper/head"


def fixture_report():
    return build_watchkeeper_report(
        fixture_path("watchkeeper", "head"),
        base=fixture_path("watchkeeper", "base"),
    )


def clean_report():
    base = fixture_path("watchkeeper", "base")
    return build_watchkeeper_report(base, base=base)


def run_cli(argv, capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# --- recommendations ----------------------------------------------------------


def test_recommendation_codes_and_order():
    report = fixture_report()
    assert report.review_recommended
    assert [rec.code for rec in report.recommendations] == [
        REASON_VALIDATION_REGRESSION,
        REASON_BROKEN_RELATIONSHIP,
        "acceptance_criteria_removed",
        "constraint_removed",
        "constraint_weakened",
        "specificity_regression",
    ]
    # Reasons are Core-owned sentences, deduplicated by code.
    assert all(rec.reason.endswith(".") for rec in report.recommendations)
    assert len({rec.code for rec in report.recommendations}) == len(report.recommendations)


def test_informational_codes_never_recommend_alone(tmp_path):
    # An added, valid, *linked* pair plus an ambiguity edit: a warning finding
    # that is not in the recommending set must not flip the verdict.
    base_dir = tmp_path / "base"
    head_dir = tmp_path / "head"
    for directory in (base_dir, head_dir):
        directory.mkdir()
    text = (
        "# Upload\n\n## Problem\n\nUploads are slow.\n\n## Requirements\n\n"
        "[REQ-001] Upload completes within 5 seconds\n"
    )
    (base_dir / "upload.md").write_text(text, encoding="utf-8")
    (head_dir / "upload.md").write_text(
        text.replace("within 5 seconds", "within 5 fast seconds"), encoding="utf-8"
    )
    report = build_watchkeeper_report(str(head_dir), base=str(base_dir))
    assert [f.code for f in report.findings] == ["ambiguity_introduced"]
    assert not report.review_recommended


def test_clean_comparison_recommends_nothing():
    report = clean_report()
    assert not report.review_recommended
    assert report.recommendations == []
    assert not report.has_warnings


def test_json_review_block():
    payload = json.loads(render_watchkeeper_json(fixture_report()))
    assert payload["review"]["recommended"] is True
    reasons = payload["review"]["reasons"]
    assert reasons[0] == {
        "code": "validation_regression",
        "reason": "One or more artifacts became invalid.",
    }


# --- fail-on matrix (through the CLI) ------------------------------------------


@pytest.mark.parametrize(
    "fail_on,dirty_rc,clean_rc",
    [("error", 1, 0), ("warning", 1, 0), ("none", 0, 0)],
)
def test_fail_on_matrix(fail_on, dirty_rc, clean_rc, capsys, monkeypatch):
    rc, _, _ = run_cli(
        ["watchkeeper", HEAD, "--base", BASE, "--fail-on", fail_on], capsys, monkeypatch
    )
    assert rc == dirty_rc
    rc, _, _ = run_cli(
        ["watchkeeper", BASE, "--base", BASE, "--fail-on", fail_on], capsys, monkeypatch
    )
    assert rc == clean_rc


def test_fail_on_warning_fails_on_warning_only_findings(tmp_path, capsys, monkeypatch):
    base_dir = tmp_path / "base"
    head_dir = tmp_path / "head"
    for directory in (base_dir, head_dir):
        directory.mkdir()
    text = (
        "# Upload\n\n## Problem\n\nUploads are slow.\n\n## Requirements\n\n"
        "[REQ-001] Upload completes within 5 seconds\n"
    )
    (base_dir / "upload.md").write_text(text, encoding="utf-8")
    (head_dir / "upload.md").write_text(
        text.replace("within 5 seconds", "within 5 fast seconds"), encoding="utf-8"
    )
    argv = ["watchkeeper", str(head_dir), "--base", str(base_dir)]
    assert main(argv + ["--fail-on", "error"]) == 0  # warning finding, no recommendation
    assert main(argv + ["--fail-on", "warning"]) == 1
    capsys.readouterr()


# --- github format --------------------------------------------------------------


def test_github_format_writes_markdown_to_stdout(capsys, monkeypatch):
    rc, out, _ = run_cli(
        ["watchkeeper", HEAD, "--base", BASE, "--format", "github"], capsys, monkeypatch
    )
    assert rc == 1
    assert out.startswith("# RAC Watchkeeper")
    assert "| Change | Artifact | Type |" in out
    assert "**Review recommended.**" in out
    assert "::" not in out  # workflow commands never pollute the summary


def test_github_format_writes_annotations_to_stderr(capsys, monkeypatch):
    _, _, err = run_cli(
        ["watchkeeper", HEAD, "--base", BASE, "--format", "github"], capsys, monkeypatch
    )
    lines = [line for line in err.splitlines() if line]
    assert lines, "expected workflow-command annotations on stderr"
    assert all(line.startswith(("::error", "::warning", "::notice")) for line in lines)
    # Paths are repository-relative: the corpus directory joined to the
    # corpus-relative artifact path.
    assert any(
        line.startswith(
            "::error file=tests/fixtures/watchkeeper/head/requirements/payouts.md::"
            "validation_regression:"
        )
        for line in lines
    )
    # Recommendation triggers annotate as errors, not warnings.
    assert any("::error" in line and "specificity_regression" in line for line in lines)


def test_no_annotate_suppresses_annotations(capsys, monkeypatch):
    _, _, err = run_cli(
        ["watchkeeper", HEAD, "--base", BASE, "--format", "github", "--no-annotate"],
        capsys,
        monkeypatch,
    )
    assert "::" not in err


def test_clean_github_verdict_is_green(capsys, monkeypatch):
    rc, out, err = run_cli(
        ["watchkeeper", BASE, "--base", BASE, "--format", "github"], capsys, monkeypatch
    )
    assert rc == 0
    assert "Nothing requiring attention." in out
    assert err == ""


def test_json_flag_remains_an_alias(capsys, monkeypatch):
    _, out, _ = run_cli(["watchkeeper", HEAD, "--base", BASE, "--json"], capsys, monkeypatch)
    payload = json.loads(out)
    assert payload["schema_version"] == "1"
    assert payload["review"]["recommended"] is True
