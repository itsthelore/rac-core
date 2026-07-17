---
schema_version: 1
id: RAC-KXBE6DEDTCYA
type: roadmap
---
# Native Derived Index — Cache and Persistent Store in the Rust Engine

## Status

Planned

Maintainer-sponsored follow-up to the native-engine spike, unscheduled.
The spike shipped its v0 posture deliberately cache-free — a fresh
deterministic walk per invocation — and left the entire derived-index
architecture (ADR-099, ADR-103, ADR-104, ADR-105, ADR-106, ADR-107,
ADR-108, ADR-112) unported. This item ports it.

Sequencing gate, recorded as maintainer intent: **ADR-063 is not
flipped or superseded until this item lands.** The Python engine
remains the authoritative implementation, and the spike branch remains
evidence-gathering, until the Rust engine carries the derived-index
cache and persistent store and proves them against the same
byte-parity referees the spike established. Completing this item does
not itself flip ADR-063 — it satisfies the maintainer's stated
precondition for taking that decision.

## Outcomes

- The Rust engine serves reads through the unified derived read-model
  (ADR-103) backed by the persistent memory-mapped index store
  (ADR-104), with the cache on by default and stat-proxy freshness as
  the floor (ADR-112), matching the recorded architecture the Python
  engine implements today.
- Warm-path search and retrieval stop paying the fresh-walk tax. The
  motivating measurement (heal verification, 2026-07-12): uncached
  `find --json` over a 5,000-file synthetic corpus takes ~21.6 s in the
  Rust engine — the only covered workload that is slow in absolute
  terms, and precisely the workload the derived-index decisions exist
  to serve.
- Byte-parity is preserved: the cache is contractually byte-neutral, so
  the existing CLI, retrieve, and MCP parity suites — plus
  cache-on/cache-off differential runs — referee the port exactly as
  they refereed the spike.

## Initiatives

- Port the derived-index cache (ADR-099) and the unified derived
  read-model (ADR-103) into `rac-engine`, keeping classification,
  validation, and read shaping on the existing pinned code paths.
- Port the persistent memory-mapped index store (ADR-104) with
  event-sourced freshness (ADR-105) and incremental directory
  validation (ADR-106).
- Port the parallel cold build (ADR-107) with the
  term-range-partitioned merge (ADR-108), holding the existing
  order-preserving rayon posture the spike proved byte-neutral.
- Extend the parity harness with cache-state matrices: cold vs warm,
  cache-on vs `--no-cache`, and staleness-transition cases, each
  byte-compared against the oracle's corresponding mode.
- Re-run the performance matrix against the recorded Python baselines
  and the spike's fresh-walk numbers; the report updates
  `rust/PERF-REPORT.md` with warm-path figures.

## Constraints

- ADR-063 remains in force for the duration: the Python tree stays the
  authoritative engine and the frozen parity oracle; this work does not
  modify it.
- Byte-parity is the gate, unchanged from the spike: identical stdout
  bytes and exit codes on every covered command, cache on or off; any
  divergence is enumerated with root cause.
- The cache must be byte-neutral by construction — a warm read returns
  the same bytes as a cold walk, or the cache is wrong.
- No new workspace dependencies without a recorded decision.

## Success Measures

- All existing parity suites green with the cache enabled, plus a
  cache-state differential matrix green (cold, warm, stale, bypassed).
- Warm `find` / `retrieve` on the 5k synthetic corpus drops from the
  measured ~21.6 s fresh-walk floor to within the ADR-107 budget line,
  with the number recorded beside the methodology in
  `rust/PERF-REPORT.md`.
- The maintainer has the evidence needed to take the ADR-063 flip
  decision; the decision itself is recorded separately if and when it
  is taken.

## Assumptions

- The oracle's cache behavior is contractually byte-neutral (verified
  during the spike), so cache-on parity runs are decidable mechanically.
- The recorded index architecture (ADR-099 through ADR-112) is
  implementable in Rust without semantic deviation; where the mmap
  store's on-disk format needs to differ from the Python store's, the
  read-model contract, not the file format, is the parity surface.

## Risks

- Cache staleness semantics diverge subtly from the oracle's
  (stat-proxy edge cases, event ordering), producing rare warm-path
  divergences; mitigated by the cache-state differential matrix and by
  pinning every divergence found as a regression case.
- The persistent store introduces platform-dependent behavior (mmap,
  file locking) the byte-parity harness cannot see; mitigated by
  keeping the store behind the read-model contract and testing
  cold/warm equivalence on every suite run.
- Scope creep into the flip decision itself; mitigated by this
  artifact's explicit boundary — landing the index satisfies the
  precondition, and the flip remains a separate recorded decision.

## Related Decisions

- ADR-063
- ADR-099
- ADR-103
- ADR-104
- ADR-105
- ADR-106
- ADR-107
- ADR-108
- ADR-112

## Related Roadmaps

- native-engine-spike
- artifact-specs-extraction
- conformance-fixtures
