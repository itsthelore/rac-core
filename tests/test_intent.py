"""Tests for deterministic intent analysis (v0.12.1).

Positive cases ride the shared watchkeeper fixtures; boundary cases that
must NOT fire build minimal corpora under ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

from conftest import fixture_path

from rac.services.compare import compare_states, load_state
from rac.services.intent import (
    ACCEPTANCE_CRITERIA_REMOVED,
    AMBIGUITY_INTRODUCED,
    CONSTRAINT_REMOVED,
    CONSTRAINT_WEAKENED,
    RELATIONSHIP_IMPACT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SPECIFICITY_REGRESSION,
    SUCCESS_MEASURES_REMOVED,
    UNLINKED_SCOPE,
    analyze_intent,
)


def fixture_findings():
    base = load_state(fixture_path("watchkeeper", "base"))
    head = load_state(fixture_path("watchkeeper", "head"))
    return analyze_intent(compare_states(base, head))


def by_code(findings, code):
    return [f for f in findings if f.code == code]


def _corpus(root: Path, name: str, files: dict[str, str]) -> str:
    directory = root / name
    for rel, text in files.items():
        target = directory / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


def _requirement(req_lines: str, extra_sections: str = "") -> str:
    return (
        "# Upload\n\n## Problem\n\nUploads are slow.\n\n## Requirements\n\n"
        + req_lines
        + "\n"
        + extra_sections
    )


def _findings_for(tmp_path: Path, base_files: dict[str, str], head_files: dict[str, str]):
    base = load_state(_corpus(tmp_path, "base", base_files))
    head = load_state(_corpus(tmp_path, "head", head_files))
    return analyze_intent(compare_states(base, head))


# --- positives (shared fixtures) ---------------------------------------------


def test_specificity_regression_detected():
    findings = by_code(fixture_findings(), SPECIFICITY_REGRESSION)
    assert [f.path for f in findings] == ["requirements/checkout.md"]
    finding = findings[0]
    assert finding.severity == SEVERITY_WARNING
    assert "REQ-001" in finding.detail
    assert finding.evidence == (
        "- Payment confirmation must complete within 2 seconds",
        "+ Payment confirmation should complete quickly",
    )


def test_ambiguity_introduced_detected():
    findings = by_code(fixture_findings(), AMBIGUITY_INTRODUCED)
    assert [f.path for f in findings] == ["requirements/checkout.md"]
    assert "'quickly'" in findings[0].detail


def test_constraint_weakened_detected():
    findings = by_code(fixture_findings(), CONSTRAINT_WEAKENED)
    assert [f.path for f in findings] == ["requirements/checkout.md"]
    assert "REQ-001" in findings[0].detail


def test_constraint_removed_for_removed_artifact():
    findings = by_code(fixture_findings(), CONSTRAINT_REMOVED)
    assert [f.path for f in findings] == ["requirements/legacy-upload.md"]
    assert findings[0].evidence == ("- Upload must complete within 5 seconds",)


def test_acceptance_criteria_removed_detected():
    findings = by_code(fixture_findings(), ACCEPTANCE_CRITERIA_REMOVED)
    assert [f.path for f in findings] == ["requirements/checkout.md"]


def test_unlinked_scope_detected():
    findings = by_code(fixture_findings(), UNLINKED_SCOPE)
    assert [f.path for f in findings] == ["requirements/billing.md"]


def test_relationship_impact_is_informational():
    findings = by_code(fixture_findings(), RELATIONSHIP_IMPACT)
    assert [f.path for f in findings] == [
        "requirements/checkout.md",
        "requirements/legacy-upload.md",
    ]
    assert all(f.severity == SEVERITY_INFO for f in findings)
    assert all(f.evidence for f in findings)


def test_findings_order_warnings_first_then_code_then_path():
    findings = fixture_findings()
    keys = [(f.severity != SEVERITY_WARNING, f.code, f.path, f.detail) for f in findings]
    assert keys == sorted(keys)


# --- boundaries (must not fire) -----------------------------------------------


def test_rewording_that_keeps_the_number_is_not_a_regression(tmp_path):
    findings = _findings_for(
        tmp_path,
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds")},
        {"upload.md": _requirement("[REQ-001] Upload must finish within 5 seconds")},
    )
    assert by_code(findings, SPECIFICITY_REGRESSION) == []


def test_preexisting_ambiguous_term_is_not_reintroduced(tmp_path):
    findings = _findings_for(
        tmp_path,
        {"upload.md": _requirement("[REQ-001] Upload feels fast on retry")},
        {"upload.md": _requirement("[REQ-001] Upload feels fast on every retry")},
    )
    assert by_code(findings, AMBIGUITY_INTRODUCED) == []


def test_ambiguity_matches_tokens_not_substrings(tmp_path):
    # "breakfast" contains "fast"; token-boundary matching must not fire.
    findings = _findings_for(
        tmp_path,
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds")},
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds of breakfast")},
    )
    assert by_code(findings, AMBIGUITY_INTRODUCED) == []


def test_mandatory_to_mandatory_rewording_is_not_weakening(tmp_path):
    findings = _findings_for(
        tmp_path,
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds")},
        {"upload.md": _requirement("[REQ-001] Upload shall complete within 5 seconds")},
    )
    assert by_code(findings, CONSTRAINT_WEAKENED) == []


def test_removed_requirement_without_mandatory_wording_is_not_flagged(tmp_path):
    findings = _findings_for(
        tmp_path,
        {
            "upload.md": _requirement(
                "[REQ-001] Upload must complete within 5 seconds\n"
                "[REQ-002] User can see upload history"
            )
        },
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds")},
    )
    assert by_code(findings, CONSTRAINT_REMOVED) == []


def test_success_measures_removed_detected(tmp_path):
    metrics = "\n## Success Metrics\n\n- Upload p95 stays under 5 seconds\n"
    findings = _findings_for(
        tmp_path,
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds", metrics)},
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds")},
    )
    flagged = by_code(findings, SUCCESS_MEASURES_REMOVED)
    assert [f.path for f in flagged] == ["upload.md"]


def test_emptied_section_counts_as_removed(tmp_path):
    filled = "\n## Acceptance Criteria\n\n- Upload confirms within budget\n"
    emptied = "\n## Acceptance Criteria\n"
    findings = _findings_for(
        tmp_path,
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds", filled)},
        {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds", emptied)},
    )
    assert [f.path for f in by_code(findings, ACCEPTANCE_CRITERIA_REMOVED)] == ["upload.md"]


def test_added_artifact_with_a_relationship_is_not_unlinked(tmp_path):
    base_files = {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds")}
    head_files = dict(base_files)
    head_files["billing.md"] = (
        "# Billing\n\n## Problem\n\nNo reports.\n\n## Requirements\n\n"
        "[REQ-001] User can export a payout report\n\n## Related Requirements\n\n- upload\n"
    )
    findings = _findings_for(tmp_path, base_files, head_files)
    assert by_code(findings, UNLINKED_SCOPE) == []


def test_added_ambiguous_requirement_is_flagged(tmp_path):
    base_files = {"upload.md": _requirement("[REQ-001] Upload must complete within 5 seconds")}
    head_files = dict(base_files)
    head_files["checkout.md"] = (
        "# Checkout\n\n## Problem\n\nCarts are abandoned.\n\n## Requirements\n\n"
        "[REQ-001] Checkout should be seamless\n"
    )
    findings = _findings_for(tmp_path, base_files, head_files)
    flagged = by_code(findings, AMBIGUITY_INTRODUCED)
    assert [f.path for f in flagged] == ["checkout.md"]
    assert "'seamless'" in flagged[0].detail


def test_identical_states_produce_no_findings():
    state = load_state(fixture_path("watchkeeper", "base"))
    assert analyze_intent(compare_states(state, state)) == []
