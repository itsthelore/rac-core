# PORT-CONTRACT — Rust engine spike (roadmap:native-engine-spike)

The binding contract for the Rust port of the rac-core engine. The detailed,
per-subsystem contracts live in `PORT-CONTRACT.d/` (one section per recon
workstream, each verified empirically against the Python oracle). This file
is the index, the cross-cutting decisions, and the scope fence.

Oracle: the Python tree at `src/` (frozen — never modified), installed into
`.venv-oracle`. Parity means **identical stdout bytes and identical exit
codes** for every covered invocation, JSON and human output alike.

## Sections

| # | File | Scope |
|---|------|-------|
| 01 | `PORT-CONTRACT.d/01-cli-surface.md` | argv surface, flags, exit codes, streams, env vars per covered command |
| 02 | `PORT-CONTRACT.d/02-frontmatter.md` | frontmatter parsing: PyYAML-1.1 SafeLoader subset, bounds, exact errors |
| 03 | `PORT-CONTRACT.d/03-markdown.md` | markdown sectioning: consumed token surface, line ranges, normalization |
| 04 | `PORT-CONTRACT.d/04-classification-validation.md` | classification scoring, identity, validation rules and message catalog |
| 05 | `PORT-CONTRACT.d/05-relationships.md` | edge extraction, resolution, the nine `--validate` issue types, renderers |
| 06 | `PORT-CONTRACT.d/06-resolve-search.md` | BM25F + RRF: tokenization, f64 operation order, rounding, tie-breaks |
| 07 | `PORT-CONTRACT.d/07-output-bytes.md` | every `json.dumps` call site, float repr, human padding, SARIF, ANSI |
| 08 | `PORT-CONTRACT.d/08-goldens-fixtures.md` | golden-test conventions, fixture corpora, git-derived field inventory |
| 09 | `PORT-CONTRACT.d/09-walk-stats-export-review-schema.md` | corpus walk order, stats/export/review/schema payloads |

## Covered command set (v0)

`validate`, `find`, `resolve`, `relationships`, `review`, `stats`, `schema`,
`export`, plus `--version` — JSON, human, and (where implemented) SARIF
output, and every associated exit code. Everything else is enumerated in the
gap list of section 01 and re-listed in `PARITY-REPORT.md`.

Out of scope for v0 (by the spike roadmap): explorer TUI, `ingest`, MCP
serving, and the entire derived-index cache/mmap store. The Rust engine does
a fresh deterministic walk per invocation. The oracle's cache is contractually
byte-neutral (section 01, verified in 06), so the oracle runs with defaults.

## Cross-cutting decisions

1. **Python-compatibility primitives first.** One `pycompat` module in
   `rac-engine` implements, with tests against oracle-generated tables:
   - `py_repr(str)` — Python `repr()` incl. quote-flipping and escape forms
     (used by ~10 message formats via `{x!r}`).
   - `py_float_repr(f64)` — shortest-roundtrip repr shaped Python-style
     (`1e-05`, `1e+20`, whole floats keep `.0`); used by the JSON writer.
   - `py_round(f64, ndigits)` — correct decimal round-half-even on the true
     binary value (David Gay semantics), NOT `(x*10^n).round()/10^n`.
   - `py_casefold(str)` — full Unicode case folding (`ß`→`ss`), never
     `to_lowercase()`.
   - `py_strip`, `py_splitlines` — Python's whitespace set (incl.
     `\x1c`–`\x1f`, NBSP; excluding U+FEFF and U+200B) and line-boundary set
     (incl. `\v \f \x1c-\x1e \x85 U+2028/29`).
   - Unicode-aware `\d`/`\b` where the oracle uses `re` defaults.
2. **One JSON writer**, Python-`json.dumps`-shaped: `indent=2` with bare `,`
   before newline and `": "` key separator, `ensure_ascii=true` (`\uXXXX`),
   insertion-order keys, `py_float_repr` for floats, empty `[]`/`{}` inline,
   trailing `\n` from `print`. Exception: `export --documents` JSONL is
   compact separators (`", "`, `": "`) with raw UTF-8 (`ensure_ascii=false`).
