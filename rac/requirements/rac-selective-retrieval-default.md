---
schema_version: 1
id: RAC-KWK8HM6Q4YWT
type: requirement
---
# Requirement: Selective On-Demand Retrieval by Default

## Status

Proposed

Classification: `[internal]` — a default-behaviour guarantee for the retrieval
path. Initiative 2 of the `lean-context-delivery` roadmap.

## Problem

Context rot degrades every frontier model as input length grows, well before
the window fills, so dumping a corpus actively worsens output. The antidote is
selective, on-demand retrieval — pull the relevant artifact, not the whole
corpus. Lore's surfaces already lean this way, but the guarantee is not stated
or asserted, so a future change could quietly widen the default payload and
reintroduce the rot the tool exists to cure.

## Requirements

- [REQ-001] The default retrieval path MUST return the *relevant* artifacts for a query, not the whole corpus: search and lookup are scoped and on-demand, so an agent receives small, relevant payloads by construction.
- [REQ-002] The selective-by-default behaviour MUST be documented as the antidote to context rot, so callers understand the default and the deliberate option to pull more.
- [REQ-003] Selective delivery MUST respect the response budget (ADR-033): scoped payloads are additionally bounded by the budget, with truncation behaviour unchanged.
- [REQ-004] Bulk/whole-corpus delivery MUST remain an explicit, opt-in action rather than a default, so no caller receives the corpus unless it asks.
- [REQ-005] Selectivity MUST be achieved without semantic compression or summarisation (ADR-066): payloads are small because they are scoped, never because an artifact was lossily shrunk.

## Acceptance Criteria

- A representative query returns only the matching artifacts, not the full
  corpus, over the fixture corpus.
- The documented guidance states selective-on-demand as the default and names
  the explicit path to retrieve more.
- Scoped responses stay within the response budget; the budget's truncation
  behaviour is unchanged.
- No default path emits a whole-corpus payload; bulk retrieval is only ever an
  explicit request.

## Success Metrics

- Retrieval is selective and on-demand by default, so context rot is avoided
  by construction rather than by the caller's discipline.

## Risks

- Optimising for small payloads could under-serve an agent that genuinely
  needs more. Mitigation: on-demand retrieval lets the agent pull more when it
  asks, rather than front-loading everything (the roadmap's recorded
  mitigation).
- "Relevant" is under-specified and a change quietly widens the default.
  Mitigation: REQ-001 and REQ-004 fix scoped-by-default with bulk as explicit
  opt-in, assertable over the fixture.

## Assumptions

- The existing search and lookup surfaces already retrieve scoped results, so
  this confirms and documents a property rather than rebuilding retrieval.
- A small, structured corpus needs no semantic compression for payloads to
  stay lean; scoping is sufficient.

## Related Decisions

- adr-005
- adr-033
- adr-066

## Related Roadmaps

- lean-context-delivery

## Related Requirements

- rac-mcp-surface-budget
- rac-cli-first-delivery
