# Index Report

Execution record for `rust/INDEX-PLAN.md` (roadmap:native-derived-index,
RAC-KXBE6DEDTCYA) on branch `claude/native-derived-index-plan-58s5mq`
(from the head of `claude/rac-engine-heal`): the derived-index cache and
persistent store stack — ADR-099, 103, 104, 105, 106, 107, 108, 112 —
ported to `rac-engine`/`rac-mcp` byte-parity against the frozen Python
oracle (`.venv-oracle/bin/rac`, `0.1.dev50+g21c8be403`; `src/` verified
byte-identical to the branch head; the Python tree was never modified,
ADR-063 unchanged). This closes the maintainer's recorded precondition
for the ADR-063 flip; the flip decision itself is NOT taken here.

## Commit list

| batch | commit | subject |
| --- | --- | --- |
| P0 | `64e2f13` | docs(decisions): record native index workspace dependencies — ADR-114 |
| P0 | `65735fe` | test(engine): pin index-store contracts, format spec, and oracle golden vectors |
| P0 | `9e1747d` | feat(parity): add engine-run cache warming and the index cache-state smoke suite |
| P0 | `9100597` | docs(decisions): correct ADR-114 — rayon is an existing workspace dependency |
| B1 | `a5ac586` | feat(engine): port rac index — the plain-walk inventory |
| B2 | `5893e8f` | feat(engine): port the index codec and memory-mapped store |
| B3 | `6eb0c5e` | feat(engine): serve rac find from the persistent store |
| B4 | `039fee5` | feat(engine): port incremental validate with the .vseg row store |
| B5 | `f98a1c4` | feat(engine): port the parallel cold build |
| B6 | `ccf4584` | feat(engine): port serving freshness behind rac-mcp |
| B7 | (this commit) | perf addendum, this report, final verification |

Durable contracts: `rust/spec/index-store-format.md` (byte-level store
spec) and `rust/spec/index-contracts.json` (per-module briefs). Golden
vectors: `rust/spec/gen_vectors_index.py` →
`rac-engine/tests/vectors/index_store.json` (oracle-written store
bytes over two pinned fixture corpora, all 12 segments raw, plus
`.vseg`/`.fseg` codec vectors and the manifest root-key probes).

## Store byte-identity (the chosen parity surface)

The roadmap's format-may-differ escape hatch was **not** needed: the
native writer is byte-identical to the oracle's store.

- Golden vectors: every segment of both fixture corpora byte-equal
  (`index_store_vectors.rs`, raw-hex compare, regenerated after every
  corpus-shifting commit).
- Live corpus: an oracle-written store and a native-written store over
  the working tree's `rac/` — `diff -r` clean across all 12 segments,
  matching corpus hash and marker (`rac-engine/examples/store_write.rs`
  is the referee helper).
- Cross-engine from the CLI: parity cases capture
  `cache/store/**` + the marker after cold, warm, stale, and
  forced-parallel runs — the SETS and BYTES must match between the
  oracle's cache tree and the native one, and do (`b3-*-capture`,
  `b5-find-cold-parallel-build-capture`).
- Worker invariance: per-segment hashes equal at 1 and 4 workers and
  equal to the serial floor (`parallel_build.rs` test).

## Referee battery (green after every batch, cache-on AND cache-off)

- CLI suite 130/130; closure suite 391/391; retrieve suite 44/44 —
  unchanged, `RAC_NO_CACHE=1` base env as always.
- Index suite (`rust/parity-cases-index.json`): 45 cases — P0
  cache-state smoke (13), B1 `rac index` (17), B3 find/store (8),
  B4 incremental validate (6), B5 parallel build (1) — every case
  proven oracle-vs-oracle before its port landed, then
  oracle-vs-rust.
- MCP: 56/56 (primary) and 76/76 (six-tool oracle) no-cache;
  **cache-on 52/52 and 71/71** (`mcp_parity.py --cache-on`;
  duplicate-token cases excluded, see ledger entry 2).
- Mutation-sequence referee (`rust/tools/mcp_mutation_referee.py`):
  both servers cache-on over one shared corpus, 15 tool calls
  interleaved with edits, adds, deletes (including a duplicate-alias
  delete and a double mutation): all frames byte-identical.
