"""End-to-end offline smoke of the two real arms + RunResult shape + crossover."""

import json
from pathlib import Path

from providers import ScriptedAnsweringModel
from runner.cli import run_one
from scenarios.loader import load_scenarios
from scoring.crossover import build_dataset

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"
_RUN_SCHEMA = _ROOT / "schema" / "run_result.schema.json"

_REQUIRED = {
    "run_id", "timestamp", "arm", "scenario_id", "corpus_size_N",
    "answering_model", "grounding", "proposed_change", "score", "harness_version",
}


def _validate_run(rr: dict):
    try:
        import jsonschema  # type: ignore

        jsonschema.validate(rr, json.loads(_RUN_SCHEMA.read_text()))
    except ImportError:
        assert _REQUIRED <= set(rr), f"missing keys: {_REQUIRED - set(rr)}"


def test_both_real_arms_run_and_emit_valid_runresults():
    model = ScriptedAnsweringModel(seed=0)
    scenarios = load_scenarios(_SCENARIOS)
    for arm in ("context_dump", "naive_rag"):
        for sc in scenarios:
            rr = run_one(arm, sc, model, seed=0)
            _validate_run(rr)
            assert rr["arm"] == arm


def test_tiny_corpus_is_an_expected_tie():
    # On the tiny corpus both real arms should adhere on every worked scenario.
    model = ScriptedAnsweringModel(seed=0)
    for arm in ("context_dump", "naive_rag"):
        for sc in load_scenarios(_SCENARIOS):
            rr = run_one(arm, sc, model, seed=0)
            assert rr["score"]["adherent"], (arm, sc.scenario_id)


def test_crossover_shows_naive_rag_degrading_and_context_dump_holding():
    scenarios = load_scenarios(_SCENARIOS)
    ds = build_dataset(scenarios, arms=("context_dump", "naive_rag"), seed=0)

    cd = [p["adherence_rate"] for p in ds["arms"]["context_dump"]]
    nr = [p["adherence_rate"] for p in ds["arms"]["naive_rag"]]

    # context_dump holds; naive_rag starts tied and ends strictly worse.
    assert all(r == 1.0 for r in cd)
    assert nr[0] == 1.0
    assert nr[-1] < cd[-1]

    # The supersession case is where chunked retrieval severs the relationship.
    sup = ds["per_scenario"]["naive_rag"]["superseded_decision"]
    assert sup[0]["adherent"] is True       # tie at small N
    assert sup[-1]["adherent"] is False     # severed at large N
    assert sup[-1]["stale_decision_followed"] is True
