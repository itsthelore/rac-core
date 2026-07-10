---
schema_version: 1
id: RAC-KX6WESB8QYKN
type: decision
---
# ADR-113: Compound Deterministic Retrieval Surface

## Context

The SWE-DecisionBench study (`rac-grounding-baseline-study`) compares
grounding arms under one fixed answering model. Its `rac` arm should measure
RAC's retrieval judgement, but RAC exposes only primitives —
`search_artifacts`, `find_decisions`, `get_artifact`, `get_related`,
`get_summary` — so the arm author must hand-compose discovery, scope
binding, supersedes handling, ranking, and budgeting. The benchmark then
scores the author's composition, not the engine's. The same is true for any
agent that wants "the best grounding for this task" in one call.

The primitives are close but not sufficient. Scope lookup is already on the
MCP (`find_decisions(topic, path)`, ADR-067) and the tag facet already
exists (ADR-109), but there is no general live-only facet (liveness is
modelled only for decisions), no per-call response budget (ADR-033's budget
is server-wide, fixed at construction), and no compound operation that
returns a ranked, capped, provenance-carrying grounding block.

Three recorded decisions constrain the shape of a fix: ADR-030 pins the
tools-only surface and its verbatim descriptions; ADR-033 pins the
character-budget enforcement; ADR-034 draws the line that Guide tools return
facts and the agent does the reasoning. ADR-066 and ADR-097 pin the
determinism posture any benchmarked surface must keep.

## Decision

RAC owns its grounding opinion and exposes it as a compound deterministic
retrieval operation, plus two additive facets on existing tools.

- **Compound operation.** A pure core service,
  `retrieve_grounding(task, scope, top_k, budget, live_only)`, composes the
  existing seams in one pass: keyword and tag discovery over the index
  (ADR-037/038/109 matching), scope binding when `scope` is given (the
  `decisions-for` semantics — declared `## Applies To` coverage, which binds
  regardless of keyword match), supersedes resolution (retired artifacts are
  dropped and replaced by their live successor along the inbound
  `supersedes` edge), the existing BM25F+RRF ranking (ADR-078), then top-k
  and budget capping. Every returned artifact carries provenance: the
  discovery channel(s), the matched scope entry when scope-bound, and the
  search evidence (field, terms, tier, score components) — the same evidence
  `--explain` surfaces.
- **Two faces, one implementation (ADR-031).** The MCP tool
  `retrieve_grounding` and the CLI command `rac retrieve` are thin faces
  over the one core function; their JSON output is byte-identical for the
  same request. A benchmark harness drives the CLI form per cell with no
  server lifecycle and measures exactly what agents get over MCP.
- **Single call, deterministic, no model in the loop.** The result is a
  pure function of corpus bytes and request arguments: no embeddings, no
  LLM, no network, no clock or randomness in the scored path (ADR-002,
  ADR-066, ADR-097).
- **`live_only` facet on search.** The liveness predicate generalises from
  decisions to every artifact type, spec-driven off the type's
  `retired_status` set (the same source relationship validation already
  reads), and is exposed as a pre-scoring filter on the core search seam,
  `rac find --live`, and `search_artifacts(live_only=...)`. Default off on
  the primitives (additive, ADR-007); default on in the compound operation.
- **Per-call `budget` on `get_artifact` and the compound op.** An optional
  integer that lowers the effective response budget for that call only,
  enforced by the existing ADR-033 mechanism (whole-item and content-tail
  truncation with `truncated`/`omitted` markers). The unit stays characters
  of serialized JSON — deterministic across tokenizers — not tokens. A
  per-call value may only lower, never raise, the server-wide budget.
- **Surface change is explicit.** The pinned tool surface (ADR-030) grows
  from five tools to six; the new tool's description is a verbatim-pinned
  product string and the standing surface token budget's hard cap is a
  named implementation gate.
- **Reasoning boundary holds (ADR-034).** The compound result is facts with
  provenance produced by a deterministic pipeline. Selecting and ordering by
  a recorded, explainable scoring function is retrieval, not reasoning: the
  agent still decides what the grounding means for its task. If RAC
  declined to own this composition, every consumer would re-implement it
  divergently — that, not the composition, would blur the boundary.

## Consequences

### Positive

- The benchmark measures RAC's judgement: one call per cell, symmetric with
  `naive_rag`'s single top-k, with provenance a deterministic scorer can use
  to measure governing recall.
- Agents get lean grounding in one round-trip instead of a hand-rolled
  multi-call dance; per-call budgets stop a single artifact from dominating
  a context window.
- The facets close real gaps additively; untouched calls stay
  byte-identical (ADR-007).

### Negative

- A sixth pinned tool spends standing-surface tokens (ADR-030) and adds a
  contract to maintain, benchmark (ADR-097), and document.
- The compound operation's output shape becomes load-bearing for an external
  publication study; changing it later is a contract change, not a refactor.
- Generalising liveness beyond decisions gives every typed spec's
  `retired_status` a retrieval-visible meaning it did not previously carry;
  specs must keep it accurate.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

### Keep primitives only; the benchmark arm hand-composes

Rejected as the default, but recorded as the fallback finding: if RAC
declines to own the composition, RAC is a primitives kit, not a retriever,
and the benchmark measures arm-author skill. Owning the opinion is the
product position.

### Compose in the benchmark repo against the Python SDK

Rejected: the composition would live outside the contract surface,
unavailable to agents over MCP, and ADR-063 keeps non-Python clients thin
over the contract — the compound op must be *on* the contract.

### Token-denominated budgets

Rejected: ADR-033 chose characters of serialized JSON precisely because the
unit is deterministic across tokenizers; a token unit would re-open that.
The deterministic token approximation remains available downstream for
consumers that need a token view.

### An agentic retrieve (model-planned multi-step)

Rejected outright: violates ADR-002/ADR-066 determinism and would make the
benchmark unscorable as a pure function of corpus and query.

## Relationship to Other Decisions

- ADR-030 (RAC-KTW0M81E7TRA area — tools-only surface): amended by
  extension; the pinned surface grows to six tools.
- ADR-033 (RAC-KTW0M81HX5C6): the per-call budget is an additive parameter
  on the same enforcement mechanism.
- ADR-034 (RAC-KTW0M81MVJ7D): the reasoning boundary holds; deterministic
  composition with provenance is retrieval, not reasoning.
- ADR-067 (RAC-KV80WX94GY8A): scope lookup on the MCP already exists; the
  compound op folds it in as a discovery channel.
- ADR-031 (RAC-KTW0M81B0GBB): CLI and MCP share the one core
  implementation.
- ADR-066 (RAC-KV6KFCC8MHTM) and ADR-097 (RAC-KWFVA38YT2C0): the compound
  surface inherits the deterministic, benchmarkable posture and joins the
  per-tool benchmark family.
- ADR-078 (RAC-KVSQ24G2H2D6): the compound op exposes the existing ranking,
  it does not add a new one.
- ADR-109 (RAC-KWY7886GSEE5): the tag facet precedent the `live_only` facet
  follows (pre-scoring constraint, CLI and MCP served identically).
- ADR-007 (RAC-KTQ63DPYKJF4): all changes to existing tools are additive.

## Related Roadmaps

- grounding-retrieval-surface
