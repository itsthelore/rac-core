---
schema_version: 1
id: RAC-KVSQ24G2H2D6
type: decision
---
# ADR-078: Deterministic Relevance Ranking — BM25, RRF, and a Graph Boost

## Context

Search ranks by a fixed tier ladder (id, title, path, heading, body; ties by
sorted path) under ADR-037 and ADR-038. ADR-038 made two commitments that this
decision must respect: the ladder's *matching* is token-boundary and body-aware,
and — emphatically — there is "no embeddings, semantic scoring, stemming, or
synonym expansion in Core, ever." ADR-066 reaffirms the same line for grounding:
deterministic scoring, no embeddings, no LLM judge.

The ladder's weakness is *ordering within a tier*: two body matches are ranked by
path alphabetisation, not by how well each matches the query, so a weak hit can
sort ahead of a strong one and, under the response budget, push the strong one
out of the window. Two deterministic signals already present are unused for
ranking — term frequency within a field, and the validated relationship graph (a
much-referenced artifact is usually a better answer than an isolated one).

The question is how to use them without crossing ADR-038/ADR-066. BM25 is a
*lexical, statistical* relevance model (term frequency × inverse document
frequency) — not semantic, no embeddings, no stemming required; Reciprocal Rank
Fusion (RRF) combines ranked lists by `Σ 1/(k + rank)`, a pure arithmetic merge;
graph centrality is a count over edges RAC already validates. All three are
deterministic and explainable.

## Decision

Replace tier-precedence-then-path ordering with a deterministic **relevance
score**, while reaffirming ADR-038/ADR-066's prohibition on embeddings, semantic
scoring, stemming, and synonym expansion. This **refines ADR-038's ranking
clause only**; its tier set, token-boundary matching, snippet fields, and the
no-embeddings/no-semantic guardrail all stand unchanged.

- **BM25-family lexical scoring.** Each matchable field is scored by term
  frequency with inverse document frequency across the corpus — a statistical
  lexical score, never a semantic one (ADR-038 holds).
- **RRF fusion.** The per-field/tier ranked lists are fused with Reciprocal Rank
  Fusion (`Σ 1/(k + rank)`), so a result strong on one signal ranks well without
  hand-tuned tier weights. The tier *identity* still informs the inputs (an id
  match is a strong list); RRF replaces the brittle "best tier, then path"
  tiebreak.
- **Bounded graph boost.** A deterministic boost derived from the validated
  relationship graph (inbound-reference count, normalised/capped) is fused in as
  one more signal, so connectedness breaks near-ties toward the artifact the
  corpus already leans on. It is bounded so it cannot dominate lexical relevance.
- **Explainable and additive.** Results keep their match evidence and gain the
  contributing score components as additive JSON fields (ADR-007); the order is a
  pure function of corpus bytes and the query, byte-stable across runs.

The implementation stays in Core and serves `rac find` and `search_artifacts`
identically (ADR-031). Quality is gated on the deterministic grounding benchmark
(`rac eval --check`, ADR-066), so the new order is measured against the committed
baseline rather than asserted.

## Consequences

Agents and humans get a candidate list ordered by relevance, so the right
artifact lands inside the response budget more often — the ordering improvement
the tier ladder could not make. Every component is deterministic and
explainable, so the property that makes RAC's retrieval trustworthy and testable
is preserved, and the change is provable on the eval benchmark.

Trade-offs accepted: ranking gains moving parts ADR-038 deliberately avoided
(BM25 statistics, an RRF merge, a graph term), which is more to test and explain
than a path tiebreak — mitigated by golden tests, additive contracts, and the
eval gate. The graph boost risks floating hubs onto unrelated queries; it is
bounded and fused, never dominant, and tuned against the benchmark. This is a
refinement of ADR-038, not a reversal: the moment a proposal here reached for an
embedding or a semantic score, it would contradict ADR-038/ADR-066 and be out of
scope.

## Status

Proposed

## Category

Technical

## Alternatives Considered

- **Keep the tier-precedence ladder.** The status quo (ADR-038). Rejected: it
  leaves within-tier order to path alphabetisation, which is the defect — a weak
  body hit can outrank a strong one and crowd it out of the budget.
- **Add semantic / embedding ranking.** Rejected outright: it contradicts the
  explicit "ever" prohibition of ADR-038 and ADR-066. Determinism, offline
  operation, and explainability are non-negotiable here.
- **Hand-tuned per-tier weights instead of RRF.** Rejected: weights are brittle
  and corpus-specific; RRF is parameter-light (one constant `k`), deterministic,
  and robust to combining heterogeneous signals.
- **Graph boost as the primary sort key.** Rejected: it would answer queries with
  whatever is most-referenced regardless of lexical fit. The boost is a bounded
  tiebreak fused via RRF, not the lead signal.

## Related Decisions

- adr-038
- adr-037
- adr-066
- adr-007
- adr-031

## Related Requirements

- rac-deterministic-relevance-ranking

## Related Designs

- deterministic-relevance-ranking

## Related Roadmaps

- v0.29.0-relevance-ranking
