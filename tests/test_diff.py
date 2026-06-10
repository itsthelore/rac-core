"""Tests for AST-level diffing."""

from __future__ import annotations

from conftest import fixture_path

from rac.core.markdown import parse_file
from rac.services.diff import diff


def make_diff():
    old = parse_file(fixture_path("diff", "old.md"))
    new = parse_file(fixture_path("diff", "new.md"))
    return diff(old, new)


def test_added_requirements():
    d = make_diff()
    assert [r.id for r in d.added_requirements] == ["REQ-004"]


def test_removed_requirements():
    d = make_diff()
    assert [r.id for r in d.removed_requirements] == ["REQ-003"]


def test_modified_requirements():
    d = make_diff()
    assert [c.id for c in d.modified_requirements] == ["REQ-002"]
    change = d.modified_requirements[0]
    assert "or SMS" in change.new_text
    assert "or SMS" not in change.old_text


def test_unchanged_requirements_are_omitted():
    d = make_diff()
    touched = (
        {r.id for r in d.added_requirements}
        | {r.id for r in d.removed_requirements}
        | {c.id for c in d.modified_requirements}
    )
    assert "REQ-001" not in touched  # identical in both versions


def test_metric_changes():
    d = make_diff()
    assert d.added_metrics == ["Digest opt-in rate above 20%"]
    assert d.removed_metrics == ["Open rate above 40%"]


def test_risk_changes():
    d = make_diff()
    assert d.added_risks == ["SMS delivery adds per-message cost"]
    assert d.removed_risks == []


def test_identical_files_have_empty_diff():
    a = parse_file(fixture_path("diff", "old.md"))
    b = parse_file(fixture_path("diff", "old.md"))
    assert diff(a, b).is_empty()
