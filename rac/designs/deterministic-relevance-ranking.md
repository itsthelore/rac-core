---
schema_version: 1
id: RAC-KVSQ25YPB5WT
type: design
---
# Deterministic Relevance Ranking

## Context

This design is the *how* for the `rac-deterministic-relevance-ranking`
requirement and the boundary ADR-078 draws: rank search by a deterministic
relevance score — BM25-family lexical scoring, RRF fusion, and a bounded graph
boost — without ever introducing embeddings or semantic scoring (ADR-038,
ADR-066).

The machinery to extend already exists. `services/resolve.py` runs the tiered
matcher: for each artifact it finds the best (lowest) tier any query term hits
across id, title, path, heading, and body (ADR-037 token-boundary matching,
ADR-038 body tier), records match evidence `{field, terms, tier}` (v0.23
explainable retrieval), and orders by tier then sorted path. This design keeps
the matcher and the evidence; it replaces the *ordering* step.

**Prior art.** Hybrid retrieval systems (for example GBrain) fuse a lexical
(BM25/`tsvector`) ranking with a vector ranking using RRF, and boost by graph
backlinks. RAC adopts the deterministic half — BM25 + RRF + a graph boost — and
omits the vector half, which ADR-066 excludes.

## User Need

An agent grounding itself through `search_artifacts`, and a human running
`rac find`, want the most relevant artifact at the top, not merely inside the
correct tier. Under the response budget, order decides what the agent even sees.
They also need the order to stay reproducible and explainable: the same query
must give the same ranking, and a caller must be able to see why one hit
outranks another, exactly as `--explain` shows today.

## Design

### Signals (all deterministic, all lexical or structural)

For a query of one or more terms, each candidate artifact produces:

- **Per-field BM25 scores.** For each matchable field (id, title, path, heading
  text, body text) a BM25 score over the query terms: term frequency in the
  field, damped by field length, weighted by inverse document frequency across
  the corpus. Token-boundary tokenisation is ADR-037's, unchanged; no stemming,
  no synonyms. Fields keep their relative importance through standard BM25 field
  weighting (title and id heavier than body), replacing the hard tier cutoff with
  a graded contribution.
- **A graph score.** A bounded value from the validated relationship graph —
  inbound reference count, normalised and capped (a log or min-cap so a few hubs
  cannot dominate). Computed from the same relationship index `rac relationships`
  and `rac doctor` already build.

### Fusion (RRF)

Each signal produces a ranked list of candidates. The lists are merged with
**Reciprocal Rank Fusion**: an artifact's fused score is `Σ 1/(k + rank_s)` over
each signal `s` it appears in, with a fixed constant `k` (the conventional 60,
recorded as the one tunable). RRF is chosen over weighted-sum because it needs no
per-field weight tuning, is robust to combining heterogeneous signals (a
BM25 score and a graph count are not on the same scale), and is a pure arithmetic
function — deterministic and trivially explainable.

The matching contract from ADR-038 is unchanged: a multi-term query still
requires every term to match somewhere; only artifacts that match at all enter
the ranking. RRF reorders the matched set; it never widens it.

### Tie-breaking

Equal fused scores break by the existing rule — sorted path — so the order stays
total and byte-stable. Tie-breaking is documented as part of the contract.

### Surfaces and contract

- **`rac find` / `search_artifacts`** consume the new order identically (ADR-031);
  no new verb.
- **Explainability (additive, ADR-007).** Each result keeps `{field, terms, tier}`
  and gains optional score components: the per-signal contributions and the fused
  score, so `--explain` and the JSON show *why* the order is what it is.
  `schema_version` is unchanged; existing fields are untouched.
- **Determinism.** The order is a pure function of corpus bytes and query, proven
  by golden tests; no model, embedding, or network call is on the path.

### Quality gate

Ranking changes are measured, not asserted: the deterministic grounding benchmark
(`rac eval --check`, ADR-066) must hold or improve Precision@k / Recall@k against
the committed baseline before the change ships, so a ranking tweak that helps one
query but hurts the corpus is caught.

## Constraints

- No embeddings, semantic scoring, stemming, or synonym expansion — ever
  (ADR-038, ADR-066). BM25 is statistical lexical scoring; RRF and the graph
  boost are arithmetic over existing data.
- Deterministic and offline: identical bytes and query yield identical order.
- Additive contract (ADR-007): existing search fields unchanged; score components
  are new optional fields.
- Reuse the existing matcher, tokeniser, relationship index, and eval harness; do
  not fork a parallel search path. Core serves both surfaces (ADR-031).

## Rationale

BM25 is the standard deterministic answer to "which lexical match is stronger,"
and it stays inside ADR-038's line because it is statistical, not semantic. RRF
is the standard way to combine ranked lists without scale-matching or weight
tuning, and it keeps the result explainable. The graph boost turns data RAC
already validates into a relevance signal at near-zero cost. Gating on `rac eval`
makes the whole thing falsifiable, which is the property ADR-066 exists to
protect.

## Alternatives

- **Keep tier-then-path ordering.** Rejected (ADR-078): the within-tier order is
  the defect.
- **Vector / embedding ranking.** Rejected: contradicts ADR-038/ADR-066.
- **Weighted-sum fusion with per-tier weights.** Rejected: brittle and
  corpus-specific; RRF is parameter-light and robust.
- **Unbounded backlink boost (as some hybrid systems use).** Rejected: it floats
  hubs onto unrelated queries; the boost is capped and fused, not dominant.

## Accessibility

Output is plain text and diffable, the same shape as today's results, with the
score components available in `--explain` and `--json`; nothing relies on colour
or a graphical display.

## Style Guidance

Default human output is unchanged in shape — ranked list with snippets;
`--explain` adds the score breakdown compactly, in the established `rac find`
style. Copy frames the score as a deterministic relevance signal, never a
semantic judgement of meaning.

## Open Questions

- The exact BM25 field weights and whether they are fixed or configurable.
- The graph-score shape (raw inbound count vs a capped/log centrality) and its
  cap, tuned against the benchmark.
- Whether the RRF constant `k` is fixed at 60 or exposed in `.rac/config.yaml`.

## Related Decisions

- adr-078
- adr-038
- adr-037
- adr-066
- adr-007

## Related Requirements

- rac-deterministic-relevance-ranking

## Related Roadmaps

- v0.29.0-relevance-ranking
