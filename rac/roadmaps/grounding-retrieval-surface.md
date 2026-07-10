---
schema_version: 1
id: RAC-KX6WEQ4KMNBQ
type: roadmap
---
# RAC — Grounding Retrieval Surface

## Status

Planned

Motivated by the SWE-DecisionBench publication study
(`rac-grounding-baseline-study`): the study's `rac` arm must consume RAC as
RAC's *own* retrieval opinion — one non-agentic, deterministic call,
symmetric with the `naive_rag` arm's single top-k — but today the arm author
must hand-compose primitives, so the benchmark measures the author's
composition, not the engine's judgement. Not folded into the
`v0.22.x-housekeeping` series (topology-only); scoped as its own
codename-identified initiative per ADR-094. Execution is tracked in GitHub
(ADR-093).

## Context

An external consumer that wants "the best grounding RAC can offer for this
task" cannot get it in one call today. The gaps, after correcting for what
already shipped:

- **Scope lookup is already on the MCP.** `find_decisions(topic, path)`
  (ADR-067) reaches the same core as CLI `decisions-for`, so the
  path-governed bindings lookup — the discovery channel immune to corpus
  size — is reachable. It is, however, a *separate* call an author must
  know to make and merge with search results.
- **`search_artifacts` already has a `tags` facet** (ADR-109). What it lacks
  is a `live_only` facet: liveness is modelled only for decisions
  (`is_live_decision`), and no general retired-status filter exists on the
  search surface for any artifact type, even though the retired-status
  predicate is already spec-driven in relationship validation.
- **`get_artifact` has no per-call budget.** The ADR-033 response budget is
  a single server-wide character budget fixed at server construction; a
  consumer that wants a lean grounding excerpt cannot ask for one, and a
  whole artifact can dominate a context window.
- **No compound retrieval operation exists.** Nothing composes keyword
  discovery, scope binding, supersedes resolution, ranking, and budget
  capping into a single deterministic answer with provenance. If RAC has an
  opinion about "best grounding for this task", RAC should own it and expose
  it; the benchmark then measures RAC's judgement.

## Outcomes

- A single deterministic call — `retrieve_grounding` on the MCP,
  `rac retrieve` on the CLI, one shared core implementation (ADR-031) —
  returns a ranked, budget-capped grounding block with per-artifact
  provenance (discovery channel, matched scope entry, search evidence).
- A benchmark harness can drive the identical retrieval logic through the
  CLI without a server lifecycle, byte-identical to what agents get over
  MCP.
- Existing tools gain the two missing facets additively: `live_only` on
  `search_artifacts`, per-call `budget` on `get_artifact`.

## Initiatives

### Initiative 1 — Generalised live-only facet

Add a spec-driven retired-status predicate for any artifact type (the
generalisation of `is_live_decision`, reusing the spec's `retired_status`
set as relationship validation already does) and expose it as a `live_only`
filter on the core search seam, `rac find`, and the `search_artifacts`
tool. A pre-scoring constraint, like the ADR-109 tag facet.

### Initiative 2 — Per-call response budget

Add an optional `budget` argument to `get_artifact` (and the compound tool)
that lowers the effective ADR-033 character budget for that call only. Same
enforcement mechanism — whole-item and content-tail truncation with
markers — no new mechanism.

### Initiative 3 — Compound retrieve (core, CLI, MCP)

A pure core service composing: keyword and tag discovery over the index,
scope binding when a path is supplied, supersedes resolution to live
successors, the existing BM25F+RRF ranking, top-k and budget capping, and a
provenance block per returned artifact. Exposed as `rac retrieve` and the
`retrieve_grounding` MCP tool, both thin faces over the one core function.

### Initiative 4 — Benchmark consumption contract

Document how an external harness (the SWE-DecisionBench `rac` arm, the
`tool-benchmarks` family) consumes the compound surface: the CLI invocation
form, JSON shape stability (ADR-007), and the provenance fields a
deterministic scorer needs to measure governing recall.

## Constraints

- Single call, deterministic, no model in the loop (ADR-002, ADR-066,
  ADR-097): the compound result is a pure function of corpus bytes and the
  request arguments.
- One shared core implementation for CLI and MCP (ADR-031); no parallel
  retrieval path — reuse the existing tokenizer, tiers, ranking, scope, and
  budget seams (ADR-037, ADR-038, ADR-078, ADR-109, ADR-033).
- Additive contract (ADR-007): new arguments and fields are optional;
  existing tool responses are byte-identical when the new arguments are not
  used.
- Adding a sixth MCP tool changes the pinned tools-only surface (ADR-030)
  and must stay inside the standing surface token budget's hard cap.

## Non-Goals

- Any embedding, vector, or LLM-judged retrieval; the `naive_rag` arm stays
  in the external benchmark repo (`rac-grounding-baseline-study`).
- Agentic multi-step retrieval; the compound op is one deterministic pass.
- Replacing the existing primitive tools — they remain for consumers that
  want to compose their own retrieval.

## Success Measures

- The SWE-DecisionBench `rac` arm invokes one CLI call per cell and its
  output is byte-identical to the MCP tool's JSON for the same request.
- Repeated compound calls on an unchanged corpus return byte-identical
  results.
- Provenance names, for every returned artifact, why it was returned
  (channel, matched entry or evidence), sufficient for a deterministic
  governing-recall scorer.

## Assumptions

- The existing BM25F+RRF ranking (ADR-078) is the ranking opinion worth
  exposing; the compound op adds composition, not a new ranker.
- Character budgets (ADR-033) are an acceptable lean-grounding unit for
  benchmark fairness; a token view can be derived downstream.

## Risks

- The compound tool could be read as RAC doing the agent's reasoning
  (ADR-034). Mitigation: the result is facts with provenance produced by a
  deterministic pipeline; ADR-113 records the boundary explicitly.
- Surface growth: a sixth pinned tool spends standing-surface tokens
  (ADR-030). Mitigation: the surface budget gate is a named implementation
  gate; the tool description is written to fit.

## Related Decisions

- adr-002
- adr-007
- adr-030
- adr-031
- adr-033
- adr-034
- adr-037
- adr-038
- adr-066
- adr-067
- adr-078
- adr-093
- adr-094
- adr-097
- adr-109
- adr-113

## Related Roadmaps

- tool-benchmarks
- retrieval-diagnostics
- lean-context-delivery

## Related Requirements

- rac-compound-grounding-retrieval
- rac-grounding-baseline-study
- rac-selective-retrieval-default