3. **Frontmatter is a bespoke parser** reproducing the oracle's bounded
   PyYAML-1.1 SafeLoader semantics — YAML-1.1 resolution (octal `010`,
   sexagesimal `1:30`, `on/yes/off` bools but bare `y`/`n` strings, dates,
   float-needs-dot-and-signed-exponent), duplicate-key rejection with
   Python-repr'd keys, alias rejection (anchors alone allowed), the 32-level
   node-count depth cap, and the pinned error wordings including embedded
   PyYAML problem strings. No Rust YAML crate (all are YAML-1.2). The
   long-tail malformed-YAML message catalog is fuzz-driven in Phase 3.
   The unhashable-collection-key `TypeError` crash in the oracle is mirrored
   as observable behavior only if fuzzing shows it reachable from covered
   commands; otherwise recorded in the report.
4. **Markdown is a bespoke block-boundary tokenizer.** The consumed surface
   is exactly: `heading_open` (tag + start line) and `inline` (raw content +
   start line) from CommonMark block parsing — no HTML, no inline rendering.
   The bake-off (section 03) therefore targets block-structure parity only:
   headings (ATX and setext, incl. inside blockquotes/lists), fences/code/
   HTML-blocks as heading-invisibility rules, and paragraph raw text with
   0-based start lines. Candidate crates are judged by this surface; a
   bespoke tokenizer is the expected winner.
5. **Sorting**: corpus walk and every path sort are component-wise
   (Python `PurePath` parts tuple), not whole-string. Classification
   tie-breaks preserve `ARTIFACT_SPECS` order (stable sort, reverse by score
   only). Resolve fusion sort key is `(-py_round(fused, 12), path)` with the
   fused value itself unrounded; f64 accumulation order is normative
   (section 06) and `idf` uses `ln` on the plain expression, never `log1p`.
6. **Version string is injectable.** The oracle emits a setuptools-scm
   git-describe version (`0.1.dev50+g…`) in `--version`, `export --json`
   (`rac_version`), and SARIF (`driver.version`). The Rust binary takes its
   version from the `DECIDED_RS_VERSION` env var when set (spike-only seam); the
   parity harness sets it to the oracle's exact string so comparison stays
   byte-for-byte with no masking.
7. **Git-derived fields come from real git.** Recency/staleness (`find`,
   `review` drift) shells out to `git log` exactly as the oracle does
   (committer-offset `%cI` timestamps, `timedelta.days` flooring). The
   parity harness runs both engines against the *same* checkout/fixture git
   state; where goldens strip these fields, the harness reproduces the
   goldens' exact stripping conventions (section 08) and documents each one.
8. **ANSI color** is gated solely on stdout-isatty (no `NO_COLOR`, no flag).
   The harness captures via pipes, so both engines emit plain text; TTY
   color parity is asserted separately by code inspection plus a small
   pty-based spot check, not the main scoreboard.
9. **Help/usage text is out of parity scope.** argparse's width-wrapped
   `--help`/usage bodies are not reproduced; the contract pins only the
   final `<prog>: error: <msg>` line, the `rac: <msg>` hand-written dialect,
   stderr routing, and exit code 2.
10. **Determinism env for all measured/compared runs**: pipes for stdio,
    same cwd, `TERM` unset irrelevant (isatty gate), and the oracle's usage
    ping neutralized (section 01) so no run touches the network.

## Baselines on this box (7-run medians, 2026-07-11)

| Measure | Median | Min |
|---|---|---|
| `python -c pass` | 12 ms | 12 ms |
| `rac --version` | 192 ms | 182 ms |
| `rac validate <one file>` | 201 ms | 188 ms |
| `rac validate rac/` (warm cache, 417 artifacts) | 223 ms | 217 ms |
| `rac validate rac/ --no-cache` | 1 588 ms | 1 580 ms |

Fresh-walk throughput ≈ 263 files/s. Targets (same box, Rust, no cache):
`--version` < 15 ms; single-file validate < 25 ms; fresh `rac/` walk
< 150 ms; ≥ 10× the 263 files/s serial throughput scaling to 4 cores with
order-invariant output; peak RSS < 1 GiB at 20k artifacts.

## Spec data

`rust/spec/artifact-specs.json` is generated from `rac.core.artifacts` by
`rust/spec/extract_artifact_specs.py` (derived copy; regenerate, never edit).
The Rust engine embeds it at build time. The mainline extraction where
Python itself reads the file remains the `artifact-specs-extraction` roadmap
item — this spike does not modify Python.
