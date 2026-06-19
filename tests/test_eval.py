"""Grounding-eval benchmark battery (v0.23.0, WS1).

Proves the gate is real (ADR-027 per-service battery): the scored ``metrics``
are byte-stable on an unchanged corpus, ``--check`` exits 0/1/2 correctly, and
three regression-injection cases each fire a named rule. Tests pass explicit
fixture paths so they never depend on the working directory.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rac import cli
from rac.services import eval as ev

EVAL_DIR = Path(__file__).parent / "eval"
CORPUS = EVAL_DIR / "corpus"
QUERIES = EVAL_DIR / "queries.json"
BASELINE = EVAL_DIR / "baseline.json"
CONFIG = EVAL_DIR / "eval-config.json"

# Fixture ids referenced by the regression cases.
REALTIME_SYNC = "EVAL-STK2ZW0AWS3V"
TOKEN_REFRESH_V2 = "EVAL-JTDKWHNVD8GG"
TOKEN_EXPIRY_V1 = "EVAL-KRRRS99DSV9W"
REQ_OFFLINE = "EVAL-FCTMD6C13A4N"


def _run_cli(argv: list[str], capsys) -> tuple[int, str, str]:
    try:
        code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _check_argv(
    *,
    root: str | None = None,
    queries: str | None = None,
    baseline: str | None = None,
    config: str | None = None,
) -> list[str]:
    return [
        "eval",
        "--check",
        "--root",
        root or str(CORPUS),
        "--queries",
        queries or str(QUERIES),
        "--baseline",
        baseline or str(BASELINE),
        "--config",
        config or str(CONFIG),
    ]


# --- Determinism (REQ-002, Acceptance Criteria) ------------------------------


def test_metrics_are_byte_identical_across_runs():
    a = ev.run_eval(str(CORPUS), str(QUERIES))
    b = ev.run_eval(str(CORPUS), str(QUERIES))
    assert json.dumps(a.metrics, sort_keys=True) == json.dumps(b.metrics, sort_keys=True)


def test_generated_at_lands_only_in_metadata_never_metrics():
    a = ev.run_eval(str(CORPUS), str(QUERIES), generated_at="2020-01-01T00:00:00+00:00")
    b = ev.run_eval(str(CORPUS), str(QUERIES), generated_at="2099-12-31T23:59:59+00:00")
    assert a.metrics == b.metrics
    assert a.metadata["generated_at"] != b.metadata["generated_at"]


# --- Scorecard shape (REQ-005) -----------------------------------------------


def test_scorecard_has_exactly_three_top_level_objects():
    card = ev.run_eval(str(CORPUS), str(QUERIES))
    assert set(card.to_dict()) == {"metrics", "metadata", "per_query"}


def test_metadata_records_versions_hashes_and_count():
    card = ev.run_eval(str(CORPUS), str(QUERIES))
    meta = card.metadata
    assert meta["corpus_hash"].startswith("sha256:")
    assert meta["query_set_hash"].startswith("sha256:")
    assert meta["n_queries"] == len(card.per_query)
    assert "lore_version" in meta and "generated_at" in meta


def test_baseline_meets_initial_floors():
    overall = ev.run_eval(str(CORPUS), str(QUERIES)).metrics["overall"]
    assert overall["negative_violations"] == 0
    assert overall["p_at_1"] >= 0.90
    assert overall["r_at_5"] >= 0.95


# --- Gate exit codes (REQ-006) -----------------------------------------------


def test_check_passes_on_committed_baseline(capsys):
    code, out, _ = _run_cli(_check_argv(), capsys)
    assert code == 0
    assert "PASS" in out


def test_check_missing_baseline_is_usage_error(capsys):
    code, _, err = _run_cli(_check_argv(baseline="/tmp/does-not-exist.json"), capsys)
    assert code == 2
    assert "baseline" in err


def test_check_unreadable_corpus_is_usage_error(capsys):
    code, _, err = _run_cli(_check_argv(root="/tmp/no-such-corpus-dir"), capsys)
    assert code == 2
    assert "corpus" in err


def test_check_malformed_query_set_is_usage_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"cases": [{"id": "X", "tool": "search_artifacts"}]}', encoding="utf-8")
    code, _, err = _run_cli(_check_argv(queries=str(bad)), capsys)
    assert code == 2
    assert "malformed query set" in err


# --- Three regression-injection proofs (Acceptance Criteria) -----------------


def test_injection_1_clean_fixture_passes(capsys):
    code, out, _ = _run_cli(_check_argv(), capsys)
    assert code == 0 and "PASS" in out


def test_injection_2_removed_relevant_artifact_drops_recall(tmp_path, capsys):
    corpus = tmp_path / "corpus"
    shutil.copytree(CORPUS, corpus)
    # requirement-offline-editing is relevant for a feature_lookup case and an
    # impact_analysis case; removing it deterministically drops overall.r_at_5.
    (corpus / "requirement-offline-editing.md").unlink()
    code, out, _ = _run_cli(_check_argv(root=str(corpus)), capsys)
    assert code == 1
    assert "overall.r_at_5" in out
    assert "[regression]" in out or "[floor]" in out


def test_injection_3_forced_hard_negative_fails(tmp_path, capsys):
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))
    # A query whose terms are in the *superseded* decision's title forces it into
    # the top-k, so the hard-negative guard fires.
    queries["cases"].append(
        {
            "id": "QFORCE",
            "tool": "search_artifacts",
            "category": "supersession",
            "query": "static session token expiry",
            "relevant": [TOKEN_REFRESH_V2],
            "must_not_return": [TOKEN_EXPIRY_V1],
        }
    )
    forced = tmp_path / "forced.json"
    forced.write_text(json.dumps(queries), encoding="utf-8")
    code, out, _ = _run_cli(_check_argv(queries=str(forced)), capsys)
    assert code == 1
    assert "[negative_violations]" in out
    assert "negative_violations" in out


# --- Human + JSON output (Acceptance Criteria) -------------------------------


def test_human_summary_lists_all_sections(capsys):
    code, out, _ = _run_cli(["eval", "--root", str(CORPUS), "--queries", str(QUERIES)], capsys)
    assert code == 0
    for heading in ("Overall", "By category", "By tool", "Violations"):
        assert heading in out


def test_json_output_is_the_scorecard_shape(capsys):
    code, out, _ = _run_cli(
        ["eval", "--json", "--root", str(CORPUS), "--queries", str(QUERIES)], capsys
    )
    assert code == 0
    payload = json.loads(out)
    assert set(payload) == {"metrics", "metadata", "per_query"}
    assert payload["metrics"]["overall"]["negative_violations"] == 0


# --- Re-baselining is human-gated; CI never rebaselines (REQ-007) ------------


def test_update_baseline_writes_the_metrics_object(tmp_path, capsys):
    out_baseline = tmp_path / "baseline.json"
    code, _, _ = _run_cli(
        [
            "eval",
            "--update-baseline",
            "--root",
            str(CORPUS),
            "--queries",
            str(QUERIES),
            "--baseline",
            str(out_baseline),
        ],
        capsys,
    )
    assert code == 0
    written = json.loads(out_baseline.read_text(encoding="utf-8"))
    assert written == ev.run_eval(str(CORPUS), str(QUERIES)).metrics


def test_ci_workflows_never_rebaseline():
    """No CI step may run ``--update-baseline`` (REQ-007). Checks executed
    ``run:`` commands, not comment prose, so the gate job can still explain the
    rule it enforces."""
    import yaml

    workflows = Path(__file__).parent.parent / ".github" / "workflows"
    for wf in workflows.glob("*.yml"):
        data = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        for job in (data.get("jobs") or {}).values():
            for step in job.get("steps", []) or []:
                assert "--update-baseline" not in (step.get("run") or ""), wf.name


# --- Real surface, id-membership only (REQ-002, REQ-004, REQ-010) ------------


def test_search_case_consumes_production_order_verbatim():
    from rac.services.index import build_repository_index
    from rac.services.resolve import search_index

    entries = build_repository_index(str(CORPUS)).artifacts
    case = ev.QueryCase(
        id="t",
        tool=ev.TOOL_SEARCH,
        query="refresh token rotation",
        category="c",
        relevant=(TOKEN_REFRESH_V2,),
    )
    expected = [m.id for m in search_index(entries, "refresh token rotation").matches]
    assert ev.returned_ids(str(CORPUS), entries, case) == expected


def test_get_related_scores_incoming_edges():
    entries = []  # unused for get_related
    case = ev.QueryCase(
        id="t",
        tool=ev.TOOL_GET_RELATED,
        query=REALTIME_SYNC,
        category="impact_analysis",
        relevant=(REQ_OFFLINE,),
    )
    returned = ev.returned_ids(str(CORPUS), entries, case)
    assert REQ_OFFLINE in returned
    # Only artifacts that reference realtime-sync — the superseded decision is not
    # an incoming edge and must not appear.
    assert TOKEN_EXPIRY_V1 not in returned


def test_additive_evidence_fields_do_not_shift_membership(monkeypatch):
    """REQ-010: scoring compares only returned-id membership, so additive WS2
    evidence/snippet fields on retrieval output cannot move a metric."""
    from rac.services.index import build_repository_index

    entries = build_repository_index(str(CORPUS)).artifacts
    case = ev.QueryCase(
        id="t",
        tool=ev.TOOL_SEARCH,
        query="refresh token rotation",
        category="c",
        relevant=(TOKEN_REFRESH_V2,),
    )
    baseline_ids = ev.returned_ids(str(CORPUS), entries, case)

    real_search_index = ev.search_index

    def _with_evidence(entries_arg, query, artifact_type=None):
        result = real_search_index(entries_arg, query, artifact_type=artifact_type)
        for match in result.matches:
            # Simulate an additive WS2 evidence field hanging off each result.
            match.evidence = {"field": "title", "terms": ["refresh"], "tier": "title"}
        return result

    monkeypatch.setattr(ev, "search_index", _with_evidence)
    assert ev.returned_ids(str(CORPUS), entries, case) == baseline_ids

    # get_related scoring is structurally id-only too: incoming_references yields
    # IncomingReference records and the eval reads only their ids.
    related_case = ev.QueryCase(
        id="t2",
        tool=ev.TOOL_GET_RELATED,
        query=REALTIME_SYNC,
        category="impact_analysis",
        relevant=(REQ_OFFLINE,),
    )
    related_ids = ev.returned_ids(str(CORPUS), entries, related_case)
    assert all(isinstance(rid, str) for rid in related_ids)
    assert REQ_OFFLINE in related_ids
