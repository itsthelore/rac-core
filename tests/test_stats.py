"""Tests for portfolio statistics (`rac stats`)."""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.stats import collect_stats

from conftest import fixture_path


def test_collect_counts():
    s = collect_stats(fixture_path("portfolio"))
    assert s.files_found == 4  # includes the nested feature_c.md (recursion)
    assert s.valid_features == 3
    assert s.invalid_features == 1
    assert s.total_requirements == 7  # 2 + 1 + 1 (invalid) + 3 (nested)
    assert s.total_metrics == 1
    assert s.total_risks == 1


def test_invalid_files_are_reported_not_skipped():
    s = collect_stats(fixture_path("portfolio"))
    assert len(s.invalid) == 1
    bad = s.invalid[0]
    assert bad.path.endswith("broken.md")
    assert "missing-title" in bad.error_codes
    # Its requirement still contributes to the portfolio total.
    assert bad.requirements == 1


def test_warnings_only_file_counts_as_valid():
    # feature_b.md has no metrics/risks (warnings only) -> still a valid feature.
    s = collect_stats(fixture_path("portfolio"))
    feature_b = next(f for f in s.features if f.path.endswith("feature_b.md"))
    assert feature_b.valid is True
    assert feature_b.error_codes == []


def test_quality_metrics():
    s = collect_stats(fixture_path("portfolio"))
    assert s.features_missing_metrics == 3  # only feature_a has a metric
    assert s.features_missing_risks == 3  # only feature_a has a risk
    # REQ-008/009: identify *which* features are missing them (by name).
    assert s.missing_metrics == ["broken", "Feature B", "Feature C"]
    assert s.missing_risks == ["broken", "Feature B", "Feature C"]
    assert round(s.average_requirements, 1) == 1.8  # 7 reqs / 4 files
    assert s.largest_feature.name == "Feature C"
    assert s.largest_feature.requirements == 3
    # Sorted by requirement count desc, then name asc.
    assert [f.name for f in s.requirements_by_feature] == [
        "Feature C",
        "Feature A",
        "Feature B",
        "broken",
    ]


def test_cli_stats_human(capsys):
    rc = main(["stats", fixture_path("portfolio")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Portfolio Overview" in out
    assert "Features: 4" in out
    assert "Quality" in out
    assert "Features Missing Metrics: 3" in out
    assert "  - Feature B" in out  # names listed, not just the count
    assert "Average Requirements Per Feature: 1.8" in out
    assert "Largest Feature: Feature C (3 requirements)" in out
    assert "Requirements by Feature" in out
    assert "Invalid Features (1)" in out
    assert "broken.md" in out


def test_cli_stats_json(capsys):
    rc = main(["stats", fixture_path("portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["features"] == 4
    assert payload["valid_features"] == 3
    assert payload["requirements"] == 7
    assert payload["metrics"] == 1
    assert payload["features_missing_metrics"] == 3
    assert payload["missing_metrics"] == ["broken", "Feature B", "Feature C"]
    assert payload["average_requirements_per_feature"] == 1.8
    assert payload["largest_feature"] == {"name": "Feature C", "requirements": 3}
    assert payload["requirements_by_feature"][0] == {
        "name": "Feature C",
        "requirements": 3,
    }
    assert payload["invalid"][0]["file"].endswith("broken.md")


def test_cli_stats_missing_directory_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["stats", fixture_path("portfolio", "does_not_exist")])
    assert exc.value.code == 2


def test_cli_stats_exits_one_when_no_valid_features(tmp_path, capsys):
    # A directory whose only file fails validation -> no valid features.
    (tmp_path / "broken.md").write_text(
        "## Problem\n\nNo title.\n\n## Requirements\n\n[REQ-001] x\n"
    )
    rc = main(["stats", str(tmp_path)])
    assert rc == 1
    assert "Invalid Features (1)" in capsys.readouterr().out


def test_cli_stats_exits_zero_with_one_valid_feature(tmp_path):
    (tmp_path / "ok.md").write_text(
        "# Ok\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
    )
    (tmp_path / "broken.md").write_text("## Problem\n\nno title\n")
    # One valid feature present -> exit 0 even though a broken file exists.
    assert main(["stats", str(tmp_path)]) == 0


# --- unrecognized documents (ADR-010) ----------------------------------------

_OK_FEATURE = "# Ok\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
_PROSE_DOC = "# Notes\n\nJust prose, no recognizable sections.\n"


def test_unrecognized_documents_are_not_features(tmp_path):
    # A document with no recognizable artifact sections is recorded as
    # unrecognized, not validated as a broken Requirement feature.
    (tmp_path / "ok.md").write_text(_OK_FEATURE)
    (tmp_path / "notes.md").write_text(_PROSE_DOC)
    s = collect_stats(str(tmp_path))
    assert s.files_found == 1  # only the requirement feature
    assert s.valid_features == 1
    assert s.invalid_features == 0  # notes.md is NOT a broken feature
    assert s.unrecognized_count == 1
    assert s.unrecognized[0].path.endswith("notes.md")
    assert s.unrecognized[0].name == "Notes"  # title, not the filename stem
    assert s.unrecognized[0].confidence == 0.0  # no recognizable sections


def test_cli_stats_unrecognized_human(capsys, tmp_path):
    (tmp_path / "ok.md").write_text(_OK_FEATURE)
    (tmp_path / "notes.md").write_text(_PROSE_DOC)
    assert main(["stats", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Unrecognized" in out
    assert "1 document matched no known artifact schema" in out
    assert "notes.md" in out
    # The unrecognized doc must not be reported as a broken feature.
    assert "Invalid Features" not in out


def test_cli_stats_unrecognized_json(capsys, tmp_path):
    (tmp_path / "ok.md").write_text(_OK_FEATURE)
    (tmp_path / "notes.md").write_text(_PROSE_DOC)
    assert main(["stats", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["features"] == 1  # existing keys narrow to real requirements
    assert payload["invalid"] == []
    assert payload["unrecognized"]["count"] == 1
    entry = payload["unrecognized"]["files"][0]
    assert entry["file"].endswith("notes.md")
    assert entry["name"] == "Notes"
    assert entry["confidence"] == 0.0


def test_cli_stats_unrecognized_only_exits_one(capsys, tmp_path):
    # A directory of only unrecognized documents has no analysable known
    # artifact -> exit 1 (the documented contract is unchanged).
    (tmp_path / "notes.md").write_text(_PROSE_DOC)
    rc = main(["stats", str(tmp_path)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Unrecognized" in out
    assert "Invalid Features" not in out


def test_unrecognized_section_omitted_when_none(capsys):
    # A portfolio of only known artifacts renders exactly as before: no section.
    assert main(["stats", fixture_path("portfolio")]) == 0
    assert "Unrecognized" not in capsys.readouterr().out


def test_unrecognized_key_absent_from_json_when_none(capsys):
    main(["stats", fixture_path("portfolio"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert "unrecognized" not in payload
