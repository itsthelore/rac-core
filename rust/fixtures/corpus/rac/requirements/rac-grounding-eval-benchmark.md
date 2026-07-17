---
schema_version: 1
id: RAC-KV6KFF98VDBX
type: requirement
tags: [user-facing, eval, retrieval, benchmark, ci]
---
# Requirement: Grounding Retrieval Benchmark

## Status

Accepted

Classification: `[user-facing]` — it is the proof the tool works. Scoped to the
v0.23.0 hardening release (WS1).

## Problem

Lore's core claim is that an agent retrieves the right recorded decision at the
right moment. Today that claim rests on unit tests of individual behaviors and
on demo anecdote; nothing measures aggregate retrieval quality or guards against
silent regressions. The failure that matters most — surfacing a superseded
decision as if it were current — is exactly what Lore exists to prevent, yet
there is no gate that fails the build when it happens.

## Requirements

- [REQ-001] RAC MUST provide a `rac eval` CLI subcommand (argparse subcommand, `cmd_eval` + `set_defaults(func=...)`, same shape as `rac find`) that scores the retrieval tools against a versioned fixture corpus and query set rooted at `tests/eval/` and runs without arguments against that in-repo fixture by default.
- [REQ-002] Eval scoring MUST be deterministic and offline: a pure function of `(corpus, query set, retrieval code)`, with no network, no API keys, no randomness, no clock in the scored path, and no embeddings or LLM judge (ADR-066). The scored path MUST call the same `search_index` / relationship-resolution functions the MCP `search_artifacts` / `get_related` tools call (`src/rac/services/resolve.py`, `src/rac/mcp/server.py`), so the benchmark guards the real surface, never a parallel scorer.
- [REQ-003] `rac eval` MUST compute Precision@k and Recall@k at `k ∈ {1, 3, 5}` as macro-averages (equal weight per case), reported `overall`, `by_category`, and `by_tool`, and MUST count hard-negative violations (a `must_not_return` id appearing in the top-k returned ids). `P@k = |Rel ∩ top_k| / k` (empty slots count against precision); `R@k = |Rel ∩ top_k| / |Rel|` with `|Rel| ≥ 1` by construction. Each query case is scored against exactly one named tool (`search_artifacts` or `get_related`).
- [REQ-004] The scored ranked list MUST be the production retrieval order unchanged. `search_index` already orders by `(match_rank, path)`, which is total and byte-stable; `rac eval` MUST consume that order verbatim and MUST NOT re-sort, re-rank, or alter production retrieval. The ADR-066 ascending-artifact-id tie-break is satisfied as recorded only if production order is path-stable; because it already is, this release adds NO production sort change. (If a future equal-`(rank, path)` collision is possible, it is resolved by ascending artifact id at the eval read seam only.)
- [REQ-005] `rac eval` MUST write a scorecard JSON with exactly three top-level objects — `metrics`, `metadata`, `per_query` — matching the `grounding-eval-scorecard` design shape. `metadata` MUST record `lore_version`, `corpus_hash` (`sha256:…` over the fixture corpus files), `query_set_hash` (`sha256:…` over the query set), `n_queries`, and `generated_at`. ONLY `metrics` is compared by the gate; `metadata` and `per_query` are diagnostic and excluded from comparison so a clock or hash never fails a build. Scorecard JSON is an additive, stable contract (ADR-007).
- [REQ-006] RAC MUST provide a `rac eval --check` CI gate that re-runs scoring and FAILS (exit 1) if any of: (a) `negative_violations > 0`; (b) any gated metric `< floor`; (c) any gated metric `< baseline_value − tolerance`. It MUST print one line per fired rule naming the rule, metric, baseline value, and current value. A clean run exits 0; a usage error (missing baseline, unreadable corpus, malformed query set) exits 2. Floors and tolerance live in committed config alongside the baseline (initial: `negative_violations == 0` always, `overall.p_at_1 ≥ 0.90`, `overall.r_at_5 ≥ 0.95`, tolerance `T = 0.02`; plus a per-category floor on each query category's `p_at_1` and `r_at_5`, calibrated from the first green run and committed alongside the overall floors). Gated metrics are `overall.p_at_1`, `overall.r_at_5`, `negative_violations`, and each query category's `p_at_1` / `r_at_5` floor; per-tool figures remain diagnostic this release.
- [REQ-007] Re-baselining MUST be human-gated via `rac eval --update-baseline`, which overwrites `tests/eval/baseline.json` with the current `metrics` object; CI MUST NEVER pass `--update-baseline` and MUST NEVER write the baseline.
- [REQ-008] The fixture corpus MUST live under `tests/eval/corpus/`, be schema-valid (`rac validate` exit 0), pass `rac doctor` (WS3) clean, span all five artifact types, and include a supersession chain (the superseded member is the canonical `must_not_return` case), distractors, and an ambiguous pair. The query set MUST live under `tests/eval/queries.json` (or equivalent committed file), each case declaring `id`, `tool`, `query`/`id` input, `category`, `relevant` (≥1 id), and optional `must_not_return`.
- [REQ-009] The eval SHOULD reuse the WS8 content-hash short-circuit to skip unchanged artifacts on re-runs, but MUST NOT depend on it: WS8 is a cuttable Tier-2 workstream, so `rac eval` MUST be correct and deterministic without it, with the short-circuit a pure performance optimization that never changes scored output.
- [REQ-010] The scorecard `metrics` comparison MUST be insensitive to additive WS2 `evidence`/snippet fields on retrieval output (ADR-007): the gate compares only returned-id membership in top-k, so explainability fields added to `search_artifacts` / `get_related` results MUST NOT shift any metric.

## Acceptance Criteria

- `rac eval` runs offline with no network or keys against `tests/eval/`; the
  `metrics` object is byte-identical across repeated runs on an unchanged corpus
  (asserted by a byte-equality test on the serialized `metrics` block).
- `rac eval --check` exits 0 on the committed baseline, exits 1 on any gate
  failure, and exits 2 on usage errors (missing/unreadable baseline, corpus, or
  query set).
- Three regression-injection tests prove the gate is real: (1) the clean fixture
  corpus passes; (2) a deterministically removed relevant artifact drops
  `overall.r_at_5` and fails `rac eval --check` with exit 1; (3) a query forced
  to surface a `must_not_return` id in top-k fails on `negative_violations > 0`
  with exit 1. Each test asserts both the exit code and the named fired rule.
- The human-readable summary prints an overall table, then by-category and
  by-tool tables, then an explicit "Violations" section listing every violating
  case with its returned ids; `--json` prints the scorecard shape exactly.
- The gate is wired into CI (per ADR-027 per-service batteries) and fails the
  build on regression; CI never runs `--update-baseline`.

## Success Metrics

- The committed baseline meets the initial floors (`negative_violations == 0`,
  `overall.p_at_1 ≥ 0.90`, `overall.r_at_5 ≥ 0.95`, plus the per-category
  `p_at_1` / `r_at_5` floors), calibrated from the first green run and committed
  with the baseline.
- A deliberately introduced retrieval regression is caught by CI rather than by
  a human noticing later.

## Risks

- Floors mis-calibrated before the first green run. Mitigation: calibrate from
  the first run, commit the baseline, gate on `baseline − tolerance` thereafter;
  CI never rebaselines (REQ-007).
- A fixture corpus that drifts from real retrieval. Mitigation: source cases
  from real or partner-representative repos and grow from design-partner usage.
- Scope creep into a production retrieval-ranking change. Mitigation: REQ-004
  fixes the eval to the existing `(rank, path)` order; no production sort changes
  this release.

## Descope

This requirement is one workstream (WS1) inside the single v0.23.0 release and
does not split into further versions. Explicitly out of scope this release:
graded relevance, micro-averaging, per-tool gating (diagnostic only;
per-category floors ARE gated per REQ-006), any change to production retrieval
ranking, and any dependence on WS8 for correctness (REQ-009 makes the
content-hash short-circuit optional).

## Assumptions

- The existing deterministic retrieval surfaces (`search_artifacts`,
  `get_related`, via `search_index` and relationship resolution) are the right
  thing to benchmark and guard, and their current `(rank, path)` ordering is
  byte-stable enough to score without modification.
- WS3 `rac doctor` is available for the REQ-008 corpus-health check; if WS3 is
  not yet landed when WS1 is built, the corpus health check falls back to
  `rac validate` and the `doctor` clean-run assertion is added once WS3 lands.
- WS2 explainability fields on retrieval output are additive (ADR-007) and do
  not perturb the id-membership metrics the gate compares (REQ-010).

## Related Decisions

- adr-066
- adr-002
- adr-037
- adr-038
- adr-007

## Related Requirements

- rac-idempotent-content-hash-processing
- rac-single-schema-agreement

## Related Roadmaps

- v0.23.0-hardening
