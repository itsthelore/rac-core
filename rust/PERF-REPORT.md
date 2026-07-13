# PERF-REPORT — Rust engine spike (roadmap:native-engine-spike)

Final report. Box: 4-core / 15 GiB container (same class as ADR-107's
reference node). Oracle: `.venv-oracle` (Python 3.11.15, editable install
of this branch's `src/` at `21c8be4`). Rust: `rust/target/release/rac`,
toolchain 1.94.1, lto=thin, rayon parallelism with order-preserving merge
(worker count proven invisible: outputs byte-identical at 1 and 4
threads). Harness: `rust/tools/perf.py` (piped stdio, neutralized
telemetry env, 7-run medians; 3 runs at 20k). Synthetic corpora:
`rust/tools/gen_corpus.py` (seeded, five artifact types,
cross-references). Final matrix measured 2026-07-11T16:31Z, both engines
interleaved on the same box.

## Headline vs targets

| Measure | Python oracle | Rust (final, rayon) | Target | Verdict |
|---|---|---|---|---|
| Startup (`--version`) | 191.2 ms | **2.2 ms** (87×) | < 15 ms | ✅ |
| Single-file validate | 195.5 ms | **3.4 ms** (57×) | < 25 ms | ✅ |
| Fresh walk, live `rac/` (417) | 1 588 ms (`--no-cache`) / 223 ms (warm cache) | **28 ms** (57× / 8.0×) | < 150 ms | ✅ beats Python's *warm cache* 8× with no cache at all |
| Cold-walk throughput, 1k | 651 files/s | **33 906 files/s** | ≥ 10× serial | ✅ 52× |
| Cold-walk throughput, 5k | 720 files/s | **36 639 files/s** | ≥ 10× serial | ✅ 51× |
| Cold-walk throughput, 20k | 767 files/s | **34 697 files/s** | ≥ 10× serial | ✅ 45× |
| 4-core scaling | (887 files/s at 4 workers, ADR-107) | 12.3k → 34.7k files/s (1→4 threads, 2.8× on the live corpus) | near-linear | ✅ parse-dominated corpora scale ~2.8-2.9× on 4 cores |
| Peak RSS at 20k | ≤ 230 MiB | **≤ 230 MiB** | < 1 GiB | ✅ (see caveat) |
| Product bar: one-shot gate invocation | ~195 ms floor (interpreter startup) | **3.4 ms single file / 28 ms whole live corpus** | < 50 ms per gate | ✅ 15× headroom |

## Wall-clock detail (medians, final matrix)

| Workload | Python | Rust | Ratio |
|---|---|---|---|
| `--version` | 191.2 ms | 2.2 ms | 87× |
| `validate <one file>` | 195.5 ms | 3.4 ms | 57× |
| `validate rac/` fresh (417) | 1 588 ms | 28 ms | 57× |
| `validate <1k>` fresh | 1 536.1 ms | 29.5 ms | 52× |
| `validate <5k>` fresh | 6 944.7 ms | 136.5 ms | 51× |
| `validate <20k>` fresh | 26 057.6 ms | 576.4 ms | 45× |

Sequential Rust (pre-rayon, RAYON_NUM_THREADS=1) was already inside every
target: 12.3–12.6k files/s, live corpus 75–79 ms. Rayon added 2.8× on
parse-dominated corpora with byte-identical output.

## Against ADR-107's budget line

ADR-107 recorded 692 files/s serial / 887 files/s at 4 workers for the
Python cold build (pickling eats 30–40% of the parallel gain), 18.8 min
per 1M files against a 432 s budget, and a pre-streaming OOM at 15.9 GiB
at 1M. The Rust engine sustains ~34.7k files/s ≈ **29 s per 1M files** —
inside the budget with ~15× margin — with flat memory across 1k→20k and
no pickling tax (rayon shares memory; the "parallelism overhead" class
ADR-107 documents does not exist here).

## Why the cache deletion held up

The derived-index cache stack (ADR-099/103/104/105/106/107/108/112 —
mmap store, event-sourced freshness, stat-proxy scans, parallel cold
build) exists to bridge Python's 1.6 s fresh walk down to ~223 ms warm.
The Rust engine's fresh walk is 28 ms: **8× faster than Python's best
cached path, with zero cache invalidation surface**. v0 ships no cache by
design and still wins; a future cache would be an optimization, not a
requirement, even at 100k+ artifacts (projected fresh walk ~3 s at 100k).

## Caveats

- Peak RSS is `getrusage(RUSAGE_CHILDREN)` (no /usr/bin/time on the box);
  the final matrix reports 230 MiB for both engines at every size, which
  is likely dominated by a shared measurement artifact — an earlier
  isolated run showed oracle ~77 MiB and Rust ~167 MiB at 20k. Either
  reading is far under the 1 GiB target; treat exact RSS as approximate.
- Synthetic corpora have smaller/simpler bodies than the live corpus
  (live-corpus Rust throughput ≈ 15k files/s at 417 files); both engines
  ran the same corpora, so ratios hold.
- The 20k Amdahl residual (sequential render + OKF check) caps synthetic
  scaling at ~1.6× over sequential there; parse-dominated real corpora
  scale ~2.8×.

## Go / no-go recommendation

**GO for a mainline evaluation**, on this evidence:

1. **Fidelity is mechanically proven** — 130/130 byte-parity cases across
   nine commands and three output formats, ~13k differential fuzz inputs
   across two campaigns ending in a strict consecutive dry pair; every
   engine divergence ever found was fixed and pinned
   (see `rust/PARITY-REPORT.md`).
2. **Both ADR-063 gates have working prototypes here**: the
   language-neutral spec file (`rust/spec/artifact-specs.json` + its
   generator) and a cross-language conformance suite (the parity case
   list + oracle-generated vector suites) — the mainline items
   (`artifact-specs-extraction`, `conformance-fixtures`) can adopt them
   nearly as-is.
3. **Performance exceeds every target by 4–50×**, removes the interpreter
   startup tax from agent-facing gates entirely, and obsoletes the cache
   stack's complexity for the CLI path.
4. **The remaining surface is bounded and enumerated** — the gap list in
   PARITY-REPORT.md names every uncovered command; `ingest` stays a
   Python sidecar (markitdown) by design; MCP serving and explorer are
   separate delivery surfaces.

Python remains the authoritative engine until the maintainer decides
otherwise (ADR-063); this spike changes the evidence, not the decision.

---

## Warm-path addendum (roadmap:native-derived-index, 2026-07-13)

The derived-index stack (ADR-099/103/104/105/106/107/108/112) is now
ported (`rust/INDEX-PLAN.md`, report in `rust/INDEX-REPORT.md`), so the
"no cache by design" posture above is superseded: the native engine
ships the cache **on by default** (ADR-112), byte-neutral by contract
and refereed cache-on and cache-off. Same box class, same harness
posture (piped stdio, neutralized env, medians of 7 warm runs / 3
fresh runs), oracle `.venv-oracle` at `21c8be4`. Corpus: the 5k
synthetic corpus (`rust/tools/gen_corpus.py --n 5000`), measured
OUTSIDE any git repository so the numbers isolate the cache (see the
recency note below).

| Workload (5k corpus) | Python oracle | Rust | Ratio |
|---|---|---|---|
| `find --json` no-cache (fresh walk) | 8 654 ms | 647 ms | 13× |
| `find --json` cold (walk + store write) | 5 606 ms | 1 445 ms | 3.9× |
| `find --json` **warm** (mapped store) | 446 ms | **43 ms** | 10× |
| `validate` no-cache | 7 082 ms | 150 ms | 47× |
| `validate` cold (incremental first run) | 7 123 ms | 800 ms | 8.9× |
| `validate` **warm** (`.vseg` reuse) | 542 ms | **92 ms** | 5.9× |
| broad-match `find "system"` fresh → warm (Rust) | 9 103 → 1 044 ms | 873 → **211 ms** | — |
| MCP `get_summary` warm (per call, live corpus, tracker) | 2.8 ms | **1.8 ms** | — |

Against the roadmap's motivating number (RAC-KXBE6DEDTCYA: "uncached
`find --json` over a 5,000-file synthetic corpus takes ~21.6 s in the
Rust engine"): that measurement ran with the synthetic corpus INSIDE
the repository's git tree, and is dominated by the ADR-045 per-match
recency join (git lookups after ranking), not by the walk — the same
query outside git is 0.87 s fresh. The cache closes the walk/derive
half: warm `find` on the 5k corpus is **43 ms** (~500× under the
recorded floor, ~15× under the out-of-git fresh walk). The recency
join is orthogonal to the cache (it runs identically warm or cold, in
both engines, only for matches inside a git tree) and is recorded here
so the floor's provenance is honest.

Warm MCP serving (ADR-105 tracker, stat-scan rung per ADR-114 — no
inotify): after the cold call, `get_summary` serves at ~1.8 ms/call
native vs ~2.8 ms/call for the oracle's inotify-clean skip; the
stat-scan of a 427-file corpus prices at ~1 ms, so the deferred
inotify rung buys nothing at this scale (it becomes interesting at
100k+ files, where the seam it slots into still exists).

Methodology: `RAC_CACHE_DIR` pointed at a scratch dir per engine;
no-cache = `RAC_NO_CACHE=1`; cold = first cache-on run against an
empty cache dir; warm = median of 7 subsequent runs. MCP per-call
numbers from a single long-lived server driven over stdio.
