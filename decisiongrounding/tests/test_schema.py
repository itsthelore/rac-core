"""Scenario schema validity: the worked scenarios load; a malformed one fails."""

import copy
import json
from pathlib import Path

import pytest

from scenarios.loader import _fallback_validate, load_scenarios

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"


def test_all_worked_scenarios_load():
    scenarios = load_scenarios(_SCENARIOS)
    ids = {s.scenario_id for s in scenarios}
    assert {
        "simple_adherence_logging",
        "superseded_decision",
        "prohibition_language_migration",
        "negative_control_cache_ttl",
    } <= ids
    for s in scenarios:
        assert s.corpus  # corpus text was loaded
        for a in s.corpus:
            assert a.text.strip()


def test_supersedes_relationship_present():
    superseded = next(
        s for s in load_scenarios(_SCENARIOS) if s.scenario_id == "superseded_decision"
    )
    edges = [(r.source, r.type, r.target) for r in superseded.relationships]
    assert ("DG-ADR-DBA-002", "supersedes", "DG-ADR-DBA-001") in edges


def test_negative_control_has_null_governing_decision():
    nc = next(
        s for s in load_scenarios(_SCENARIOS) if s.scenario_type == "negative_control"
    )
    assert nc.gold_label.governing_decision is None
    assert nc.gold_label.verdict == "permitted"


def _raw(scenario_id: str) -> dict:
    return json.loads((_SCENARIOS / scenario_id / "scenario.json").read_text())


def test_malformed_scenario_rejected_missing_key():
    raw = _raw("superseded_decision")
    del raw["gold_label"]
    with pytest.raises(ValueError):
        _fallback_validate(raw)


def test_malformed_scenario_rejected_bad_type():
    raw = copy.deepcopy(_raw("superseded_decision"))
    raw["scenario_type"] = "not_a_real_type"
    with pytest.raises(ValueError):
        _fallback_validate(raw)


def test_malformed_scenario_rejected_bad_verdict():
    raw = copy.deepcopy(_raw("superseded_decision"))
    raw["gold_label"]["verdict"] = "maybe"
    with pytest.raises(ValueError):
        _fallback_validate(raw)
