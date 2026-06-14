# Scoring Rubric (FROZEN — pre-registration)

Frozen before results exist. Scoring is **deterministic and structural first**.
An LLM judge is reserved as a disclosed fallback and is **not built this pass**.

## What is scored

Each arm produces a `ProposedChange` (summary, structured actions, cited
decisions, and two booleans: `asserts_prohibition` / `asserts_permission`). The
scorer inspects that structure against the scenario's gold label. See
`../scoring/scorer.py`.

## Deterministic verdicts

Per scenario type:

- **prohibition_at_point_of_action** — adherent iff the agent refrains
  (`asserts_prohibition`, not `asserts_permission`) **and** cites the governing
  decision. Proposing the action is a **false_permit**.
- **superseded_decision** — adherent iff the agent follows the superseding
  decision. Relying on a superseded decision (cited, with its successor not
  followed) is **stale_decision_followed**, and is never adherent.
- **negative_control** — adherent iff the agent does **not** assert a
  prohibition. Inventing one is a **false_prohibit**.
- **simple_adherence / other permitted** — adherent iff the agent proceeds
  (`asserts_permission`, not `asserts_prohibition`) and satisfies the stated
  `required_actions` constraint(s).

## Metrics

- **Headline: decision-adherence rate.** Fraction of scenarios scored adherent.
- **Headline artifact:** the adherence-vs-corpus-size crossover curve over
  N ∈ {10, 50, 150, 300}.
- Also reported: **stale-decision rate**, **false-permit rate**,
  **false-prohibit rate**, **per-arm run-to-run variance** (an arm that is
  correct-but-unstable is reported as such, not smoothed), and
  **governing-decision recall** — whether the arm's grounding actually contained
  the binding decision. Recall is a *diagnostic*, not the headline: it explains
  why adherence rises or falls (the analog of MemoryBench's Hit@K) and is `null`
  for negative controls, where no decision governs.
- **No composite.** There is deliberately no MemScore-style single number. The
  headline stays a legible rate.

## LLM-judge fallback (DISCLOSED, NOT BUILT THIS PASS)

Some genuinely open-ended proposals cannot be scored structurally. For those —
and only those — a future version may use a single, fixed, **disclosed** judge
model, with:

- the judge model id and version pinned and published;
- a **human spot-check hook**: a sampled fraction of judge verdicts reviewed by
  a human, with disagreement rate reported alongside results;
- the judge's share of total scoring reported, so readers know how much of the
  headline rests on deterministic vs. judged scoring.

The judge is a fallback, never the spine. It is intentionally out of scope here.

## Reproducibility

Every run records the pinned answering model, version, temperature, and seed in
its `RunResult`. Runs reproduce from seed + pinned model versions. `results/` is
append-only.
