---
schema_version: 1
id: RAC-KX8EAEPHWWQQ
type: design
---
# Paraphrase Recall Response — Closing the Miss Side of Deterministic Search

## Status

Proposed

## Context

Retrieval is deterministic and lexical by hard decision: token-boundary
matching (ADR-037), a body-text tier (ADR-038), tag tier (ADR-109), BM25 +
RRF fusion with a bounded graph boost, and no embeddings or LLM judging
anywhere in core (ADR-066, ADR-002). The recorded cost is the paraphrase
gap: a query with zero keyword overlap misses silently. July 2026 demand
research (`research/2026-07-agentic-tooling-demand.md`) puts context-supply
over MCP at the centre of what agent-equipped teams want, and they will
judge it by recall. The outbound Supermemory adapter
(`lore-supermemory-grounding`) records the sidecar direction; explain-miss
diagnostics are recorded in `retrieval-diagnostics`. This design ties those
threads into one answer to the question "what happens when a well-formed
query misses?"

## User Need

An agent (or its human) asks `lore` a reasonable question phrased in words
the corpus does not use — "what did we decide about caching defaults?"
against an artifact titled "warm-by-default" — and gets an empty result.
They need either the right artifact anyway, or a legible explanation of the
miss and a cheap next move, instead of silently concluding the knowledge
does not exist.

## Design

Three layers, none of which put semantics inside core:

- **Deterministic reformulation guidance (core).** On a low-confidence or
  empty result, `search_artifacts` returns a structured miss payload
  instead of a bare empty list: nearest lexical neighbours (existing index
  terms with closest token overlap), the tag facet, and a one-line
  instruction telling the agent to reformulate using corpus vocabulary.
  The reasoning stays on the agent's side of the ADR-034 boundary — core
  supplies vocabulary, the model does the paraphrasing. This exploits the
  fact that every MCP consumer already has a capable model in the loop.
- **Explain-miss (core).** The `retrieval-diagnostics` explain-miss
  initiative: `rac find --explain-miss <id>` answers "why did this query
  not surface artifact X" with the tier-by-tier reason. Serves corpus
  authors tuning titles and tags so lexical recall improves at the source.
- **Semantic sidecar (outside core).** For teams that want associative
  recall, the outbound-only export path of `lore-supermemory-grounding`
  stands: RAC exports, the sidecar recalls, the artifact id always resolves
  back through `lore` for the deterministic ground truth. Core never reads
  the sidecar back.

## Constraints

- ADR-066 and ADR-002 are not amended: no embeddings, no LLM judge, no
  network calls in core retrieval.
- ADR-037/ADR-038/ADR-109 tier semantics unchanged; the miss payload is
  additive to the response shape, subject to JSON contract stability
  (ADR-007) and the Guide response budget (ADR-033).
- ADR-032: the miss payload must be computable statelessly from the index.
- The reformulation loop costs the agent an extra tool call; the payload
  must be small enough that retry-with-better-vocabulary is cheaper than
  the agent giving up.

## Rationale

The paraphrase gap does not require abandoning determinism — it requires
noticing that the consumer is a model. Supplying corpus vocabulary on a
miss converts "silent empty result" into a one-turn self-correction, keeps
every core guarantee, and is testable with the deterministic grounding
eval (ADR-066). The sidecar remains available for teams whose recall needs
exceed what reformulation delivers, without core inheriting its trust
problems.

## Alternatives

- Embeddings in core behind a flag. Rejected: splits the determinism
  guarantee into configuration, contradicts ADR-066 rather than working
  within it.
- Static synonym/alias tables in config. Deterministic and honest, but
  maintenance-heavy and perpetually stale; vocabulary-on-miss achieves the
  same effect using the model already present.
- Doing nothing beyond the sidecar. Leaves the default (keyless, core-only)
  experience with silent misses, which is where the demand research says
  the judgement happens.

## Open Questions

- Miss-payload trigger: empty results only, or also below a score
  threshold? A threshold risks noise on genuinely thin corpora.
- How many neighbour terms fit the ADR-033 budget without crowding out
  real results on the hit path?
- Should the grounding eval (ADR-066) grow a paraphrase family to measure
  whether reformulation actually closes the gap?

## Related Decisions

- adr-002
- adr-007
- adr-032
- adr-033
- adr-034
- adr-037
- adr-038
- adr-066
- adr-109

## Related Roadmaps

- retrieval-diagnostics
- lore-supermemory-grounding
- agentic-demand-alignment
