"""Tests for per-type standards checks (v0.17.1, ADR-056).

Requirements: BCP-14 keyword discipline (error), 29148 singular (warning), and
EARS (warnings). Roadmaps: optional horizon and an advancement-linkage warning.
Plus the repository-wide reach of severity overrides (ADR-053, revised): a rule a
repo downgrades in .decided/config.yaml is downgraded for `decided review`/portfolio too,
not only `decided validate`.
"""

from __future__ import annotations

from asdecided.core.markdown import parse
from asdecided.core.validation import validate
from asdecided.services.portfolio import build_portfolio_summary

REQ = "# R\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] {line}\n"
ROADMAP = "# R\n\n## Outcomes\n\no\n\n## Initiatives\n\ni\n{extra}"


def codes(text):
    return {i.code for i in validate(parse(text))}


# --- requirements: BCP-14 ----------------------------------------------------


def test_lowercase_normative_keyword_is_error():
    assert "requirement-normative-keyword" in codes(
        REQ.format(line="The system shall export data.")
    )
    assert "requirement-normative-keyword" in codes(REQ.format(line="It must be fast."))


def test_uppercase_normative_keyword_is_clean():
    c = codes(REQ.format(line="The system SHALL export all account data within 24 hours."))
    assert "requirement-normative-keyword" not in c
    assert "requirement-non-ears" not in c
    assert "requirement-not-singular" not in c


def test_must_not_uppercase_is_clean():
    assert "requirement-normative-keyword" not in codes(
        REQ.format(line="Deactivated accounts MUST NOT be returned by default queries.")
    )


# --- requirements: 29148 singular --------------------------------------------


def test_two_normative_keywords_not_singular():
    c = codes(REQ.format(line="The system SHALL log in and SHALL also export."))
    assert "requirement-not-singular" in c


# --- requirements: EARS ------------------------------------------------------


def test_no_normative_keyword_is_non_ears():
    assert "requirement-non-ears" in codes(REQ.format(line="User can filter results by category."))


def test_if_without_then_flags_ears_clause():
    c = codes(REQ.format(line="If the upload fails, the system SHALL retry."))
    assert "requirement-ears-clause" in c


def test_if_then_is_clean():
    c = codes(REQ.format(line="If the upload fails, then the system SHALL retry once."))
    assert "requirement-ears-clause" not in c


# --- roadmaps: horizon + linkage ---------------------------------------------


def test_invalid_horizon_is_error():
    c = codes(ROADMAP.format(extra="\n## Horizon\n\nsoonish\n"))
    assert "invalid-roadmap-horizon" in c


def test_valid_horizon_passes():
    assert "invalid-roadmap-horizon" not in codes(ROADMAP.format(extra="\n## Horizon\n\nnext\n"))
    assert "invalid-roadmap-horizon" not in codes(ROADMAP.format(extra="\n## Horizon\n\nQ3 2026\n"))


def test_absent_horizon_is_fine():
    assert "invalid-roadmap-horizon" not in codes(ROADMAP.format(extra=""))


def test_roadmap_without_advancement_link_warns():
    assert "roadmap-no-advancement-link" in codes(ROADMAP.format(extra=""))


def test_roadmap_with_decision_link_is_clean():
    c = codes(ROADMAP.format(extra="\n## Related Decisions\n\n- adr-049\n"))
    assert "roadmap-no-advancement-link" not in c


# --- overrides are repository-wide (ADR-053 revised) -------------------------

BAD_REQ = "# R\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] The system shall export.\n"


def test_review_honours_repository_overrides(tmp_path):
    (tmp_path / "r.md").write_text(BAD_REQ, encoding="utf-8")
    cfg = tmp_path / ".decided"
    cfg.mkdir()
    # No overrides: the BCP-14 error makes the artifact invalid in the portfolio.
    cfg.joinpath("config.yaml").write_text("repository_key: RAC\n", encoding="utf-8")
    assert build_portfolio_summary(str(tmp_path)).invalid_artifacts == 1
    # Downgraded: review/portfolio see it clean too, not just `decided validate`.
    cfg.joinpath("config.yaml").write_text(
        "repository_key: RAC\nvalidation:\n  rules:\n    requirement-normative-keyword: off\n",
        encoding="utf-8",
    )
    assert build_portfolio_summary(str(tmp_path)).invalid_artifacts == 0