- Harness growth (P0/B4): `engine-run` sandbox setup step (per-side
  cache warming under the case env) and `remove` (delete/rename
  staleness); existing suites re-proven oracle-vs-oracle after each
  harness change.

## Cache-state differential matrix

Cold, warm, stale (edit/add/delete/rename), bypassed
(`--no-cache` / `RAC_NO_CACHE`), verify, corrupt-segment,
truncated-header, unwritable-cache-dir, config-change invalidation,
top-level root keys — for `find`, `validate`, and the MCP server, each
byte-compared against the oracle in the same state. Native
warm == cold additionally pinned in cargo tests over five queries per
fixture corpus, including duplicate-token queries.

## Divergence ledger

1. **S5 accepted miss** (ADR-105/112). An in-place rewrite preserving
   both size and mtime_ns is invisible to the stat rung. Pinned as-is,
   not fixed: the native engine reproduces the stale reuse, `--verify`
   (the content-confirm floor) catches it, and the verify pass
   self-heals the store. Confirmed behavior-identical against the
   oracle by direct experiment; cargo test
   `incremental_validate::s5_...` pins it.
2. **Duplicate-token df (oracle defect, PORT-CONTRACT.d/10 §0a).** The
   oracle's warm search dedups a repeated query term's document
   frequency where its own cold walk counts per occurrence — an
   ADR-112 violation recorded during the spike. The native engine
   keeps **warm == cold** (per-occurrence df on both paths), so for
   this input class native-warm intentionally diverges from
   oracle-warm. Duplicate-token cases are excluded from cache-on
   referee runs and pinned natively instead
   (`index_store_vectors.rs` warm==cold over `"widget widget"` etc.).
3. **inotify deferred (ADR-114).** The tracker's fastest rung is the
   stat-manifest scan; `mode()` is always `"stat"`. Behavior-neutral
   by construction — the oracle only ever trusted inotify to assert
   *clean* — and worth ~1 ms/call at live-corpus scale (PERF-REPORT
   addendum). The ladder seam remains for a later decision.
4. **`retrieve_grounding` under the tracker walks fresh.** The
   native six-tool server serves retrieve by fresh walk in both cache
   modes (byte-neutral either way; cache-on 71/71 against the
   six-tool oracle confirms). Serving it from the read-model is a
   latency follow-up, not a parity item.
5. **Snapshot-arm resolution tag asymmetry (oracle-faithful).** The
   oracle resolves `get_artifact`/`get_related` over the mapped base's
   identity rows (tags present) but over the delta snapshot's
   tag-elided `identity_entries` projection — observable only inside a
   mutation window. Mirrored exactly; the mutation referee pins both
   arms.
6. **Unknown-tool calls freshen the tracker.** The native server
   resolves the read-model once per `tools/call` before dispatch; the
   oracle freshens inside each known tool. Latency-only, no wire
   bytes.

## RAC_TIMING scorecard

`rac-timing:` lines (stderr-only, env-gated, never a parity surface)
ported on both cold-build paths with the oracle's exact shape:
`build_parse_ms/build_derive_ms/build_write_ms/workers/files` on the
cache cold miss and the tracker cold start, and
`detect_ms/recompute_ms/files_changed` on incremental validate.

P0 extends that opt-in surface with content-free operation records:

```text
rac-timing: op=<stable-name> duration_ms=<milliseconds> <numeric counters...>
```

The records remain absent by default and stderr-only. They never include a
path, query, identifier, tag, document field, or response content. The stable
operation names are:

- `cache.discovery_stat`, `cache.corpus_hash`, `cache.manifest_write`,
  `cache.store_open`, `cache.cold_build`, and `cache.store_write`;
- `store.encode`, `store.segment_write`, and `store.segment_sync`;
- `search.query_tokenize`, `search.postings_decode`,
  `search.candidate_merge`, `search.row_decode`, `search.row_tokenize`,
  `search.matching`, `search.bm25f`, `search.rank_fusion`,
  `search.final_sort`, and `search.response_projection`;
- `git.recency_join` and `cli.response_serialize`;
- `grounding.search` and `grounding.projections`;
- `graph.view_build` and `graph.lookup`;
- `stat.discovery` and `stat.metadata`;
- `tracker.detect`, `tracker.recompute`, `mcp.dispatch`, and
  `mcp.response_serialize`.

