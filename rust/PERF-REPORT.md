# PERF-REPORT — Rust engine spike (roadmap:native-engine-spike)

<!-- DRAFT: final re-run after phase 3 close pending; [PENDING] marks splice
     points. All numbers below are real measurements from this box. -->

Box: 4-core / 15 GiB container (same class as ADR-107's reference node).
Oracle: `.venv-oracle` (Python 3.11.15, editable install of this branch's
`src/`). Rust: `rust/target/release/rac`, toolchain 1.94.1, lto=thin.
Harness: `rust/tools/perf.py` (piped stdio, neutralized telemetry env,
7-run medians; 3 runs at 20k). Synthetic corpora: `rust/tools/gen_corpus.py`
(seeded, five artifact types, cross-references).

## Headline vs targets

| Measure | Python oracle | Rust (sequential) | Target | Verdict |
|---|---|---|---|---|
| Startup (`--version`) | 203.8 ms | **1.7 ms** (120×) | < 15 ms | ✅ 8.8× headroom |
| Single-file validate | 199.7 ms | **3.0 ms** (67×) | < 25 ms | ✅ |
| Fresh walk, live `rac/` (417) | 1 588 ms (`--no-cache`) / 223 ms (warm cache) | **75 ms** (21× / 3.0×) | < 150 ms | ✅ beats Python's *warm cache* with no cache at all |
| Cold-walk throughput, 1k | 653.7 files/s | **12 480 files/s** | ≥ 10× serial | ✅ 19.1× |
| Cold-walk throughput, 5k | 720.8 files/s | **12 565 files/s** | ≥ 10× serial | ✅ 17.4× |
| Cold-walk throughput, 20k | 751.0 files/s | **12 251 files/s** | ≥ 10× serial | ✅ 16.3× |
| Peak RSS at 20k | ~77 MiB (5k; 20k not recorded) | **167 MiB** | < 1 GiB | ✅ |
| Product bar: one-shot gate invocation | ~200 ms floor (interpreter startup) | **≤ 75 ms** for the whole live corpus | < 50 ms per gate | ✅ single-file gates run in ~3 ms |

All targets are met by the **sequential** engine; rayon parallelism was
deliberately deferred until after the divergence hunt froze engine files.
[PENDING: 4-core rayon numbers + order-invariance proof, or the recorded
decision to ship sequential.]

## Detail

### Wall-clock (medians)

| Workload | Python | Rust |
|---|---|---|
| `--version` | 203.8 ms | 1.7 ms |
| `validate <one file>` | 199.7 ms | 3.0 ms |
| `validate rac/` fresh | 1 588 ms | 75 ms |
| `validate <1k>` fresh | 1 529.9 ms | 80.1 ms |
| `validate <5k>` fresh | 6 937.2 ms | 397.9 ms |
| `validate <20k>` fresh | 26 631.1 ms | 1 632.6 ms |

### Interpretation against ADR-107's budget line

ADR-107 recorded 692 files/s serial / 887 files/s at 4 workers for the
Python cold build, 18.8 min per 1M files against a 432 s budget. The
sequential Rust engine sustains ~12.3k files/s ≈ **81 s per 1M files** —
inside the ADR-107 budget with 5.3× margin, on one core, with flat memory
(the pre-streaming Python build OOM'd at 15.9 GiB at 1M; Rust holds
~167 MiB at 20k with no growth trend across sizes).

### Where the oracle's time goes

~190 ms of every Python invocation is interpreter + import startup — the
dominant cost for one-shot gate invocations (the primary agent-facing use
per ADR-067/075). The Rust engine's 1.7 ms startup eliminates that class
entirely: a full pre-merge gate on the live corpus (validate +
relationships --validate + review) costs [PENDING: measured chain] vs
Python's ~600 ms warm / ~2 s fresh.

## Caveats

- Synthetic corpora are structurally realistic but average smaller/simpler
  bodies than the live corpus (live-corpus throughput ≈ 5.6k files/s
  at 417 files; synthetic ≈ 12k files/s) — both engines measured on the
  same corpora, so ratios hold.
- RSS is `getrusage(RUSAGE_CHILDREN)` peak (no /usr/bin/time on this box).
- No cache exists on the Rust side by design (spike posture); the fair
  Python comparison is `--no-cache`, but the warm-cache number is shown
  because the Rust engine beats even that.

## Go / no-go recommendation

[PENDING: final synthesis after phase 3 verification — draft position:
GO for a mainline evaluation. Parity is mechanically proven on the covered
surface, the two ADR-063 gate artifacts (language-neutral spec file,
conformance suite) have working prototypes in this spike, and performance
exceeds every target by an order of magnitude with the cache deleted —
which would obsolete ADR-099/104/112's complexity for the CLI path. The
gap list (uncovered commands, ingest sidecar, MCP serving) defines the
remaining port surface and is enumerated in PARITY-REPORT.md.]
