# Fuzz Campaign 1 — validate / relationships / stats

Differential fuzzing of the Rust engine against the Python oracle over the
currently-green command set, per the native-engine spike phase 3.

- Fuzzer: `rust/fuzz/difffuzz.py` (stdlib-only, deterministic per seed).
- Oracle: `.venv-oracle/bin/rac` (rac 0.1.dev50+g21c8be403, Python 3.11.15,
  PyYAML 6.0.3).
- Rust engine: `rust/target/release/rac`, prebuilt by the port workflow.
  NOTE: the port workflow rebuilt the binary twice mid-campaign (working
  tree ahead of commit e7e6425; final build md5
  57c7fa4f0741e0e650d125f1262250ec). Wave 1 ran mostly against the b8db3af
  build; wave 2 replayed all wave-1 inputs against the newer builds with
  identical per-seed divergence totals (20/25/20/27), and all three filed
  finding classes were re-verified byte-level against the final build.
- Command matrix per input (9): `validate FILE [--json]`,
  `validate DIR [--json|--sarif]`, `relationships DIR --validate [--json]`,
  `stats DIR [--json]` — raw stdout bytes + exit codes compared under the
  parity env (env-cleared, `DECIDED_NO_CACHE=1`, `LC_ALL=C`, `TZ=UTC`,
  `COLUMNS=80`, `PYTHONHASHSEED=0`, `DECIDED_RS_VERSION` seam, null stdin).

## Inputs tested

| wave | seeds | generated inputs | engine-pair command runs |
|---|---|---|---|
| 1 (random) | 11, 12, 13, 14 | 3,200 (8 rounds x 100/seed) | ~28,800 x2 |
| 2 (re-run audit + fresh) | 11-14 replayed, 21, 22 | 3,200 replayed + 1,600 fresh | ~43,200 x2 |
| directed probes (`probe_directed.py`) | — | 50 | 450 x2 |
| multi-file probes (`probe_multifile.py`) | — | 16 corpora | 160 x2 |

Total distinct generated inputs: **4,866** (3,200 random + 1,600 fresh
random + 66 directed), plus the deterministic 3,200-input replay for the
dedup audit. Every input ran the full command matrix on both engines.

## Counts per mutation class (random waves; 1-4 mutations per input)

Applications across the 4,800 random inputs (replay identical; from
deterministic RNG replay):

| operator | wave 1 (3,200) | seeds 21-22 (1,600) |
|---|---|---|
| op_fm_scalar_swap (weighted 3x) | 686 | 341 |
| op_fm_dup_key | 265 | 122 |
| op_html_block | 263 | 119 |
| op_setext | 260 | 130 |
| op_nbsp_delim | 249 | 125 |
| op_remove_block | 249 | 118 |
| op_fences | 248 | 121 |
| op_astral | 247 | 118 |
| op_splice | 245 | 121 |
| op_fm_tags_mutate | 243 | 131 |
| op_fm_tab | 241 | 118 |
| op_heading_in_container | 240 | 116 |
| op_hash_games | 239 | 116 |
| op_tabs | 238 | 111 |
| op_fm_quote | 234 | 128 |
| op_fm_deep_nesting | 233 | 107 |
| op_fm_merge_key | 233 | 123 |
| op_indented_code | 233 | 95 |
| op_fm_oversize | 233 | 118 |
| op_truncate | 232 | 119 |
| op_fm_dup_key_cross_type | 232 | 130 |
| op_concat | 229 | 127 |
| op_invalid_utf8 | 229 | 116 |
| op_fm_complex_key | 229 | 111 |
| op_crlf | 228 | 126 |
| op_control_chars | 227 | 111 |
| op_fm_anchor_alias | 223 | 138 |
| op_dup_block | 223 | 122 |
| op_byte_edit | 219 | 123 |
| op_delim_games | 219 | 112 |
| op_unicode_heading | 217 | 112 |
| op_bom | 216 | 128 |

All 32 operators exercised in every wave.

## Divergences

Random campaign: **92 divergent inputs in wave 1** (per-seed 20/25/20/27,
see `campaign.log`) and **141 in wave 2** (the same 92 replayed with
identical per-seed totals, plus 49 from fresh seeds 21/22) — **every one of
them reduces to a single root-cause class** (finding 001 below; the wave-2
original-signature audit filed zero new signatures, confirming no second
class was masked by minimization collapse in wave 1). Directed probes added
**24/50 divergent inputs** falling into two further classes (002, 003).
Multi-file probes: **0/16 diverged**.

### Findings (catalog: `rust/fuzz/findings/`)

