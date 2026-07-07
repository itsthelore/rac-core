---
schema_version: 1
id: RAC-KWSMFKEE9EQW
type: roadmap
---
# Single-Node Scale Residuals

## Status

Planned

Unscheduled — captures what the `rebuild-scale` exercise deliberately left
on the table, each residual already named in an accepted decision record.
This is the "needs a further decision or a further bundle" list, split from
the delivered work so the delivered claims stay auditable.

## Context

The rebuild-scale roadmap landed five Movement-B bundles (ADR-103 through
ADR-107): the unified derived read-model, the persistent memory-mapped
index store, event-sourced serving freshness, incremental validation, and
the parallel cold build. The operational serving paths became
changeset-bound rather than corpus-bound, and each bundle recorded the
walls it did not move. This item collects those residuals as future work
so they are scheduled deliberately rather than rediscovered.

## Outcomes

- The cold full build approaches its ~2 minutes per million artifacts
  budget (ADR-107 records the honest miss: ~15-19 minutes per million as
  built, with parallel parse at 1.8x and a serial derive/write tail).
- Search cost on a corpus with uncompacted changes matches the compacted
  fast path, and the summary tool becomes change-bound rather than
  corpus-bound on change.
- The relationships subsystem gains the same incremental treatment
  validation received.

## Initiatives

- Term-range-partitioned parallel merge and STREAMING segment writes for
  the cold build: workers emit postings-run fragments and compact rows
  rather than parsed products, and segments flush incrementally instead of
  materializing the whole derived model in memory first. The final 1M
  measurement makes this the top residual: the build was OOM-killed at
  15.9 GiB on the 15 GiB node — the store serves within budget at every
  size it can be built, but at one million artifacts it cannot be built on
  the reference node as shipped (the cold path also runs ~5.7x over the
  120 s/1M budget where it completes).
- Postings-served search over a non-empty delta window: fold delta
  postings into candidate discovery so edited corpora keep the fast path
  before compaction (the v1 scope note in the ADR-104 postings
  subsection).
- Change-bound summary derivation: incremental portfolio-summary inputs
  so `get_summary` stops re-deriving over the whole corpus on change (the
  stated O(N)-on-change residual in ADR-105's record).
- Incremental relationships validation: build the declared-reference
  index and transition-class recompute that ADR-106 records as
  design-of-record for the relationships subsystem.
- A public scope-matching seam so the read-model composer stops importing
  the two private scope matchers (the coupling ADR-103's implementation
  noted).
- Changed-set detection below the stat floor for one-shot CLI runs: the
  1M measurement shows recompute flat at 3.0 s for a 1,000-file changeset
  but stat detection at 17.9 s — the O(files) slope ADR-106 records fails
  the 5 s gate past a few hundred thousand files without a service mode
  or a git/fsmonitor fast path; that fast path is the initiative.
- Graph-read and per-match constants: get_related sits 2 ms over the
  30 ms p50 budget at 100k (the Theta(edges) incoming-scan), and match
  scoring costs ~1.6 ms per matching document against legacy's ~3 ms/match
  resident-vector scan only at moderate sizes — batch row reconstruction
  is the lever for both.
- Broad-query streaming: revisit whether the full-ranked-order contract
  can admit a bounded-heap evaluation without a byte break — a decision,
  not an optimization, since the current contract makes it un-prunable.

## Success Measures

- The scalecorpus gate's cold-build budget passes at the top measured
  corpus size, or the budget is revised by decision with the measured
  ceiling recorded.
- Warm search latency on a corpus with a non-empty delta window is within
  2x of the compacted path at every measured size.
- A 1,000-file changeset re-validates relationships in under 5 seconds,
  corpus-size-independent, with byte-identical output.

## Assumptions

- The reference node remains the 4-core, 15 GiB single node; no sharding
  and no external services remain hard scope lines.
- The frozen examiner and the byte-parity law continue to gate every
  change.

## Risks

- The parallel merge touches global derivations (inbound counts,
  resolution, portfolio) whose byte-parity is the most fragile in the
  system; ADR-107 deferred it for exactly that reason. It should ship as
  its own bundle with parity tests per mutation class.

## Related Decisions

- RAC-KWS4Y9KCTD90
- RAC-KWS7QCT10Q5A
- RAC-KWSDFYW7PCW6
- RAC-KWSH9J2S7QB1
- RAC-KWSJZJ30EN1J

## Related Roadmaps

- rebuild-scale
