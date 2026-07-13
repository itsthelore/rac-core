# Index Plan — native derived index (roadmap:native-derived-index)

Port the derived-index cache and persistent store stack (ADR-099, 103,
104, 105, 106, 107, 108, 112) from the frozen Python oracle to
`rac-engine`, satisfying the maintainer's recorded precondition for the
ADR-063 flip (RAC-KXBE6DEDTCYA). Scope is the oracle's actual stack
(~4,000 LOC, surveyed 2026-07-13): `services/index.py` (the `rac index`
command), `derived_cache.py`, `index_format.py`, `index_store.py`,
`freshness.py`, `parallel_build.py`, `parallel_merge.py`, plus the
cache seams in `cli.py` (`find`, `validate`, `mcp`) — `index` and
`resolve` never consume the cache; only `find`, `validate`, and the
MCP server do.

## Ground rules

- All existing suites (CLI 130 + closure 391, retrieve 44, MCP 56/76)
  stay green after every commit; the Python tree is never modified
  (ADR-063). New cases land in `parity-cases-index.json`.
- The cache is byte-neutral by contract: a warm read returns the bytes
  of a cold walk, or the cache is wrong. Every batch referees
  cache-on AND cache-off.
- **Store byte-identity is the chosen parity surface**: the oracle's
  on-disk format is fully deterministic (RACIDX01 magic, LE structs,
  sorted termdict/aliasmap/pathmap, walk-order docids,
  content-addressed dirs), so the Rust store must be byte-identical to
  the oracle's for the same corpus — a mechanical referee (hash the
  segment dirs) and free interop. The roadmap's format-may-differ
  escape hatch is a fallback, invoked only with a recorded reason.
- Commits: `feat(engine): ... [roadmap:native-derived-index]`;
  harness work `feat(parity)`.
- **Dependency gate, decided before coding**: ADR-104 mandates mmap
  and the stack wants inotify. Rust needs `memmap2` (and optionally
  `notify`/`inotify`) — new workspace dependencies require a recorded
  decision (one small ADR at session start, or the plain-`read()`
  fallback for v0 with mmap deferred; inotify is skippable
  behavior-neutrally since it only ever asserts *clean*).

## Batches

- **P0 — contracts and golden vectors**: per-module briefs
  (`spec/index-contracts.json`) probed from the oracle; a durable
  store-format spec (`spec/index-store-format.md`: framing, all 12
  segments, vseg/fseg, marker JSON, corpus hash); oracle-generated
  golden fixtures — store dirs built by the oracle over pinned fixture
  corpora, committed as segment hashes + small raw segments for codec
  vectors. Harness: cache-state plumbing (per-engine `RAC_CACHE_DIR`
  into the sandbox, a `pre_run` setup step to warm a cache with the
  same engine, `RAC_NO_CACHE` env cases); prove existing suites
  oracle-vs-oracle after any harness change.
- **B1 — `rac index` command**: plain-walk port (no cache), human +
  JSON (identity-only contract: aliases in, search_sections /
  inbound_count / tags out), `--top-level`, exit codes. Closes the
  last unported non-fenced CLI verb.
- **B2 — codec and store**: `index_format` (Writer/Reader, segment
  framing, indexed segments) against golden vectors; `index_store`
  writer + reader (12 segments, fail-closed open gates: magic,
  versions, scoring fingerprint, hash echo, truncation);
  corpus-hash + marker. Referee: store byte-identity vs the oracle on
  every fixture corpus and the live corpus.
- **B3 — read-model + `find` seam**: `derived_cache` (DerivedIndex,
  ScopeRow/governing_decisions reuse from retrieve.rs, load_or_build,
  default_cache_dir ladder), `ReadModelView`/Fold over the mmap
  reader, BM25F fed from store integers with the pinned float order;
  `find --cache/--no-cache` + `RAC_NO_CACHE`/`RAC_CACHE_DIR`.
  Referee: cache-state matrix (cold, warm, stale, bypassed) byte-
  compared vs the oracle in the same state, plus warm==cold on every
  covered find case.
- **B4 — incremental validate + manifests**: `.vseg` store,
  `validate --cache/--no-cache/--verify` with row reuse and
  reassembly in walk order; `.fseg` stat-proxy manifests
  (size/mtime_ns gate re-reads, content_hash is truth; the S5
  size+mtime-preserving miss is the oracle's accepted behavior — pin
  it, don't fix it). Referee: matrix as B3 over validate, including
  rename-reuse and `--verify` floor cases.
- **B5 — parallel cold build**: rayon port of the fragment fan-out +
  cross-doc merge (no pickling boundary; keep the spike's
  order-preserving posture). Referee: store bytes invariant across
  worker counts (1 vs N) and equal to the serial build; the
  RAC_PARALLEL_BUILD_MIN_FILES threshold and fault→serial-floor
  degrade pinned.
- **B6 — serving freshness (MCP)**: `FreshnessTracker` (base + delta,
  compaction threshold `max(10_000, base//100)`, RSS shed,
  full-rehash floor) behind `rac-mcp`; the stat_scan differ shared
  with B4. inotify per the P0 dependency decision — if skipped, the
  stat_scan rung is the resting differ (behavior-neutral). Referee:
  MCP suites cache-on; a mutation script (edit/add/delete between
  tool calls) byte-compared vs the oracle server in the same
  sequence.
- **B7 — perf + report**: re-run the perf matrix (5k synthetic corpus;
  warm find/retrieve vs the recorded ~21.6 s fresh-walk floor and the
  Python baselines); update `rust/PERF-REPORT.md`; write
  `rust/INDEX-REPORT.md`; double clean-rebuild verification of every
  suite cache-on and cache-off.

## Definition of done

- All existing suites green cache-on AND cache-off, twice, from a
  clean rebuild; `parity-cases-index.json` green; workspace clippy
  `-D warnings`; `cargo test` green.
- Store byte-identity vs the oracle proven on fixture corpora and the
  live corpus; worker-count invariance proven.
- Cache-state differential matrix (cold/warm/stale/bypassed/verify)
  green for `find`, `validate`, and MCP.
- Warm-path numbers recorded beside methodology in `PERF-REPORT.md`;
  `INDEX-REPORT.md` carries the divergence ledger and the evidence
  the maintainer needs for the ADR-063 flip decision (taken
  separately, per the roadmap).

## Known hazards (from the survey)

- BM25F float summation order must come off store integers exactly as
  off the walk (field order `id,title,path,heading,body,tags` is
  asserted in the oracle) — any drift breaks warm==cold.
- The oracle asserts read-model equality against a *fresh build*,
  never a self round-trip; the Rust tests must do the same.
- Temp-file names embed pid/random bytes (never mapped payload);
  `RAC_TIMING` writes stderr only — neither is a parity surface.
- Cache failure of any kind degrades silently to a fresh build
  ("latency only"); the degrade paths need explicit negative cases
  (corrupt segment, truncation, version bump, unwritable dir, homeless
  fallback ladder).
- `portfolio.seg` is the one JSON-in-binary blob; everything else is
  structs — keep it that way.
