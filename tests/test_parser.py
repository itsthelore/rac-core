"""Tests for the Markdown -> Product AST parser."""

from __future__ import annotations

from conftest import fixture_path

from rac.core.markdown import parse, parse_file


def test_parses_basic_structure():
    p = parse_file(fixture_path("valid", "feature.md"))
    assert p.title == "Search Filters"
    assert "narrow large result sets" in p.problem
    assert [r.id for r in p.requirements] == ["REQ-001", "REQ-002"]
    assert p.success_metrics == ["Median results-per-search drops below 20"]
    assert p.risks == ["Filter combinations could produce confusing empty states"]
    assert p.has_problem_section and p.has_requirements_section
    assert p.has_metrics_section and p.has_risks_section


def test_headings_are_case_insensitive_and_trimmed():
    text = "# T\n\n##   problem  \n\nbody\n\n##\tREQUIREMENTS\n\n[REQ-001] do it\n"
    p = parse(text)
    assert p.has_problem_section
    assert p.has_requirements_section
    assert [r.id for r in p.requirements] == ["REQ-001"]


def test_requirement_ids_preserved_exactly():
    text = "# T\n\n## Problem\n\nx\n\n## Requirements\n\n[REQ-007] keep zero padding\n"
    p = parse(text)
    assert p.requirements[0].id == "REQ-007"


def test_line_numbers_are_tracked():
    p = parse_file(fixture_path("valid", "feature.md"))
    # Requirements start on line 9 in the fixture.
    assert p.requirements[0].line == 9
    assert p.requirements[1].line == 10


def test_bullet_and_plain_requirements_both_parse():
    bullets = parse_file(fixture_path("valid", "bullet_requirements.md"))
    assert [r.id for r in bullets.requirements] == ["REQ-001", "REQ-002"]


def test_malformed_lines_are_captured_not_dropped():
    text = "# T\n\n## Problem\n\nx\n\n## Requirements\n\n[REQ-1A] bad id\nno id at all\n[REQ-002]\n"
    p = parse(text)
    assert p.requirements == []
    kinds = {(m.bad_id, m.empty_text) for m in p.malformed_requirements}
    assert ("REQ-1A", False) in kinds  # malformed id
    assert (None, False) in kinds  # missing id
    assert ("REQ-002", True) in kinds  # empty text


def test_absent_vs_empty_problem():
    absent = parse("# T\n\n## Requirements\n\n[REQ-001] x\n")
    assert absent.problem is None
    assert not absent.has_problem_section

    empty = parse("# T\n\n## Problem\n\n## Requirements\n\n[REQ-001] x\n")
    assert empty.has_problem_section
    assert empty.problem == ""