`tools/perf.py` now exercises exact-ID, rare, common, no-match, multi-term,
and duplicate-term queries across no-cache, cold-cache, and warm-cache modes.
It records p50/p95/p99, match count, mapped-index bytes, peak RSS, and one
phase trace per query. Synthetic corpora are copied outside Git by default so
the published out-of-Git case is reproducible; `--contexts inside-git` makes
the deliberately expensive Git-recency case explicit.

### P0 release baseline

The first release-profile matrix ran on this Apple Silicon host against 5,000
generated files in `/private/tmp` (outside Git), five measured runs per mode.
It reproduced the published no-cache scale: common-term p50 was 576 ms and
multi-term p50 was 666 ms, bracketing the recorded 647 ms scenario. Warm
no-match was 49.7 ms p50 / 71.7 ms p95, close to the published 43 ms single
warm observation while making the run-count distinction explicit.

Selectivity changes the picture materially:

- warm no-match: 49.7 ms p50 / 71.7 ms p95, with no row decoding;
- warm common-term (4,990 matches): 404 ms p50 / 482 ms p95;
- warm multi-term (4,979 matches): 912 ms p50 / 1,253 ms p95;
- warm duplicate-term (4,990 matches): 738 ms p50 / 992 ms p95;
- cold-cache queries: 1.3–2.4 seconds p50, including store construction;
- mapped index size: 27,652,190 bytes; measured peak RSS: 21.7 MiB.

One diagnostic common-term trace attributed 118 ms to row tokenisation and
99 ms to final sort. The multi-term trace attributed 446 ms to row
tokenisation and 501 ms to final sort. The no-match trace spent its useful
time in freshness: discovery 21 ms, corpus-hash recomposition 12 ms, and
manifest write 5 ms. These are phase observations, not independent benchmark
samples; the p50/p95 figures above remain the comparison surface.

This validates the seven-workstream order: P1 owns the redundant warm
freshness work, P2 the per-result Git join,
P3/P5 read-model consumers, P4 candidate reconstruction/tokenisation/sort, P6
incremental recompute, and P7 cold encode/write construction. The 10k matrix
remains the product-gate run required before an optimisation claims completion.

### P1 freshness result

P1 removes two unchanged-corpus costs without weakening freshness: corpus-hash
recomposition now consumes the complete scan-order manifest directly instead
of walking the directory a second time, and an identical persisted manifest is
not rewritten. Missing/corrupt manifests and `--verify` still take the original
content-confirming and persistence path.

On the same release-profile 5,000-file, outside-Git matrix, warm no-match fell
from 49.7 ms to 25.7 ms p50 and from 71.7 ms to 27.8 ms p95: 48% and 61%
reductions respectively. The diagnostic trace moved corpus-hash work from about
12 ms to 3.0 ms and unchanged manifest persistence from about 5 ms to 0.05 ms.
Mapped-index bytes remained 27,652,190 and peak RSS was effectively unchanged
(21.7 MiB before, 21.5 MiB after).

Broad-query timings remain workload- and host-load-sensitive; their phase
traces still identify row tokenisation and final sorting as the next search
hotspots. P1 therefore claims the selective unchanged-corpus result only.

### P2 Git-recency result

P2 replaces the per-result `git log -1 --format=%cI -- <path>` loop with a
bounded batched history traversal. Each batch asks Git for newest-first `%cI`
commit stamps plus NUL-delimited changed paths; the first stamp observed for a
path is the same value the single-path command returned. Input order,
duplicates, untracked files, paths outside the work tree, timezone offsets,
and all-null non-repository behavior remain pinned.

On a 5,000-file corpus committed in a local Git repository, the 4,990-match
common-term query spent 34,104 ms in `git.recency_join` before P2 and 316 ms
after P2: a 108x reduction. Like-for-like total warm wall time fell from 34.49
seconds to 1.09 seconds. The before and after 3,368,660-byte JSON responses had
the same SHA-256 (`edb0f2a899c4b9ebf3b3f89b41443d286eea507c3dea195a95b3520fa0cc338a`).

