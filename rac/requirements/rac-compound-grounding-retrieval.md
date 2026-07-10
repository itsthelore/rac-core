---
schema_version: 1
id: RAC-KX6WEXWV5RJ8
type: requirement
tags: [user-facing, retrieval, grounding, mcp, cli, benchmark]
---
# Requirement: Compound Grounding Retrieval

## Status

Proposed

Classification: `[user-facing]` — the single-call grounding surface agents
and the SWE-DecisionBench harness consume. Scoped by the
`grounding-retrieval-surface` roadmap; decided by ADR-113; shapes pinned by
the `grounding-retrieval-surface` design.

## Problem

A consumer that wants "the best grounding RAC can offer for this task" must
hand-compose search, scope lookup, supersedes handling, ranking, and
budgeting across multiple primitive calls. Agents pay extra round-trips and
risk surfacing superseded decisions; the SWE-DecisionBench `rac` arm ends up
measuring the arm author's composition rather than RAC's judgement. RAC has
a retrieval opinion — it should own it, expose it in one deterministic
call, and make that call reachable identically from the MCP and the CLI.

## Requirements

- [REQ-001] RAC MUST provide a compound retrieval operation `retrieve_grounding(task, scope="", top_k=5, budget=0, live_only=True)` as an MCP tool (empty-string/zero sentinels mean "unset" — the `find_decisions` `topic=""` precedent, keeping the token-budgeted schema free of nullable `anyOf` shapes) and `rac retrieve "<task>" [directory] [--scope <path>] [--top-k K] [--budget N] [--live | --all] [--json]` as a CLI subcommand, both thin faces over one shared core service function (ADR-031).
- [REQ-002] The compound result MUST be a pure deterministic function of `(corpus bytes, request arguments)`: no model, embeddings, network, clock, or randomness in the pass (ADR-002, ADR-066, ADR-097). Repeated calls on an unchanged corpus MUST return byte-identical JSON.
- [REQ-003] For the same `(corpus, arguments)`, the CLI `--json` output and the MCP tool's JSON payload MUST be byte-identical, asserted by a parity test, so a harness driving the CLI measures exactly the MCP surface.
- [REQ-004] The compound pass MUST compose the existing seams and no parallel implementations: ADR-037/038/109 matching for keyword discovery, the `decisions-for` scope semantics for path binding (scope hits bind regardless of keyword match), the spec-driven `retired_status` liveness predicate, resolution along the validated acyclic `supersedes` graph to live successors, the ADR-078 BM25F+RRF ranking, and the ADR-033 budget mechanism for capping.
- [REQ-005] Every returned item MUST carry provenance sufficient for a deterministic governing-recall scorer: `channels` (`keyword`/`scope`/`supersedes`), `matching_entry` for scope-bound items, `superseded` ids when a live successor replaced a retired match, and the existing explain-hit `evidence` object for keyword items — matching the design's response shape exactly.
- [REQ-006] With `live_only=True` (the default) a retired artifact MUST NOT appear in `items`; when a retired artifact is matched and has a live successor along an inbound `supersedes` edge, the successor MUST appear with the substitution recorded in provenance.
- [REQ-007] The `budget` argument MUST be denominated in characters of serialized JSON and enforced by the existing ADR-033 mechanism (whole-item then content-tail truncation with `truncated`/`omitted` markers). On the MCP face the effective budget is `min(server_budget, budget)` — a per-call value lowers, never raises, the server-wide budget.
- [REQ-008] `search_artifacts` MUST gain an additive `live_only: bool = False` argument and `rac find` a `--live` flag, dropping retired artifacts (the spec-driven retired-status predicate, every artifact type) from the matched set before ranking; `get_artifact` MUST gain an additive per-call `budget: int = 0` argument (`0` = server budget) with REQ-007 semantics. Calls without the new arguments MUST return byte-identical responses to today (ADR-007), and existing `find_decisions` behaviour MUST be unchanged.
- [REQ-009] An empty `items` list MUST be a valid success: exit code 0 on the CLI, a structured non-error payload on the MCP face. Usage errors (unreadable directory, invalid arguments) exit 2 on the CLI and return structured error data on the MCP face, never exceptions.
- [REQ-010] The extended pinned tool surface (six tools) MUST stay within the standing surface token budget's hard cap (ADR-030), asserted by the existing surface-budget test, and the compound tool MUST join the ADR-097 per-tool benchmark family.
- [REQ-011] The grounding eval (`rac eval --check`) MUST remain green: the compound operation and facets change no existing production retrieval ordering, and the scorecard `metrics` object is unaffected by the additive fields (ADR-007).

## Acceptance Criteria

- One CLI call per benchmark cell returns ranked, budget-capped grounding
  with provenance; a parity test proves CLI/MCP byte-identity (REQ-003).
- A fixture with a supersession chain proves REQ-006: the retired decision
  never appears live-only; its successor appears carrying `superseded`
  provenance.
- A scope fixture proves scope-bound decisions are returned and ranked
  ahead of keyword-only hits even when the task string shares no tokens
  with the decision.
- Budget tests prove the response never exceeds the requested character
  budget and that markers appear exactly when truncation occurred.
- Determinism test: two runs on an unchanged corpus produce byte-identical
  JSON on both faces.
- Negative boundary tests: absent new arguments, `search_artifacts`,
  `get_artifact`, and `rac find` outputs are byte-identical to the
  pre-change fixtures; `rac eval --check` exits 0.

## Success Metrics

- The SWE-DecisionBench `rac` arm is implemented as one `rac retrieve` call
  per cell with no hand composition, and its governing-recall scoring keys
  only on the response's provenance fields.
- Agents over MCP obtain task grounding in one round-trip within a declared
  character budget.

## Risks

- Stratified ranking (scope ahead of keyword) could surprise consumers
  expecting pure lexical order. Mitigation: provenance makes the stratum
  visible; the design pins the rule.
- The response shape becomes load-bearing for an external study; later
  changes are contract changes. Mitigation: additive-only evolution
  (ADR-007) and `schema_version` on the payload.
- Generalised liveness depends on every type spec's `retired_status` being
  accurate. Mitigation: the predicate reuses the same source relationship
  validation already exercises.

## Assumptions

- The existing BM25F+RRF ordering is the ranking opinion to expose; no new
  ranker is introduced (ADR-078).
- Character budgets are an acceptable fairness unit for the study; a token
  view is derivable downstream (ADR-033).
- The MCP server's read-model and fresh-walk paths both serve the compound
  operation, as they do the existing tools (ADR-032, ADR-104).

## Descope

Out of scope for this requirement: a `sections` selector on
`get_artifact`; caller-tunable composition (channel weights, strata
toggles); scope channels for non-decision types; any change to production
lexical ranking; any embedding, vector, or LLM-assisted arm (those live in
the external benchmark repo per `rac-grounding-baseline-study`).

## Related Decisions

- adr-113
- adr-007
- adr-030
- adr-031
- adr-033
- adr-034
- adr-066
- adr-067
- adr-078
- adr-097
- adr-109

## Related Requirements

- rac-grounding-baseline-study
- rac-grounding-eval-benchmark
- rac-selective-retrieval-default
- rac-explainable-retrieval

## Related Roadmaps

- grounding-retrieval-surface
