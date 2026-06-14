"""Cover the real-backend wiring: recall metric, supersedes resolution, pins.

These exercise the offline-testable surface of Steps 1-3 (real answering model,
real embeddings, rac arm). The backends that need network/credentials/the rac
CLI are constructed but not invoked here.
"""

from pathlib import Path

import pytest

from providers import (
    ClaudeAnsweringModel,
    LocalDeterministicEmbedder,
    ScriptedAnsweringModel,
    VoyageEmbedder,
    make_embedder,
    resolve_supersedes,
)
from runner.cli import run_one
from scenarios.loader import load_scenario
from scoring import recall_rate

_SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"


# --- resolve_supersedes (pure, the heart of the rac thesis) -----------------

def test_resolve_supersedes_replaces_stale_with_successor():
    # B supersedes A; a search that matched A should ground on B instead.
    out = resolve_supersedes(["A"], [("B", "A")], corpus_ids={"A", "B"}, top_k=4)
    assert out == ["B"]


def test_resolve_supersedes_is_transitive():
    # C supersedes B supersedes A → A resolves to C.
    edges = [("B", "A"), ("C", "B")]
    out = resolve_supersedes(["A"], edges, corpus_ids={"A", "B", "C"}, top_k=4)
    assert out == ["C"]


def test_resolve_supersedes_dedupes_and_caps():
    edges = [("B", "A")]
    out = resolve_supersedes(["A", "B", "X", "Y", "Z"], edges, {"A", "B", "X", "Y", "Z"}, top_k=3)
    assert out == ["B", "X", "Y"]  # A→B collapses with the matched B, then capped


# --- recall metric ----------------------------------------------------------

def test_recall_rate_excludes_negative_controls():
    assert recall_rate([True, False, None, True]) == pytest.approx(2 / 3)
    assert recall_rate([None, None]) is None
    assert recall_rate([]) is None


def test_run_one_emits_governing_recall_on_tiny_corpus():
    model = ScriptedAnsweringModel(seed=0)
    sc = load_scenario(_SCENARIOS / "superseded_decision")
    rr = run_one("naive_rag", sc, model, seed=0)
    # Tiny corpus: the governing (superseding) decision is retrieved.
    assert rr["retrieval"]["governing_decision_retrieved"] is True


def test_negative_control_recall_is_null():
    model = ScriptedAnsweringModel(seed=0)
    sc = load_scenario(_SCENARIOS / "negative_control_cache_ttl")
    rr = run_one("context_dump", sc, model, seed=0)
    assert rr["retrieval"]["governing_decision_retrieved"] is None


# --- embedder factory + pinned answering model ------------------------------

def test_make_embedder_offline_default():
    assert isinstance(make_embedder("local-hash"), LocalDeterministicEmbedder)


def test_make_embedder_constructs_real_backends_lazily():
    # Constructing must not require the optional dependency (import is lazy).
    e = make_embedder("voyage:voyage-3")
    assert isinstance(e, VoyageEmbedder)
    assert e.name == "voyage:voyage-3"


def test_claude_answering_model_is_pinned():
    m = ClaudeAnsweringModel(seed=0)
    assert m.version == "claude-opus-4-8"  # pinned model id
    assert m.temperature is None  # Opus 4.8 exposes no temperature/seed knob
