---
schema_version: 1
id: RAC-KVSQ232DWE6N
type: requirement
---
# Deterministic Relevance Ranking

## Problem

RAC's search (`rac find` and `search_artifacts`) ranks by a fixed tier ladder —
identifier, then title, then path, then heading, then body, with ties broken by
sorted path (ADR-037, ADR-038). That is deterministic and explainable, but it is
coarse: within a tier every hit is equal, so the order of two body-matched
artifacts is decided by path alphabetisation, not by how well each actually
matches the query. An agent grounding itself through `search_artifacts` gets a
correctly-filtered but poorly-ordered candidate list, and the response budget
means a weakly-relevant artifact sorted ahead of a strong one can crowd the
strong one out of the window entirely.

The signal to fix this is already in the corpus and unused for ranking: term
frequency within a field, and the validated relationship graph (a
heavily-referenced decision is usually a better answer than an isolated one).
The constraint is that RAC's retrieval must stay deterministic, offline, and
free of embeddings or semantic scoring (ADR-038, ADR-066) — so the fix has to be
a *lexical and structural* relevance model, not a vector one.

The affected users are every agent and human who searches: better ordering means
the right artifact lands inside the response budget more often.

## Requirements

- [REQ-001] RAC SHALL rank search results by a deterministic relevance score, not by tier precedence alone, so that within and across tiers a more relevant artifact ranks higher.
- [REQ-002] The score SHALL include a deterministic lexical component in the BM25 family (term frequency with inverse document frequency over the matchable fields), computed with no embeddings, semantic similarity, stemming, or synonym expansion (ADR-038, ADR-066).
- [REQ-003] RAC SHALL fuse the per-field/tier signals into one ranking using Reciprocal Rank Fusion (RRF), so a result strong on one signal ranks sensibly without hand-tuned tier weights.
- [REQ-004] RAC SHALL apply a deterministic graph-derived boost computed from the validated relationship graph (for example inbound-reference count or a bounded centrality measure), so a well-connected artifact ranks above an isolated one at equal lexical relevance.
- [REQ-005] Ranking SHALL stay explainable: each result SHALL continue to carry its match evidence (winning field, matched terms, tier) and SHALL additionally expose the contributing score components, so a caller can see why one result outranks another (extending the explainable-retrieval contract).
- [REQ-006] Ranking SHALL be deterministic and offline: identical corpus bytes and query yield a byte-identical ordering across runs, with stable, documented tie-breaking and no model or network call.
- [REQ-007] The search JSON contract SHALL change additively (ADR-007): existing fields are unchanged and the score components are new optional fields, with `schema_version` unchanged.

## Success Metrics

- The grounding-eval benchmark (`rac eval --check`, ADR-066) holds or improves
  Precision@k / Recall@k against the committed baseline after ranking changes —
  the ordering is measured, not asserted.
- Re-running a query on an unchanged corpus yields a byte-identical result order.
- For a query with several body matches, the artifact a maintainer judges most
  relevant ranks at or near the top, where tier-precedence alone left it ordered
  by path.

## Risks

- **Complexity regression.** ADR-038 deliberately chose a simple ladder; a scorer
  adds moving parts. Mitigation: keep every component deterministic and
  explainable, pin behaviour with golden tests, and gate quality on `rac eval`.
- **Hub over-boosting.** A graph boost could float highly-referenced artifacts to
  the top of unrelated queries. Mitigation: bound the boost and fuse it via RRF
  rather than letting it dominate lexical relevance; tune against the benchmark.

## Assumptions

- Lexical term-frequency relevance plus graph connectedness orders results closer
  to what a searcher wants than tier-precedence-then-path does, and the
  improvement is measurable via `rac eval`.
- BM25, RRF, and graph centrality are deterministic and explainable, so they sit
  inside ADR-038/ADR-066's prohibition on embeddings and semantic scoring.

## Related Decisions

- adr-078
- adr-038
- adr-037
- adr-066
- adr-007

## Related Designs

- deterministic-relevance-ranking

## Related Roadmaps

- relevance-ranking

## Related Requirements

- rac-explainable-retrieval
- rac-grounding-eval-benchmark
