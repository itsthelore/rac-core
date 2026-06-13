"""Tests for repository state comparison (v0.12.0).

The watchkeeper fixtures plant one case per delta: an added requirement
(billing), a modified requirement (checkout), a newly invalid requirement
(payouts, duplicate IDs), a removed requirement (legacy-upload), and a
relationship broken purely by that removal (adr-001 is byte-identical in
both states, its reference target is gone).
"""

from __future__ import annotations

from conftest import fixture_path

from rac.services.compare import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    compare_states,
    load_state,
)


def make_comparison():
    base = load_state(fixture_path("watchkeeper", "base"), label="base")
    head = load_state(fixture_path("watchkeeper", "head"), label="head")
    return compare_states(base, head)


def test_state_labels():
    state = load_state(fixture_path("watchkeeper", "base"), label="main")
    assert state.label == "main"
    # Without an explicit label the directory stands in.
    unlabeled = load_state(fixture_path("watchkeeper", "base"))
    assert unlabeled.label == unlabeled.directory


def test_changes_are_keyed_by_corpus_relative_path():
    comparison = make_comparison()
    assert [(c.change, c.path) for c in comparison.changes] == [
        (CHANGE_ADDED, "requirements/billing.md"),
        (CHANGE_MODIFIED, "requirements/checkout.md"),
        (CHANGE_MODIFIED, "requirements/payouts.md"),
        (CHANGE_REMOVED, "requirements/legacy-upload.md"),
    ]


def test_unchanged_artifacts_do_not_appear():
    comparison = make_comparison()
    paths = {c.path for c in comparison.changes}
    assert "decisions/adr-001-payment-provider.md" not in paths
    assert "roadmaps/q3-payments.md" not in paths


def test_added_artifact_has_no_base_status():
    comparison = make_comparison()
    added = next(c for c in comparison.changes if c.change == CHANGE_ADDED)
    assert added.type == "requirement"
    assert added.base_status is None
    assert added.head_status == "valid"
    assert added.diff is None


def test_removed_artifact_has_no_head_status():
    comparison = make_comparison()
    removed = next(c for c in comparison.changes if c.change == CHANGE_REMOVED)
    assert removed.base_status == "valid"
    assert removed.head_status is None


def test_modified_artifact_carries_requirement_diff():
    comparison = make_comparison()
    checkout = next(c for c in comparison.changes if c.path == "requirements/checkout.md")
    assert checkout.diff is not None
    assert [c.id for c in checkout.diff.modified_requirements] == ["REQ-001"]
    change = checkout.diff.modified_requirements[0]
    assert "within 2 seconds" in change.old_text
    assert "quickly" in change.new_text


def test_validation_delta():
    comparison = make_comparison()
    validation = comparison.validation
    assert (validation.base_valid, validation.base_invalid) == (5, 0)
    assert (validation.head_valid, validation.head_invalid) == (4, 1)
    assert validation.newly_invalid == ("requirements/payouts.md",)
    assert validation.newly_valid == ()


def test_relationship_delta_catches_break_without_artifact_change():
    comparison = make_comparison()
    relationships = comparison.relationships
    assert relationships.base.broken == 0
    assert relationships.head.broken == 1
    assert relationships.resolved_issues == ()
    assert len(relationships.new_issues) == 1
    issue = relationships.new_issues[0]
    assert issue.code == "relationship-target-not-found"
    assert issue.path == "decisions/adr-001-payment-provider.md"
    assert issue.target == "legacy-upload"


def test_stats_delta():
    comparison = make_comparison()
    stats = comparison.stats
    assert stats.total == (5, 5)
    assert stats.by_type["requirement"] == (3, 3)
    assert stats.by_type["decision"] == (1, 1)
    assert stats.by_type["roadmap"] == (1, 1)


def test_identical_states_compare_empty():
    state = load_state(fixture_path("watchkeeper", "base"))
    comparison = compare_states(state, state)
    assert comparison.changes == []
    assert comparison.validation.newly_invalid == ()
    assert comparison.relationships.new_issues == ()
    assert comparison.relationships.resolved_issues == ()


def test_empty_base_reports_everything_added(tmp_path):
    base = load_state(str(tmp_path), label="empty")
    head = load_state(fixture_path("watchkeeper", "base"))
    comparison = compare_states(base, head)
    assert all(c.change == CHANGE_ADDED for c in comparison.changes)
    assert len(comparison.changes) == 5