| finding | class | command | summary | resolution |
|---|---|---|---|---|
| `001-oracle-crash-unhashable-key` | (b) oracle crash | validate (all) | `? []` et al. unhashable YAML keys, tag/value constructor mismatches (`!!int ''`, `!!bool banana`), and out-of-range plain timestamps (`2026-13-01`) crash the oracle uncaught (`frontmatter.py:52 _no_duplicates`); Rust deliberately emits `internal-oracle-divergence` instead (PORT-CONTRACT decision 3, 02 §3b). Expected, intentional divergence. | **WONTFIX (by design).** Documented decision-3 marker class; repro re-verified after the 002/003 fixes — the marker mirrors the oracle's exception string byte-exactly. |
| `002-oracle-crash-map-tag-on-scalar` | (b) oracle crash, port-consistency note | validate (all) | `!!map <scalar>` crashes the oracle (`ValueError: not enough values to unpack`), but Rust mapped it to a *regular* `malformed-frontmatter` issue instead of the decision-3 `internal-oracle-divergence` marker — the port assumed a catchable ConstructorError on this path. | **RESOLVED (aligned).** `construct_strict_map` now mirrors `_no_duplicates`: `!!map` on a non-empty scalar → internal `ValueError: not enough values to unpack (expected 2, got 1)`; on a non-empty sequence → internal `TypeError: cannot unpack non-iterable {Scalar,Sequence,Mapping}Node object`; empty scalar/sequence still reach the caught `expected a mapping node` ConstructorError. Constructor audit also aligned `!!timestamp {=: …}` (message now carries `, got 'list'`) and added the CPython 4300-digit int<->str limit crashes (see 003). Repro now dedups into the 001 signature class. |
| `003-rust-bug-bigint-i64-seam` (+`003a`) | **(a) Rust engine bug** | validate (all; any command parsing frontmatter) | Integers beyond i64 (`9999999999999999999`, `0xFFFFFFFFFFFFFFFFFF`, i64::MAX+1) aborted the whole frontmatter load with `internal-oracle-divergence OverflowError … (rust port seam)`; the oracle parses them as Python bignums and reports normal per-field issues. Violated 02 §4 (int resolver is unbounded) and §5 (validator messages must print the value). | **FIXED.** `Yaml::BigInt` (sign + decimal digits, base-1e9 arithmetic) makes int construction unbounded across decimal/hex/octal/binary/sexagesimal spellings; Python-equality duplicate-key semantics (`bignum == float` compared exactly), `repr()`, and validator messages (`unsupported frontmatter schema_version: 99999999999999999999 (supported: 1)`) follow CPython, including the 4300-digit int<->str conversion-limit crashes (mirrored as decision-3 markers, `crash_stage` tracked in the vector suite). Repros 003/003a and a fresh 24-input grid (i64::MAX±1, i64::MIN±1, u64::MAX+1, 100-digit, negative huge, hex/octal/binary/sexagesimal huge, bignum-vs-float dup keys, 4300/4301-digit boundary) verified byte-identical vs the oracle; grid + crash classes added to `frontmatter.json` vectors (511 parse cases, 37 crash). |

Oracle nondeterminism observed: **none** (all divergences reproduced
deterministically on re-run; wave-2 replay counts matched wave 1 per round).

Fuzzer bugs found and fixed during the campaign:

1. **Dedup-masking risk** — findings were deduplicated on the *minimized*
   signature; ddmin only preserves "some divergence on this command", so a
   second root cause could collapse into a known class and be dropped
   silently. Fixed: dedup now keys on the *original* divergence signature
   before minimizing (also skips minimization cost for known classes), and a
   new-original/known-minimized case is filed with a `-sameclass` suffix for
   human confirmation. Wave 2 replayed all wave-1 inputs under the fixed
   dedup: zero masked divergences.

## Coverage notes

- Covered well: YAML 1.1 scalar resolution (bool/octal/hex/sexagesimal/
  date/float spellings), quoting styles, anchors/aliases, merge keys,
  duplicate keys (incl. cross-type), depth caps, oversize payloads (64 KiB
  frontmatter cap, 1 MiB file cap), delimiter games (BOM, CRLF, NBSP, `...`,
  unterminated), markdown structure (setext, fences, HTML blocks, indented
  code, containers, tabs), unicode (astral, RTL, zero-width, fullwidth,
  combining), invalid UTF-8 (lossy-decode paths), control chars, and file
  splicing/truncation. Human, `--json`, and `--sarif` renderers all byte-
  compared on every input.
- Directed probes filled random-op blind spots: explicit YAML tags
  (`!!int/!!float/!!bool/!!binary/!!set/!!omap/!!pairs/!!timestamp/!!map/
  !!seq`), out-of-range timestamps, beyond-i64 integers, float overflow
  (`1.0e+400`), NUL/DEL/C1 bytes, double/single-quote escape forms, and
  schema_version spellings — this is where 002 and 003 were found.
- Multi-file corpora (cross-file resolution, ambiguity, dot-dir skipping,
  `.markdown` handling, unicode filenames, walk order, legacy-title aliases,
  plus the non-validate `relationships` and `relationships --json/--sarif`
  surfaces): parity-clean.
- Not covered (future campaigns): `resolve`/`search`/`schema`/`export`
  commands (not in the green matrix), `DECIDED_MAX_FILE_BYTES` env variation,
  path-argument edge forms (trailing slashes, `.markdown` args), concurrent
  cache behavior (campaign pins `DECIDED_NO_CACHE=1`), stdin-based input, and
  windows-style path separators.

## Verdict

After ~4,900 distinct inputs and ~72,000 engine-pair command executions, the
only true engine-behavior gap in the green command set was the **beyond-i64
integer seam (finding 003)**. Everything else is parity-clean or an
intentional, documented response to oracle crashes.

**Post-campaign resolution (2026-07-11):** the port workflow (1) fixed 003
with an arbitrary-precision `Yaml::BigInt` representation and (2) aligned the
`!!map <scalar>` path (002) with the decision-3 marker convention. After the
fixes: `cargo test -p rac-engine` green, the full parity suite passed 118/118
twice with identical scoreboards, all catalog repros re-verified (003/003a
parity-clean; 001/002 are the documented oracle-crash marker divergence), and
a directed-probe re-run dropped from 24/50 to 16/50 divergent — every
remaining one dedups into the single 001 oracle-crash signature class (all
bigint probes now clean).
