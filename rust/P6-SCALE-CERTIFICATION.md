# P6.7 Scale Certification

Date: 2026-07-22

Decision: ADR-119

Result: **preview remains non-default**

## Purpose

This certification compares the existing snapshot freshness path with the
ADR-119 base-plus-delta preview. It measures the complete freshness lifecycle,
not an isolated parser or index microbenchmark: cold establishment, unchanged
warm reads, one-file edit/add/delete/rename publication, and threshold
compaction.

The benchmark is `rac-engine/examples/p6_scale.rs`. It restores every corpus
mutation before exit and reports JSON with raw samples plus p50/p95 summaries.
It also reports the last parse count and overlay size so a fast result cannot
silently come from skipping freshness work.

## Adoption gates

The preview may become the default only when all of these are true:

1. Existing mutation referees remain byte-identical to fresh whole-corpus
   generation.
2. A one-file mutation parses one file and leaves one delta row.
3. At 5,000 files, warm p95 is at most 25 ms and mutation p95 is at most
   150 ms.
4. At 100,000 files, warm latency is at most 500 ms and each one-file mutation
   completes within 1,000 ms.
5. Cold establishment and threshold compaction are no more than 20% slower
   than the snapshot path at either corpus size.
6. Peak resident memory is recorded before cutover and fits the deployment
   budget; the preview deliberately retains parsed documents.

These are cutover gates, not claims that every operation should be independent
of corpus size. Manifest freshness scanning and exact global portfolio/search
reductions can remain corpus-linear, but they must fit the user-visible budget.

## Environment and method

- Apple silicon (`arm64`, T8103), macOS Darwin 27.0.0
- Rust 1.96.0, release build
- synthetic corpus from `rust/tools/gen_corpus.py`, seed 1234
- 5,000-file distributions: seven delta iterations; three snapshot iterations
- 100,000-file scale probe: one iteration per mode, so the reported value is a
  point estimate rather than a statistically meaningful p95
- cache directories were distinct per mode and run

Build and run:

```sh
cd rust
cargo build --release -p rac-engine --example p6_scale
target/release/examples/p6_scale snapshot CORPUS CACHE_DIR 7
target/release/examples/p6_scale delta CORPUS CACHE_DIR 7
```

For the required memory gate, run the same commands under macOS
`/usr/bin/time -l` and record `maximum resident set size`. This run did not
capture trustworthy peak RSS, so gate 6 is explicitly unresolved.

## Results

All durations are milliseconds.

### 5,000 files

| lifecycle operation | snapshot | delta preview | gate |
|---|---:|---:|---|
| cold | 1007.44 | 1873.85 | fail: +86.0% |
| warm p50 / p95 | 10.21 / 13.14 | 12.11 / 17.92 | pass |
| edit p50 / p95 | 390.53 / 571.71 | 52.14 / 90.22 | pass |
| add p50 / p95 | 400.01 / 854.64 | 56.60 / 60.22 | pass |
| delete p50 / p95 | 617.95 / 688.93 | 56.07 / 62.25 | pass |
| rename p50 / p95 | 431.24 / 508.68 | 53.50 / 61.15 | pass |
| threshold compaction | 932.95 | 932.13 | pass |

The 5,000-file target is achieved for warm and mutation latency. Each final
mutation parsed one file and left one delta row. Cold establishment fails the
cutover regression gate.

### 100,000 files

| lifecycle operation | snapshot | delta preview | gate |
|---|---:|---:|---|
| cold | 31585.06 | 54677.07 | fail: +73.1% |
| warm | 321.16 | 387.44 | pass |
| edit | 16859.92 | 3159.01 | fail |
| add | 13682.46 | 1801.63 | fail |
| delete | 15203.05 | 1709.89 | fail |
| rename | 14607.75 | 1881.99 | fail |
| threshold compaction | 28406.54 | 47100.41 | fail: +65.8% |

The preview reduces one-file mutation latency by roughly 4.8x to 8.9x versus
snapshot rebuilds, and the final mutation still parses one file with one delta
row. However, 1.7-3.2 seconds is not a satisfactory interactive publication
budget. Cold and compaction regressions are also too large for default use.

## Findings

Certification exposed and removed two avoidable costs:

- Cold preview construction previously staged every document through the
  cumulative overlay, producing quadratic work. Cold establishment now builds
  compact bases directly from the parsed corpus.
- Candidate completeness previously cloned all live documents merely to count
  them. `DeltaDocuments::live_len()` now computes exact cardinality from base,
  tombstones, replacements, and upserts without materialization.

The remaining 100,000-file mutation time is therefore not a full reparse:
instrumentation confirms one parsed file. It is publication/derivation work,
including exact corpus-global reductions identified in ADR-119 P6.5. The next
performance slice should profile those reductions and make their maintained
state incremental where exactness permits. Re-run this same certification
before changing the default constructor used by CLI or MCP.

## Verdict

P6's architecture and correctness work is complete, and it provides a clear
5,000-file interactive win. It is **not certified for default cutover** at
100,000 files. Keep `FreshnessTracker::new_delta_preview` explicit, retain the
snapshot production path, and treat the failed cold, mutation, compaction, and
memory gates as prerequisites for a future cutover decision.