The five-run after-matrix measured warm p50 of 623 ms for common-term, 660 ms
for multi-term, 632 ms for duplicate-term, and 26.2 ms for no-match. The
corresponding diagnostic Git joins were 293–320 ms for the broad result sets
and about 13 ms for one-result queries. P2 therefore removes the subprocess
explosion; P4 still owns broad candidate reconstruction, row tokenisation, and
sorting.

### P3 read-model grounding result

P3 moves MCP `retrieve_grounding` onto the tracker model already freshened for
the call. The mapped arm searches postings, reads governing-scope and
relationship projections only when requested, resolves successors through the
path map, and derives lifecycle status from the persisted section row. The
mutation-window arm consumes the same derived snapshot. Neither arm walks or
reparses the corpus; disk reads are limited to final selected excerpts and a
safe fallback when a requested model row cannot be decoded. Unknown tool names
are rejected before tracker freshening.

One equivalence test now replays every recorded grounding vector through fresh,
snapshot, and mapped arms and compares the complete pre-serialization payload.
It covers empty and broad queries, scope paths, supersession chains,
`live_only`, Unicode, CRLF, and budget/top-k variants.

On the release-profile 5,000-file outside-Git corpus, an exact-ID grounding call
fell from 430–573 ms warm p50 on the P4 parent to 23–28 ms across P3 runs. A
broad `markdown` call fell from a 395 ms earlier parent run to 271 ms p50 in the
corresponding P3 run. Payload SHA-256 values were identical before and after:
`7fad45dae749bf8f6f1a98f07cd5460d8b7f8987498f8ef8dbc5e7fc67f441e9`
for exact-ID and
`865918b0f90a0918facfe4cc27200b9d402b365c492c40ff0e02222d221da3df`
for broad grounding. The exact-ID result is below the programme's initial
50 ms p95 target in all seven measured warm samples (22.6–31.0 ms across two
P3 runs); broad queries remain governed by P4's matched-row work.

### P4 search-hotpath result

P4 makes the store-served search plan reflect RAC's existing AND contract.
Distinct per-term posting sets are intersected smallest-first instead of
unioned, so an exact ID no longer reconstructs every document containing the
common `RAC` prefix. Store rows reuse their persisted flat field tokens;
section text is tokenized only far enough to recover a winning heading/body
snippet. Ranking uses index-aligned vectors instead of path-keyed hash maps,
and the rounded fused sort key is computed once per result rather than once
per comparison.

On the same 5,000-file matrices, exact-ID warm p50 fell from the immediately
preceding inside-Git 173 ms to 39.9 ms (77%) as its candidate set dropped from
5,000 rows to one. Inside-Git broad p50 moved from 623 to 482 ms for
common-term, 660 to 497 ms for multi-term, and 632 to 489 ms for the duplicate
query (23–25%). Outside Git, common-term warm p50 was 205 ms versus the P1/P2
search-plan baseline of 391 ms (48%); exact-ID was 36.8 ms.

The common-term diagnostic now attributes about 72 ms to persisted-token row
reconstruction and 4.2 ms to final sorting, versus the P0 observations of 118
ms and 99 ms. The retained P2 and final P4 3,368,660-byte inside-Git responses
remain byte-identical with SHA-256
`edb0f2a899c4b9ebf3b3f89b41443d286eea507c3dea195a95b3520fa0cc338a`.

### P5 indexed-graph result

P5 adds a server-lifetime `GraphView` keyed by the freshness tracker's logical
serving generation. The complete replacement view is built before publication
and indexes aliases, identities, outgoing edges, incoming resolved targets,
and docid-based adjacency. Unchanged calls reuse it; any add, edit, rename, or
delete that changes the served corpus advances the generation and replaces the
view. The persistent store format is unchanged.

The mutation test proves two unchanged calls build once and return identical
bytes, then adding a relationship-bearing artifact advances the generation,
builds exactly one replacement, and returns the new incoming edge. The complete
MCP parity basket is 76/76 byte-identical against the P4/P3 parent, including
depth 0/1/2/3/5, duplicate IDs, missing IDs, truncation, and mixed artifact
types. HTTP body/status/audit parity also passes.

