"""Headline artifact: the adherence-vs-corpus-size crossover curve.

We sweep corpus size N (default {10, 50, 150, 300}) with rising conflict
density and plot per-arm decision-adherence. The corpus is grown with
deterministic, clearly-labelled *filler* artifacts typed as `note` (not
`decision`): they are retrieval distractors, not binding decisions. This models
the mechanism under test — `naive_rag` is typing-blind, so as the corpus grows
its top-k fills with notes and the binding decision falls out; `context_dump`
supplies everything and the decision-reading agent ignores non-decisions, so it
holds. (A typed `rac` arm, once built, should hold for the same reason.)

The full N=300 corpus is illustrative synthetic padding, not a real corpus.
Real curves require real/public-derived corpora — see CONTRIBUTING.md.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from providers import ARMS, ScriptedAnsweringModel
from providers.base import CorpusArtifact
from scenarios.loader import Scenario
from scoring.scorer import score

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "to", "of", "and", "or", "for", "in", "on", "with", "is", "are"}
DEFAULT_NS = (10, 50, 150, 300)
DISCRIMINATING = {"superseded_decision", "prohibition_at_point_of_action", "conflicting_scoped"}


def _domain_tokens(scenario: Scenario) -> list[str]:
    text = f"{scenario.task.prompt} {scenario.task.proposed_action}".lower()
    toks = [t for t in _TOKEN.findall(text) if t not in _STOP and len(t) > 2]
    return sorted(set(toks))


def make_filler_notes(
    count: int, scenario: Scenario, seed: int, density: float
) -> list[CorpusArtifact]:
    """Deterministic distractor `note` artifacts (never typed as decisions).

    `density` (0..1) rises with N. A `density` fraction of the notes are *strong
    distractors* that closely echo the task — exactly the chatter a typing-blind
    retriever cannot distinguish from a binding decision; the rest are weak,
    low-similarity notes. As N (and density) grow, strong distractors crowd
    `naive_rag`'s fixed top-k and the binding decision falls out. The
    decision-reading agent ignores all notes, so `context_dump` is unaffected —
    the divergence is entirely a retrieval/typing effect.
    """
    pool = _domain_tokens(scenario)
    rng = random.Random(f"{seed}:{scenario.scenario_id}:{count}")
    action = scenario.task.proposed_action
    n_strong = int(round(count * density))
    notes: list[CorpusArtifact] = []
    for i in range(count):
        if i < n_strong:
            body = (
                f"# Note {i:04d}\n\nSlack thread: someone mentioned wanting to "
                f"{action}. Informal chatter — this is not a decision and binds "
                f"nothing.\n"
            )
        else:
            k = min(len(pool), rng.randint(1, max(1, len(pool) // 3))) if pool else 0
            sample = rng.sample(pool, k) if pool else []
            body = (
                f"# Note {i:04d}\n\nMiscellaneous notes on {' '.join(sample)}. "
                f"Not a decision.\n"
            )
        notes.append(
            CorpusArtifact(
                id=f"NOTE-{i:04d}",
                type="note",
                path="(synthetic-filler)",
                text=body,
                filler=True,
            )
        )
    return notes


def _run_arm_on_corpus(arm_name: str, corpus, scenario, seed: int):
    provider = ARMS[arm_name](ScriptedAnsweringModel(seed=seed))
    provider.prepare(list(corpus))
    pc = provider.respond(scenario.task)
    return score(scenario, pc), provider.grounding


def build_dataset(
    scenarios: list[Scenario],
    arms: tuple[str, ...] = ("context_dump", "naive_rag"),
    ns: tuple[int, ...] = DEFAULT_NS,
    seed: int = 0,
) -> dict:
    """Compute per-arm adherence at each N, averaged over discriminating scenarios."""
    discriminating = [s for s in scenarios if s.scenario_type in DISCRIMINATING]
    points: dict[str, list[dict]] = {arm: [] for arm in arms}
    # per_scenario[arm][scenario_id] -> [{N, adherent, stale}]
    per_scenario: dict[str, dict[str, list[dict]]] = {
        arm: {s.scenario_id: [] for s in discriminating} for arm in arms
    }
    n_max = max(ns)
    for n in ns:
        density = (n - min(ns)) / (n_max - min(ns)) if n_max != min(ns) else 0.0
        for arm in arms:
            adhered = 0
            for sc in discriminating:
                filler = make_filler_notes(max(0, n - len(sc.corpus)), sc, seed, density)
                corpus = list(sc.corpus) + filler
                sc_score, _ = _run_arm_on_corpus(arm, corpus, sc, seed)
                adhered += 1 if sc_score.adherent else 0
                per_scenario[arm][sc.scenario_id].append(
                    {
                        "N": n,
                        "adherent": sc_score.adherent,
                        "stale_decision_followed": sc_score.stale_decision_followed,
                    }
                )
            rate = adhered / len(discriminating) if discriminating else 0.0
            points[arm].append({"N": n, "adherence_rate": rate})
    return {
        "metric": "decision_adherence_rate",
        "scenarios_included": [s.scenario_id for s in discriminating],
        "note": "Filler is synthetic untyped `note` padding. Illustrative, not a real corpus.",
        "seed": seed,
        "ns": list(ns),
        "arms": {arm: points[arm] for arm in arms},
        "per_scenario": per_scenario,
    }


def render_chart(dataset: dict, out_path: str | Path) -> Path:
    """Render ONE crossover chart. matplotlib if present, else pure-Python SVG."""
    out_path = Path(out_path)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4.5))
        for arm, pts in dataset["arms"].items():
            ax.plot([p["N"] for p in pts], [p["adherence_rate"] for p in pts], marker="o", label=arm)
        ax.set_xscale("log")
        ax.set_xlabel("Corpus size N (log scale)")
        ax.set_ylabel("Decision-adherence rate")
        ax.set_ylim(-0.05, 1.05)
        ax.set_title("Decision adherence vs corpus size (illustrative scaffold)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        png = out_path.with_suffix(".png")
        fig.tight_layout()
        fig.savefig(png, dpi=120)
        plt.close(fig)
        return png
    except Exception:
        svg = out_path.with_suffix(".svg")
        svg.write_text(_render_svg(dataset), encoding="utf-8")
        return svg


def _render_svg(dataset: dict) -> str:
    import math

    W, H, pad = 720, 460, 60
    ns = dataset["ns"]
    xs = [math.log10(n) for n in ns]
    xmin, xmax = min(xs), max(xs)

    def px(x):
        return pad + (x - xmin) / (xmax - xmin or 1) * (W - 2 * pad)

    def py(y):
        return H - pad - y * (H - 2 * pad)

    colors = {"context_dump": "#1f77b4", "naive_rag": "#d62728", "rac": "#2ca02c"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{W/2}" y="28" text-anchor="middle" font-size="16">Decision adherence vs corpus size (illustrative scaffold)</text>',
        f'<line x1="{pad}" y1="{py(0)}" x2="{W-pad}" y2="{py(0)}" stroke="#333"/>',
        f'<line x1="{pad}" y1="{py(0)}" x2="{pad}" y2="{py(1)}" stroke="#333"/>',
        f'<text x="{pad-8}" y="{py(1)}" text-anchor="end" font-size="11">1.0</text>',
        f'<text x="{pad-8}" y="{py(0)}" text-anchor="end" font-size="11">0.0</text>',
        f'<text x="{W/2}" y="{H-15}" text-anchor="middle" font-size="12">Corpus size N (log scale)</text>',
    ]
    for n, x in zip(ns, xs):
        parts.append(f'<text x="{px(x)}" y="{py(0)+18}" text-anchor="middle" font-size="11">{n}</text>')
    legend_y = 44
    for arm, pts in dataset["arms"].items():
        color = colors.get(arm, "#555")
        poly = " ".join(f"{px(math.log10(p['N']))},{py(p['adherence_rate'])}" for p in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for p in pts:
            parts.append(f'<circle cx="{px(math.log10(p["N"]))}" cy="{py(p["adherence_rate"])}" r="3.5" fill="{color}"/>')
        parts.append(f'<text x="{W-pad-120}" y="{legend_y}" font-size="12" fill="{color}">{arm}</text>')
        legend_y += 16
    parts.append("</svg>")
    return "\n".join(parts)


def emit(dataset: dict, out_dir: str | Path) -> tuple[Path, Path]:
    """Write the dataset JSON and the chart; return both paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data_path = out_dir / "crossover_dataset.json"
    data_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    chart_path = render_chart(dataset, out_dir / "crossover")
    return data_path, chart_path
