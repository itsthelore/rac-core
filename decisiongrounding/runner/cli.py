"""decisiongrounding runner.

    python -m runner.cli run     --arm context_dump --scenarios scenarios/
    python -m runner.cli compare --arms context_dump,naive_rag --scenarios scenarios/
    python -m runner.cli demo    --scenarios scenarios/

`demo` is the one-command spine: it runs the two real arms on the worked
scenarios offline, writes an append-only report, and emits the crossover chart.

Reproducibility: the answering model + seed are pinned and recorded in every
RunResult. `results/` is append-only — runs are written as new timestamped
files and never mutated.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Make the package root importable when run as `python -m runner.cli` or directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from providers import (  # noqa: E402
    ARMS,
    REAL_ARMS,
    ClaudeAnsweringModel,
    NaiveRagProvider,
    ScriptedAnsweringModel,
    make_embedder,
)
from providers.base import ProposedChange  # noqa: E402
from scenarios.loader import Scenario, load_scenarios  # noqa: E402
from scoring import aggregate, score  # noqa: E402
from scoring.crossover import build_dataset, emit  # noqa: E402

HARNESS_VERSION = "0.1.0-scaffold"
_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_RESULTS = _ROOT / "results"


def _answering_model(name: str, seed: int):
    if name == "offline-stub":
        return ScriptedAnsweringModel(seed=seed)
    if name == "claude":
        # Real, pinned answering model (Claude Opus 4.8). Requires the [real]
        # extra + ANTHROPIC_API_KEY; not runnable in the offline demo.
        return ClaudeAnsweringModel(seed=seed)
    raise SystemExit(
        f"unknown answering model {name!r}; use 'offline-stub' or 'claude'."
    )


def _provider(arm: str, model, embedder_spec: str):
    """Instantiate an arm, wiring a real embedder into naive_rag when asked."""
    if arm == "naive_rag":
        return NaiveRagProvider(model, embedder=make_embedder(embedder_spec))
    return ARMS[arm](model)


def _pc_to_dict(pc: ProposedChange) -> dict:
    return {
        "summary": pc.summary,
        "actions": [{"kind": a.kind, "target": a.target, "detail": a.detail} for a in pc.actions],
        "cites_decisions": list(pc.cites_decisions),
        "asserts_prohibition": pc.asserts_prohibition,
        "asserts_permission": pc.asserts_permission,
    }


def run_one(arm: str, scenario: Scenario, model, seed: int, embedder: str = "local-hash") -> dict:
    provider = _provider(arm, model, embedder)
    provider.prepare(list(scenario.corpus))
    pc = provider.respond(scenario.task)
    sc = score(scenario, pc)
    g = provider.grounding
    gov = scenario.gold_label.governing_decision
    governing_retrieved = None if gov is None else (gov in g.artifacts_supplied)
    return {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "arm": arm,
        "scenario_id": scenario.scenario_id,
        "corpus_size_N": len(scenario.corpus),
        "answering_model": {
            "name": model.name,
            "version": model.version,
            "temperature": model.temperature,
            "seed": seed,
        },
        "grounding": {
            "provider": arm,
            "token_estimate": g.token_estimate,
            "artifacts_supplied": list(g.artifacts_supplied),
        },
        "proposed_change": _pc_to_dict(pc),
        "score": sc.as_dict(),
        "retrieval": {"governing_decision_retrieved": governing_retrieved},
        "harness_version": HARNESS_VERSION,
    }


def _write_report(results: list[dict], out_dir: Path, label: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"run-{stamp}-{label}.json"
    if path.exists():  # append-only: never overwrite an existing run file
        path = out_dir / f"run-{stamp}-{label}-{uuid.uuid4().hex[:6]}.json"
    by_arm: dict[str, list] = {}
    for r in results:
        by_arm.setdefault(r["arm"], []).append(r)
    from scoring.scorer import Score

    metrics = {
        arm: aggregate(
            arm,
            [Score(**r["score"]) for r in rs],
            [r["retrieval"]["governing_decision_retrieved"] for r in rs],
        ).as_dict()
        for arm, rs in by_arm.items()
    }
    report = {
        "harness_version": HARNESS_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "metrics_by_arm": metrics,
        "runs": results,
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _print_metrics(results: list[dict]) -> None:
    by_arm: dict[str, list] = {}
    for r in results:
        by_arm.setdefault(r["arm"], []).append(r)
    from scoring.scorer import Score

    print(f"{'arm':<16}{'adhere':>8}{'stale':>8}{'f-permit':>10}{'f-prohibit':>12}{'gov-recall':>12}")
    for arm, rs in by_arm.items():
        m = aggregate(
            arm,
            [Score(**r["score"]) for r in rs],
            [r["retrieval"]["governing_decision_retrieved"] for r in rs],
        )
        recall = "  n/a" if m.governing_recall_rate is None else f"{m.governing_recall_rate:.2f}"
        print(
            f"{arm:<16}{m.adherence_rate:>8.2f}{m.stale_decision_rate:>8.2f}"
            f"{m.false_permit_rate:>10.2f}{m.false_prohibit_rate:>12.2f}{recall:>12}"
        )


def cmd_run(args) -> int:
    scenarios = load_scenarios(args.scenarios)
    model = _answering_model(args.answering, args.seed)
    results = [run_one(args.arm, sc, model, args.seed, args.embedder) for sc in scenarios]
    _print_metrics(results)
    path = _write_report(results, Path(args.out), args.arm)
    print(f"\nwrote {path}")
    return 0


def cmd_compare(args) -> int:
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    scenarios = load_scenarios(args.scenarios)
    model = _answering_model(args.answering, args.seed)
    results: list[dict] = []
    for arm in arms:
        for sc in scenarios:
            results.append(run_one(arm, sc, model, args.seed, args.embedder))
    _print_metrics(results)
    path = _write_report(results, Path(args.out), "compare-" + "-".join(arms))
    print(f"\nwrote {path}")
    return 0


def cmd_demo(args) -> int:
    arms = REAL_ARMS
    scenarios = load_scenarios(args.scenarios)
    model = _answering_model("offline-stub", args.seed)
    print("== per-scenario, per-arm (tiny corpus) ==")
    results: list[dict] = []
    for arm in arms:
        for sc in scenarios:
            results.append(run_one(arm, sc, model, args.seed, args.embedder))
    _print_metrics(results)
    report = _write_report(results, Path(args.out), "demo")

    print("\n== adherence vs corpus size (discriminating scenarios, averaged) ==")
    dataset = build_dataset(scenarios, arms=arms, seed=args.seed)
    for arm in arms:
        row = " ".join(f"N={p['N']}:{p['adherence_rate']:.2f}" for p in dataset["arms"][arm])
        print(f"{arm:<16}{row}")
    print("\n== governing-decision recall vs corpus size (why adherence moves) ==")
    for arm in arms:
        row = " ".join(
            f"N={p['N']}:{'n/a' if p['governing_recall'] is None else format(p['governing_recall'], '.2f')}"
            for p in dataset["arms"][arm]
        )
        print(f"{arm:<16}{row}")

    print("\n== per-scenario adherence (where the average comes from) ==")
    for arm in arms:
        for sid, series in dataset["per_scenario"][arm].items():
            row = " ".join(f"N={p['N']}:{'1' if p['adherent'] else '0'}" for p in series)
            print(f"{arm:<13}{sid:<32}{row}")
    data_path, chart_path = emit(dataset, Path(args.out))
    print(f"\nwrote {report}\nwrote {data_path}\nwrote {chart_path}")
    print(
        "\nNOTE: offline-stub output is a harness illustration, NOT a benchmark "
        "result. See README and ADR-0001."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="decisiongrounding", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    common = dict()
    for name in ("run", "compare", "demo"):
        sp = sub.add_parser(name)
        sp.add_argument("--scenarios", default=str(_ROOT / "scenarios"))
        sp.add_argument("--out", default=str(_DEFAULT_RESULTS))
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument(
            "--answering", default="offline-stub", choices=["offline-stub", "claude"]
        )
        sp.add_argument(
            "--embedder",
            default="local-hash",
            help="naive_rag embedder: local-hash (offline) | voyage[:model] | st[:model]",
        )
        if name == "run":
            sp.add_argument("--arm", required=True, choices=sorted(ARMS))
        if name == "compare":
            sp.add_argument("--arms", default=",".join(REAL_ARMS))

    args = p.parse_args(argv)
    return {"run": cmd_run, "compare": cmd_compare, "demo": cmd_demo}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
