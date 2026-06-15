"""Contract + offline-integrity tests for the real (public-derived) corpora.

These guard the credibility surface for scenarios under `scenarios_real/`:

* the scenario loads and schema-validates;
* its typed `supersedes` structure is internally consistent;
* every corpus file embeds the exact upstream bytes recorded in provenance.json
  (checked offline by re-hashing the embedded text — no network);
* the harness scores the scenario without error.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from providers import build_provider, make_answering_model
from scenarios.loader import load_scenario, load_scenarios
from scoring.scorer import score

_ROOT = Path(__file__).resolve().parent.parent
_REAL_DIR = _ROOT / "scenarios_real"
_PILOT = _REAL_DIR / "peps_version_supersession"


def test_real_scenarios_load_and_validate():
    scenarios = load_scenarios(_REAL_DIR)
    assert scenarios, "expected at least one real scenario"
    for sc in scenarios:
        assert sc.corpus, f"{sc.scenario_id} has an empty corpus"


def test_pilot_supersession_structure():
    sc = load_scenario(_PILOT)
    assert sc.scenario_type == "superseded_decision"
    assert sc.expected_tie is False
    edges = [(r.source, r.type, r.target) for r in sc.relationships]
    assert ("PEP-0440", "supersedes", "PEP-0386") in edges
    # The governing decision is the superseding PEP, and it binds.
    assert sc.gold_label.governing_decision == "PEP-0440"
    assert "PEP-0440" in sc.binding_decisions
    # The artifact-level supersedes mirror matches the typed edge.
    superseding = next(a for a in sc.corpus if a.id == "PEP-0440")
    assert "PEP-0386" in superseding.supersedes


def test_pilot_corpus_matches_provenance_hashes_offline():
    """Each corpus file must embed exactly the upstream bytes recorded in
    provenance.json. Re-hash the embedded body; no network required."""
    provenance = json.loads((_PILOT / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["pinned_commit"]
    for entry in provenance["peps"]:
        md = (_PILOT / entry["file"]).read_text(encoding="utf-8")
        # corpus_markdown() = provenance preamble + "\n\n---\n\n" + verbatim rst.
        body = md.split("\n\n---\n\n", 1)[1]
        got = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert got == entry["source_sha256"], f"{entry['id']} body drifted from pin"


def test_pilot_scores_without_error_offline():
    sc = load_scenario(_PILOT)
    model = make_answering_model("offline-stub", seed=0)
    for arm in ("context_dump", "naive_rag", "no_grounding"):
        provider = build_provider(arm, model, "local-hash")
        provider.prepare(list(sc.corpus))
        pc = provider.respond(sc.task)
        result = score(sc, pc)
        # The scorer returns a well-formed verdict; offline-stub adherence is not
        # asserted (it is a plumbing illustration, not a benchmark result).
        assert isinstance(result.adherent, bool)
        assert isinstance(result.stale_decision_followed, bool)


def test_pilot_gold_label_is_not_a_negative_control():
    # A superseded-decision pilot must name a governing decision; a null would be
    # the negative-control shape and would mis-score.
    sc = load_scenario(_PILOT)
    assert sc.gold_label.governing_decision is not None
    assert sc.gold_label.verdict in ("permitted", "prohibited")
