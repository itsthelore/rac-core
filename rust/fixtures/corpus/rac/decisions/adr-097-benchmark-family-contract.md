---
schema_version: 1
id: RAC-KWFVA38YT2C0
type: decision
---
# ADR-097: Benchmark Family Contract

## Context

ADR-066 fixed the scoring posture for the grounding eval: deterministic,
offline, no embeddings, no vector search, no LLM judge — a pure function of
`(corpus, query set, retrieval code)`. ADR-092 fixed the home: one
`rac-benchmarks` repository, one subdir per benchmark. The per-tool suite
(one benchmark per Lore MCP tool: `search_artifacts`, `find_decisions`,
`get_artifact`, `get_related`, `get_summary`) now generalizes that posture
into a family, and the stress-test of the existing grounding benchmark
exposed three measurement gaps the family must close:

- `find_decisions` — the one tool with a structural supersession defense —
  had zero benchmark coverage anywhere; supersession was tested only through
  `search_artifacts`, which applies no liveness filter.
- The hard-negative window was top-5 while `search_artifacts` serves the
  full match list, so a superseded decision at rank 6 reached agents
  unflagged.
- The gate (P@1, R@5) is blind to ordering within ranks 2–5, although the
  shipped ranking work was justified by exactly that within-window ordering.

Contract-shaped tools (`get_artifact`, `get_summary`) additionally have no
ranked list at all: for a given lookup there is exactly one correct outcome,
which ranked-retrieval metrics cannot express.

## Decision

The benchmark family contract **extends ADR-066; it does not supersede it**.

Kept from ADR-066, unchanged: scoring is deterministic and offline — no
embeddings, no LLM judge, no network, no randomness, no clock in the scored
path; Precision@k and Recall@k at `k ∈ {1, 3, 5}`, macro-averaged (equal
weight per case); hard-negative violations gate at zero; re-baselining is
human-gated and CI never rebaselines; the serialized `metrics` block is
byte-identical across runs on an unchanged corpus.

Added for the family:

- **MRR** (mean reciprocal rank) joins the gated retrieval metrics —
  rank-aware and deterministic, it catches within-top-5 ordering regressions
  the P@1 / R@5 floors are blind to.
- **Full-returned-list negative window**: a `must_not_return` id appearing
  ANYWHERE in the returned list is a violation. The top-5 window
  under-enforced the "never surface a superseded decision" claim.
- **Conformance pass-rate** is the metric for contract-shaped tools
  (`get_artifact`, `get_summary`, and the CLI-scoped `get_related` edge
  sets), gated at 1.0 with zero tolerance: a contract is either honoured or
  it is not.

Recorded scope: the v1 harness drives `rac` strictly as an external CLI on
`PATH` per the benchmark repository's DG-ADR-0001 — zero engine imports. The
MCP-only behaviours — `get_related` depth-greater-than-one neighborhoods and
the ADR-033 response budget / truncation markers — are invisible to the CLI
and are named future work (the MCP-stdio harness workstream), not silently
dropped. The port of `decisiongrounding` onto the shared harness is a
`tool-benchmarks` roadmap initiative and must not expand the frozen
restructure item's scope.

## Consequences

Every Lore MCP tool gains a gated benchmark with a committed baseline, and a
retrieval or contract regression in any of them fails CI in
`rac-benchmarks`. Fixture corpora become load-bearing: the full-list negative
window means hard-negative artifacts must share no query vocabulary, so
corpus edits must re-run their benchmark before commit. The scorecard JSON
(`{metrics, metadata, per_query}`) is an additive, stable contract per
ADR-007 — emitted fields are never removed or renamed.

## Status

Accepted

## Category

Technical

## Alternatives Considered

- Superseding ADR-066 with a single new contract: rejected — ADR-066's
  posture is unchanged and still governs the existing grounding eval; the
  family adds to it.
- Keeping the top-5 negative window for symmetry with `rac eval`: rejected —
  the tools serve the full match list, so the window must cover what agents
  actually receive.
- Scoring contract-shaped tools with P@k over a single-item list: rejected —
  it blurs "wrong outcome" into a partial score; conformance at 1.0 states
  the contract plainly.
- An LLM judge for the conformance checks: rejected outright by ADR-066.

## Related Decisions

- adr-066
- adr-092
- adr-007

## Related Roadmaps

- tool-benchmarks
