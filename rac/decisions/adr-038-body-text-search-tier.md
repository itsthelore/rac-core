---
schema_version: 1
id: RAC-KTXTAG63E89H
type: decision
---
# ADR-038: Body-Text Search Tier

## Status

Proposed

## Category

Technical

## Context

v1 search deliberately matches metadata fields only — identifier,
title, and path — and the `guide-tool-surface` design records body-text
matching as an open question for a later version. The miss is real: a
decision whose title does not carry the query keyword is invisible to
search even when its body settles the question, and the agent falls
back to the grepping behaviour Guide exists to replace.

The cost side has already been paid. The corpus walk reads every
artifact's content to parse it, so body text is available in the same
snapshot search already uses, and the per-response budget (ADR-033)
already bounds what any response can spend of the agent's context.

The boundary that must not move: retrieval stays exact and
deterministic. The agent is the semantic layer (ADR-034) — it
reformulates queries; Core never guesses.

## Decision

Body text joins search as the lowest-ranked matching tier.

- The ranking ladder extends to: identifier, then title, then path,
  then section heading, then body — ties broken by sorted path, exactly
  the existing pattern.
- Matching uses the token-boundary semantics of ADR-037; multi-term
  queries require every term to match, anywhere in the artifact's
  matchable fields.
- Body and heading matches carry additive snippet fields in search
  responses — the matching line's text and its section heading — so an
  agent can judge relevance without spending a `get_artifact` per
  candidate. Snippet fields follow the additive rules of ADR-007 and
  truncate as whole items under the existing response budget.
- The implementation lives in Core and serves `rac find` and
  `search_artifacts` identically (ADR-031).
- No embeddings, semantic scoring, stemming, or synonym expansion in
  Core — ever, under this decision. Query reformulation belongs to the
  consuming agent; the tool description may suggest retrying a missed
  search with a synonym, which is a description-contract revision that
  can be measured (the `guide-tool-surface` measurement protocol).

## Consequences

### Positive

- Recall reaches the artifacts whose bodies, not titles, answer the
  query — the common case for decisions on large corpora.
- Snippets let the agent triage matches cheaply, reducing total context
  spent per grounded answer.
- The ranking ladder remains a one-sentence, golden-testable contract.

### Negative

- Common words match many artifacts; responses grow and truncate more
  often. Mitigated by AND semantics, tier ranking, and the budget.
- Search output gains fields; the search contract grows and must stay
  pinned.

### Risks

- Corpus growth makes in-memory body matching slow. The corpus-snapshot
  seam remains the optimization point, per the ADR-032 posture:
  optimize when a real user reports it, without breaking determinism.
- Snippet extraction rules (line boundaries, length) accrete edge
  cases. Mitigated by whole-line snippets only, pinned by contract
  tests.

## Alternatives Considered

### Embedding or RAG-based retrieval

Rejected: breaks byte-stable determinism (ADR-032), adds a model
dependency to a deterministic core, and falsifies the product's "no
RAG, no guessing" claim. Semantic flexibility is the agent's job
(ADR-034).

### Opaque lexical scoring (BM25-style)

Rejected: deterministic given a fixed corpus, but the ranking stops
being explainable or stable under corpus growth, and golden tests pin
it poorly. A tiered ladder is worth more than a better score.

### Remain metadata-only

Rejected: the misses push agents back to grepping, which is the
behaviour Guide exists to replace.

## Related Decisions

- ADR-007
- ADR-031
- ADR-032
- ADR-033
- ADR-034
- ADR-037

## Related Designs

- guide-tool-surface
