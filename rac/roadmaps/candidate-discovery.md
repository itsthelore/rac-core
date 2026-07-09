---
schema_version: 1
id: RAC-KWY786B4XMZE
type: roadmap
---
# Candidate Discovery

## Status

Planned

Captures the candidate-discovery entry-point work surfaced by the first
benchmark run: the path a query takes to find candidate artifacts before the
typed graph. The persistent inverted index (adopted via the rebuild-scale
work) made warm retrieval scale-invariant; this roadmap tracks the discovery
*quality* and *reach* gaps that remain.

## Context

The benchmark showed the typed graph layers hold up but the entry point into
them was the scaling bottleneck. Adopting the persistent memory-mapped index
made candidate discovery bound by query selectivity rather than corpus size —
deterministic and lexical, no embeddings (ADR-037/038/066). Two discovery gaps
remain from that analysis: frontmatter `tags` are parsed and validated but
invisible to search (no tag tier, no tag filter), and the postings-served fast
path is opt-in and serves only the compacted base. This roadmap records those
as scheduled work rather than latent gaps.

## Outcomes

- Frontmatter `tags` are a first-class part of discovery: a query term matches
  an artifact's tags, and a `--tag` facet narrows results to artifacts carrying
  a tag — the curated topical signal authors already write becomes findable.
- Discovery stays deterministic and lexical end to end: every new signal is a
  BM25F/tier extension, never an embedding or semantic score (ADR-038/066).

## Initiatives

- Tag search tier and tag facet: make `tags` a searchable lexical field (a
  metadata tier between title and path, ADR-037 tokenisation, a BM25F boost)
  and add a `--tag` / `tags` facet with AND semantics to `rac find` and the
  `search_artifacts` tool. Ships behind a persisted-store format bump with the
  byte-parity gate re-proven (ADR-109).
- One-shot CLI store reuse: `rac find --cache` serves the query from the
  persistent index store (ADR-104) via `load_or_build` instead of a fresh
  walk, so a benchmark or agent issuing many one-shot queries against a
  stable corpus skips the parse and graph rebuild on every warm invocation.
  Byte-identical to the uncached walk. Shipped opt-in under ADR-110; the
  `warm-by-default` roadmap has since flipped it to the default, with a
  persisted stat manifest replacing the per-call byte-hash freshness check.
- (Deferred, tracked elsewhere) Folding delta-window postings into discovery so
  edited corpora keep the fast path before compaction, and lowering the one-shot
  freshness cost below the O(files) stat floor (a git/fsmonitor fast path) —
  recorded in the single-node-scale residuals, not this item.

## Success Measures

- A query term present only in an artifact's tags retrieves it; a `--tag`
  filter constrains the result set to artifacts carrying every requested tag,
  case-insensitively; both served byte-identically whether index-on or
  index-off.
- Tag tokens do not leak into other tiers (a tag-only term surfaces no
  heading/body snippet), and untagged corpora are byte-identical to the
  pre-tags output.
- `rac find --cache` returns byte-identical output to `rac find` for search,
  the `--decisions` query, `--type`, `--tag`, and `--explain`, cold and warm;
  the warm run serves from the store without re-parsing.

## Assumptions

- `tags` remain a validated frontmatter list of non-empty strings; the tag
  facet matches whole tags, the tier matches tokenised tags.
- The persisted index remains a disposable derived structure; a format bump is
  a rebuild cost, never an answer change (ADR-104).

## Risks

- The tags field is persisted in the index, so the tier/facet ships with a
  store format bump; the byte-parity gate (store == fresh build, worker-count
  invariant) is the tripwire and must be re-proven, not assumed, across the
  bump.

## Related Decisions

- RAC-KWY7886GSEE5

## Related Roadmaps

- single-node-scale-residuals
- warm-by-default
