---
schema_version: 1
id: RAC-KV6KFDACQYYH
type: design
tags: [eval, scorecard, ci, gate, determinism]
---
# Grounding Eval Scorecard and CI Gate

## Context

WS1 of the v0.23.0 hardening release adds a deterministic grounding benchmark
(`rac eval`). The non-trivial structure worth recording here is the *scorecard*
— the machine-readable artifact every run writes — and the *gate* semantics that
compare it against a committed baseline. The scoring rules are fixed by ADR-066
(deterministic, no embeddings, no LLM judge); this design pins the data shapes
and the gate's pass/fail logic so they can be implemented and tested without
re-litigation.

## User Need

The maintainer and CI need to answer two questions deterministically and
offline: "is retrieval still returning the right decisions?" and "did this
change make retrieval worse?" They need a human-readable summary to read at a
glance and a machine-readable scorecard CI can diff against a baseline — with
timestamps and hashes excluded from the comparison so a clock never fails a
build.

## Design

### Metrics (computed per case, then macro-aggregated)

For each query case, obtain a deterministic ranked result list `R_q` from the
target tool (`search_artifacts` or `get_related`). Tie-break: equal scores order
by ascending artifact id (ADR-066). Let `Rel` be the declared `relevant` set and
`top_k` the first `k` of `R_q`:

- `P@k = |Rel ∩ top_k| / k` — empty/missing slots count against precision.
- `R@k = |Rel ∩ top_k| / |Rel|` — `|Rel| ≥ 1` by construction.
- Hard-negative violation: the case violates iff `must_not_return ∩ top_k ≠ ∅`.

Aggregate as macro-averages (equal weight per case) at `k ∈ {1, 3, 5}` for both
P and R, reported `overall`, `by_category`, and `by_tool`. Macro is the gated
statistic. `negative_violations` is the summed violation count.

### Scorecard shape (written every run; baseline at `tests/eval/baseline.json`)

Three top-level objects. Only `metrics` is compared by the gate; `metadata` and
`per_query` are diagnostic and excluded from comparison.

```json
{
  "metrics": {
    "overall": {"p_at_1": 0.0, "p_at_3": 0.0, "p_at_5": 0.0,
                "r_at_1": 0.0, "r_at_3": 0.0, "r_at_5": 0.0,
                "negative_violations": 0},
    "by_category": {"constraint_check": {"p_at_1": 0.0, "r_at_5": 0.0}},
    "by_tool": {"search_artifacts": {"p_at_1": 0.0, "r_at_5": 0.0},
                "get_related": {"p_at_1": 0.0, "r_at_5": 0.0}}
  },
  "metadata": {"lore_version": "", "corpus_hash": "sha256:…",
               "query_set_hash": "sha256:…", "n_queries": 0, "generated_at": ""},
  "per_query": [{"id": "Q001", "returned": ["…"], "p_at_5": 0.0,
                 "r_at_5": 0.0, "violations": []}]
}
```

### Gate semantics (`rac eval --check`)

Floors live in committed config (initial: `negative_violations == 0` always,
`overall.p_at_1 ≥ 0.90`, `overall.r_at_5 ≥ 0.95`; tolerance `T = 0.02`). The
gate FAILS if any of: (a) `negative_violations > 0`; (b) any gated metric
`< floor`; (c) any gated metric `< baseline_value − T`. On failure it prints
which rule fired plus the metric name, baseline value, and current value.
Baselines are updated only by `rac eval --update-baseline`; CI never rebaselines.

## Constraints

- Deterministic and offline (ADR-066): no randomness, clock, or network in the
  scored path; the `metrics` object is byte-identical across runs on an
  unchanged corpus.
- Scoring calls the same retrieval code the MCP tools call, so the benchmark
  guards the real surface.
- The scorecard JSON is an additive, stable contract (ADR-007).
- Reuse the WS8 content-hash short-circuit so re-runs skip unchanged artifacts.

## Rationale

Separating `metrics` (gated) from `metadata`/`per_query` (diagnostic) is what
lets the scorecard be both byte-stable for the gate and richly informative for a
human, without a timestamp ever breaking CI. Macro-averaging weights every case
equally, so a single category cannot be drowned out by case count.

## Alternatives

- Micro-averaging (weight by case count): rejected — lets large categories mask
  regressions in small but important ones (e.g. supersession).
- A single overall score with no per-category/per-tool breakdown: rejected —
  hides *where* retrieval regressed, which is the actionable signal.
- Token-based or similarity-based scoring: rejected by ADR-066.

## Accessibility

The human-readable summary prints plain-text tables (overall, by-category,
by-tool) and lists every violating case with its returned ids, so the result is
legible in a terminal and in CI logs without color or graphics.

## Style Guidance

Human summary: one overall table, then by-category and by-tool tables, then an
explicit "Violations" section. Failure output names the rule, metric, baseline,
and current value on one line each. JSON output follows the shape above exactly.

## Open Questions

- Initial floors are a starting point; calibrate from the first green run and
  record any change with the baseline commit.
- Whether `get_related` cases should weight relationship-type categories
  differently is deferred until the query set grows from real usage.

## Related Decisions

- adr-066
- adr-007
- adr-037

## Related Requirements

- rac-grounding-eval-benchmark

## Related Roadmaps

- v0.23.0-hardening