On the 5,000-file outside-Git corpus, repeated depth-1 `get_related` warm p50
fell from 28.4 ms to 17.2 ms (40%), with the same payload SHA-256
`399e537b21b3674b1a3a676d8c1b79a441f34ebd752ece26f611f1990edda550`.

At 100,000 artifacts and 399,905 relationships, the parent took 587.3 ms warm
p50 and P5 took 330.7 ms, with byte-identical payload SHA-256
`a800aa319647bf561a2216f555a8964fa53424a7940fca5722fb4627615fc255`.
The indexed graph lookup itself took 0.039-0.060 ms after construction for an
artifact with six incoming and four outgoing edges; the remaining 324 ms in the
observed call was the unchanged-corpus stat scan. P5 therefore meets the 30 ms
graph-operation budget, but the end-to-end 100k MCP call does not: freshness is
now the measured limiting phase.

The one-time 100k graph build took 721-806 ms. Its estimated owned payload was
140,130,245 bytes and observed resident growth after an already-warm summary
was 159,264 KiB. This is bounded and approximately linear in identities and
edges, but substantial enough that persistent adjacency is not justified as an
additional co-resident copy; a later store-native borrowed view should replace,
not duplicate, this structure if 100k server memory becomes a product gate.

### P5.5 serving-freshness result

P5.5 activates ADR-105's synchronous clean accelerator on Linux. The tracker
installs inotify watches before its initial scan and drains the non-blocking
kernel queue at every request boundary. Only a completely drained empty queue
under a complete watch set skips detection. Any event, overflow, watch failure,
or read failure rebuilds the watch set and runs the authoritative stat/content
differ; an event racing with that scan forces another bracketed scan. The
active rung and whether a scan occurred are timing-visible.

macOS FSEvents was rejected as a clean oracle after both callback flushes and
the system journal watermark missed a pinned immediately completed write. The
native engine therefore retains stat correctness on macOS and parallelizes its
fallback: root-sharded discovery preserves the final component-wise order, and
metadata/content probes collect through an indexed parallel iterator that
preserves manifest order.

On the same macOS 100,000-artifact corpus, five post-warm `get_related` calls
measured a fallback p50 of 199.9 ms (195.2-278.2 ms observed), down from P5's
approximately 324 ms limiting scan. A representative p50-near trace spent
96.1 ms in discovery and 68.3 ms in parallel metadata, while indexed graph
lookup remained 0.068 ms. This is a 38% safe-fallback improvement, not a claim
that macOS warm latency is flat. At 5k the fallback stayed within the same
small-corpus band (19.2 ms p50 observed versus P5's 17.2 ms), so no 5k win is
claimed. Linux clean latency is gated by the inotify integration tests and
must be benchmarked on the CI/reference Linux host.

## Performance

See the `PERF-REPORT.md` warm-path addendum. Headline (5k synthetic
corpus, outside git): warm `find --json` **43 ms** vs the roadmap's
recorded ~21.6 s floor (which was recency-join-dominated; the honest
out-of-git fresh walk is 647 ms — the cache still buys 15×); warm
`validate` 92 ms vs 150 ms fresh; warm MCP `get_summary` ~1.8 ms/call.

## Evidence for the ADR-063 flip (taken separately)

- The full recorded index architecture (ADR-099–112) now exists in the
  Rust engine, proven byte-identical at the store level (stronger than
  the read-model-contract fallback the roadmap allowed) and at every
  covered CLI/MCP surface, cache-on and cache-off, through mutation
  windows.
- The gap list is unchanged from the closure report: `explorer`
  (fenced delivery surface), `ingest` (markitdown sidecar by ADR-072).
  `index` — the last unported non-fenced verb — is closed by B1.
- The oracle keeps two recorded defects the native engine does not
  reproduce (ledger 2; the closure report's oracle-crash class); both
  are documented divergences in the native engine's favor.

## Final verification — clean rebuild, batteries twice

From one `cargo clean` (full rebuild): see the tail of this report's
landing commit message for the recorded runs — build + clippy
`-D warnings` clean; `cargo test --release` (24 binaries) twice;
CLI/closure/retrieve/index parity twice; MCP no-cache and cache-on
suites twice; mutation referee twice — all green, scoreboards
byte-identical between runs.
