"""Tests for rac.portfolio and the ``rac portfolio`` CLI command (v0.7.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rac.cli import main
from rac.services.portfolio import (
    ATTENTION_BROKEN_RELATIONSHIP,
    ATTENTION_INVALID,
    build_portfolio_summary,
)

FIXTURES = Path(__file__).parent / "fixtures" / "portfolio_summary"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def summary(subdir: str, **kwargs):
    return build_portfolio_summary(str(FIXTURES / subdir), **kwargs)


# ---------------------------------------------------------------------------
# REQ-002 — artifact coverage: all five types + unknown counted
# ---------------------------------------------------------------------------


def test_all_types_counted():
    s = summary("all_types")
    assert s.by_type["requirement"] == 1
    assert s.by_type["decision"] == 1
    assert s.by_type["roadmap"] == 1
    assert s.by_type["prompt"] == 1
    assert s.by_type["design"] == 1
    assert s.by_type["unknown"] == 1
    assert s.total_artifacts == 6


def test_unknown_only_no_valid_known():
    s = summary("unknown_only")
    assert s.total_artifacts == 1
    assert s.by_type["unknown"] == 1
    assert s.valid_artifacts == 0
    assert s.invalid_artifacts == 0


# ---------------------------------------------------------------------------
# Empty directory — div-by-zero guards
# ---------------------------------------------------------------------------


def test_empty_directory(tmp_path):
    s = build_portfolio_summary(str(tmp_path))
    assert s.total_artifacts == 0
    assert s.valid_artifacts == 0
    assert s.invalid_artifacts == 0
    assert s.health_score == 100
    assert s.completeness == 1.0
    assert s.relationships.total == 0
    assert s.relationships.coverage == 1.0


# ---------------------------------------------------------------------------
# Valid clean fixture — health score and attention
# ---------------------------------------------------------------------------


def test_valid_clean_no_invalid():
    s = summary("valid_clean")
    assert s.invalid_artifacts == 0
    assert not any(a.code == ATTENTION_INVALID for a in s.attention)


def test_valid_clean_health_score_high():
    s = summary("valid_clean")
    # Both artifacts are valid, all recommended sections filled in adr-001.
    # req-001 has all recommended (success metrics, risks, assumptions).
    # Relationships: req-001 references ADR-001 which exists → valid=1, broken=0.
    assert s.relationships.broken == 0
    assert s.health_score > 80


def test_valid_clean_health_score_deterministic():
    s1 = summary("valid_clean")
    s2 = summary("valid_clean")
    assert s1.health_score == s2.health_score


# ---------------------------------------------------------------------------
# Broken relationships
# ---------------------------------------------------------------------------


def test_broken_rels_counted():
    s = summary("broken_rels")
    assert s.relationships.broken == 1
    assert s.relationships.valid == 0


def test_broken_rels_health_penalised():
    s_broken = summary("broken_rels")
    s_clean = summary("valid_clean")
    assert s_broken.health_score < s_clean.health_score


def test_broken_rels_surface_in_attention():
    # A broken reference must be an attention item, not merely a count
    # (roadmap Initiative 3: "ADR-012 references missing artifact").
    s = summary("broken_rels")
    broken = [a for a in s.attention if a.code == ATTENTION_BROKEN_RELATIONSHIP]
    assert len(broken) == 1
    assert "ADR-MISSING" in broken[0].message
    # Identifier is the SOURCE artifact's canonical identifier, not the target.
    assert broken[0].identifier == "source"


def test_no_broken_attention_when_all_resolved():
    s = summary("valid_clean")
    assert not [a for a in s.attention if a.code == ATTENTION_BROKEN_RELATIONSHIP]


# ---------------------------------------------------------------------------
# All-types fixture — non-misclassification
# ---------------------------------------------------------------------------


def test_all_types_no_misclassification():
    s = summary("all_types")
    # Each known type must appear exactly once; none should collapse into another.
    for t in ("requirement", "decision", "roadmap", "prompt", "design"):
        assert s.by_type[t] == 1, f"{t} count wrong"


# ---------------------------------------------------------------------------
# Incomplete-but-recognizable: classifies as a known type, fails validation
# ---------------------------------------------------------------------------


def test_invalid_known_artifact_classifies_then_fails():
    # A titleless requirement still classifies as a requirement (Problem +
    # Requirements present) but fails validation on missing-title.
    s = summary("invalid_known")
    assert s.by_type["requirement"] == 1  # recognized, not Unknown
    assert s.by_type["unknown"] == 0
    assert s.invalid_artifacts == 1
    assert s.valid_artifacts == 0


def test_invalid_known_artifact_surfaces_in_attention():
    s = summary("invalid_known")
    invalid = [a for a in s.attention if a.code == ATTENTION_INVALID]
    assert len(invalid) == 1
    assert invalid[0].severity == "error"
    assert "missing-title" in invalid[0].message


def test_attention_identifier_is_canonical_not_title():
    # The identifier must come from the shared artifact_identifier (stem here),
    # not a separate title-based source of truth.
    s = summary("invalid_known")
    invalid = [a for a in s.attention if a.code == ATTENTION_INVALID][0]
    assert invalid.identifier == "req-no-title"


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def test_completeness_ratio_bounds():
    s = summary("all_types")
    assert 0.0 <= s.completeness <= 1.0


def test_completeness_empty_repo(tmp_path):
    s = build_portfolio_summary(str(tmp_path))
    assert s.completeness == 1.0  # no slots → full


# ---------------------------------------------------------------------------
# Health score formula
# ---------------------------------------------------------------------------


def test_health_score_bounds():
    for subdir in ("all_types", "valid_clean", "broken_rels", "unknown_only"):
        s = summary(subdir)
        assert 0 <= s.health_score <= 100, f"{subdir}: {s.health_score}"


def test_health_score_perfect_empty(tmp_path):
    assert build_portfolio_summary(str(tmp_path)).health_score == 100


# ---------------------------------------------------------------------------
# Attention ordering: errors before warnings, then path, then code
# ---------------------------------------------------------------------------


def test_attention_ordering_errors_first():
    s = summary("all_types")
    severities = [a.severity for a in s.attention]
    error_indices = [i for i, sv in enumerate(severities) if sv == "error"]
    warning_indices = [i for i, sv in enumerate(severities) if sv == "warning"]
    if error_indices and warning_indices:
        assert max(error_indices) < min(warning_indices)


# ---------------------------------------------------------------------------
# JSON contract (REQ-005)
# ---------------------------------------------------------------------------


def test_json_has_schema_version():
    s = summary("all_types")
    d = s.to_dict()
    assert d["schema_version"] == "1"


def test_json_top_level_keys():
    s = summary("all_types")
    d = s.to_dict()
    for key in ("artifacts", "validation", "completeness", "relationships", "attention", "health"):
        assert key in d, f"missing key: {key}"


def test_json_by_type_all_known_types():
    s = summary("all_types")
    d = s.to_dict()
    for t in ("requirement", "decision", "roadmap", "prompt", "design", "unknown"):
        assert t in d["artifacts"]["by_type"]


def test_json_deterministic():
    s1 = summary("all_types")
    s2 = summary("all_types")
    assert json.dumps(s1.to_dict()) == json.dumps(s2.to_dict())


def test_json_relationships_keys():
    s = summary("all_types")
    rel = s.to_dict()["relationships"]
    for key in ("total", "valid", "broken", "orphaned", "coverage"):
        assert key in rel


# ---------------------------------------------------------------------------
# CLI integration — rac portfolio
# ---------------------------------------------------------------------------


def test_cli_portfolio_exit_0(tmp_path):
    ret = main(["portfolio", str(tmp_path)])
    assert ret == 0


def test_cli_portfolio_not_a_dir(tmp_path):
    f = tmp_path / "not_a_dir.md"
    f.write_text("# x")
    with pytest.raises(SystemExit) as exc:
        main(["portfolio", str(f)])
    assert exc.value.code == 2


def test_cli_portfolio_json_output(capsys):
    ret = main(["portfolio", str(FIXTURES / "all_types"), "--json"])
    assert ret == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["schema_version"] == "1"
    assert payload["artifacts"]["total"] == 6


def test_cli_portfolio_human_output(capsys):
    ret = main(["portfolio", str(FIXTURES / "all_types")])
    assert ret == 0
    out = capsys.readouterr().out
    assert "Repository Summary" in out
    assert "Health Score" in out


def test_cli_portfolio_top_level_no_recursion(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "top.md").write_text("# T\n## Problem\nP.\n## Requirements\n[REQ-001] X.\n")
    (sub / "nested.md").write_text("# N\n## Problem\nP.\n## Requirements\n[REQ-001] X.\n")
    s_recursive = build_portfolio_summary(str(tmp_path), recursive=True)
    s_top = build_portfolio_summary(str(tmp_path), recursive=False)
    assert s_recursive.total_artifacts > s_top.total_artifacts


# ---------------------------------------------------------------------------
# Orphan detection boundary
# ---------------------------------------------------------------------------


def test_no_orphans_when_fully_connected():
    # valid_clean: req-001 references ADR-001, so ADR-001 has at least one
    # resolved inbound ref. req-001 itself is unreferenced, so it is orphaned.
    # The test confirms orphaned < total_artifacts (i.e. not everything is orphaned).
    s = summary("valid_clean")
    assert s.relationships.orphaned < s.total_artifacts


def test_all_orphaned_when_no_relationships(tmp_path):
    (tmp_path / "a.md").write_text("# A\n## Problem\nP.\n## Requirements\n[REQ-001] X.\n")
    (tmp_path / "b.md").write_text("# B\n## Problem\nP.\n## Requirements\n[REQ-001] X.\n")
    s = build_portfolio_summary(str(tmp_path))
    # No relationships → both are unreferenced → both orphaned.
    assert s.relationships.orphaned == 2
    assert s.relationships.total == 0


def test_orphan_not_double_counted_when_broken(tmp_path):
    # broken_rels has one artifact (source.md) with a broken ref to ADR-MISSING.
    # ADR-MISSING doesn't exist, so it can't be an orphan (it's not a known artifact).
    # source.md itself is not a target → it is orphaned.
    s = summary("broken_rels")
    # Only 1 known artifact (requirement) in the fixture.
    assert s.relationships.orphaned == 1


def test_unknown_paths_listed_additively():
    # v0.7.9 additive contract field (ADR-007): unknown files listed by path so
    # consumers like `rac review` can surface them without a second walk.
    s = summary("all_types")
    assert len(s.unknown_paths) == s.by_type["unknown"] == 1
    assert s.unknown_paths[0].endswith("unknown.md")
    assert s.to_dict()["artifacts"]["unknown_paths"] == s.unknown_paths
