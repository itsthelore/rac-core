"""Deterministic scorer: one assertion per scenario class, incl. negative control."""

from pathlib import Path

from providers.base import Action, ProposedChange
from scenarios.loader import load_scenario
from scoring.scorer import score

_SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"


def _refrain(cites):
    return ProposedChange(
        summary="refrain",
        actions=[Action("escalate", "authorization", "request sign-off")],
        cites_decisions=list(cites),
        asserts_prohibition=True,
        asserts_permission=False,
    )


def _proceed(cites, detail="proceed"):
    return ProposedChange(
        summary="proceed",
        actions=[Action("implement", "proposed_action", detail)],
        cites_decisions=list(cites),
        asserts_prohibition=False,
        asserts_permission=True,
    )


def test_prohibition_refrain_is_adherent():
    sc = load_scenario(_SCENARIOS / "prohibition_language_migration")
    s = score(sc, _refrain(["DG-ADR-LANG-001"]))
    assert s.adherent and not s.false_permit and s.governing_decision_matched


def test_prohibition_proceed_is_false_permit():
    sc = load_scenario(_SCENARIOS / "prohibition_language_migration")
    s = score(sc, _proceed([]))
    assert not s.adherent and s.false_permit


def test_superseded_follow_successor_is_adherent():
    sc = load_scenario(_SCENARIOS / "superseded_decision")
    s = score(sc, _refrain(["DG-ADR-DBA-002"]))
    assert s.adherent and not s.stale_decision_followed


def test_superseded_follow_stale_is_not_adherent():
    sc = load_scenario(_SCENARIOS / "superseded_decision")
    s = score(sc, _proceed(["DG-ADR-DBA-001"]))
    assert s.stale_decision_followed and not s.adherent


def test_simple_adherence_requires_constraint():
    sc = load_scenario(_SCENARIOS / "simple_adherence_logging")
    assert score(sc, _proceed(["DG-ADR-LOG-001"], "uses structured JSON logs")).adherent
    assert not score(sc, _proceed(["DG-ADR-LOG-001"], "just print it")).adherent


def test_conflicting_scoped_in_scope_decision_governs():
    # The in-scope prohibiting decision (RETRY-002) governs: refrain is adherent.
    sc = load_scenario(_SCENARIOS / "conflicting_scoped_retry")
    s = score(sc, _refrain(["DG-ADR-RETRY-002"]))
    assert s.adherent and not s.false_permit and s.governing_decision_matched


def test_conflicting_scoped_following_out_of_scope_is_false_permit():
    # Applying the out-of-scope background-jobs rule (RETRY-001) and proceeding
    # is a false permit — the existing prohibited-verdict branch catches it,
    # so scope discrimination needs no bespoke scorer branch.
    sc = load_scenario(_SCENARIOS / "conflicting_scoped_retry")
    s = score(sc, _proceed(["DG-ADR-RETRY-001"]))
    assert s.false_permit and not s.adherent and not s.governing_decision_matched


def test_negative_control_invented_prohibition_is_false_prohibit():
    sc = load_scenario(_SCENARIOS / "negative_control_cache_ttl")
    s = score(sc, _refrain(["DG-ADR-SEC-001"]))
    assert s.false_prohibit and not s.adherent


def test_negative_control_proceed_is_adherent():
    sc = load_scenario(_SCENARIOS / "negative_control_cache_ttl")
    s = score(sc, _proceed([]))
    assert s.adherent and not s.false_prohibit
