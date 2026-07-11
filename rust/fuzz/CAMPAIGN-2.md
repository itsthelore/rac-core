# Fuzz Campaign 2 — full command set, loop until dry

Differential fuzzing of the Rust engine against the Python oracle over the
FULL covered command surface (PORT-CONTRACT v0 set), extending campaign 1's
validate/relationships/stats matrix with resolve, find, schema, export,
review, the relationships inspection arm, stdin validation, env variation,
path edge forms, and multi-file corpora.

- Fuzzer: `rust/fuzz/difffuzz.py` (stdlib-only; generation deterministic
  per seed; `--jobs 8` thread workers, each with its own case dir + XDG
  root; execution order across threads may vary, the signature set does
  not).
- Oracle: `.venv-oracle/bin/rac` (rac 0.1.dev50+g21c8be403, CPython
  3.11.15, PyYAML 6.0.3, markdown-it-py 4.2.0).
- Rust engine: `rust/target/release/rac`, rebuilt between rounds as fixes
  landed — never mid-round (each round ran against a single build).
- Findings catalog: `rust/fuzz/findings2/` (campaign 1: `findings/`).
- Comparison: raw stdout bytes + exit codes under the parity env
  (env-cleared, `RAC_NO_CACHE=1`, `LC_ALL=C`, `TZ=UTC`, `COLUMNS=80`,
  `PYTHONHASHSEED=0`, `RAC_RS_VERSION` seam; stdin null unless the case
  feeds it).

## Command matrix

Per input: 5 CORE commands always + 5 sampled (deterministically per input)
from a 27-spec EXTENDED pool → 10 engine-pair runs per input, every
extended spec exercised 100+ times per 800-input round (schema variants
rotate inside one slot).

- CORE: `validate FILE [--json]`, `validate DIR --sarif`,
  `relationships DIR --validate --json`, `stats DIR --json`.
- Extended pool:
  - `validate DIR [--json]`, `relationships DIR --validate`, `stats DIR`
  - inspection arm: `relationships DIR [--json]`
  - `review DIR [--json|--sarif]`
  - `export DIR [--json]`, `export DIR --documents`
  - `resolve QUERY DIR [--json]`, `find QUERY DIR [--json]` — queries
    derived from the mutated content: full/partial/lowercased RAC ids,
    ADR refs, unicode words, duplicated tokens, two-word combos, title
    prefixes, plus fixed probes (`""`, `"the system SHALL"`, `"RAC"`)
  - `schema --list [--json]`, `schema NAME [--json|--template]` with NAME
    from the real set, case variants, or content-derived garbage
  - stdin: `validate - [--json]`, `validate - --corpus DIR --json`
    (case bytes fed on stdin)
  - env: `RAC_MAX_FILE_BYTES` ∈ {small/boundary/data-length±1, zero,
    negative, unparseable, underscore/sign/whitespace forms, non-ASCII
    Nd digits (`٣٢`), > 2^63, > 2^64} on `validate FILE --json` /
    `validate DIR`
  - path edge forms: `corpus/` (trailing slash), `./corpus`,
    `corpus//case.md`, and `case.markdown` as a direct file argument
- Multi-file corpus mode: ~35% of inputs get 1-3 auxiliary artifacts next
  to the mutated primary (plain corpus picks, mutated picks, or synthetic
  decisions whose relationships reference ids found in the primary; 10%
  `.markdown` extension, 25% nested `sub/` placement).
- Mutation operators: campaign 1's 32 plus `op_fm_relationships`
  (relationship blocks aimed at the resolution arm) = 33.

## Triage rule

Any divergence where the oracle died with an uncaught Python traceback is
the documented campaign-1 finding-001 class (PORT-CONTRACT decision 3:
divergence by design). Those are auto-classified `oracle-crash`, filed at
most once per command name (suffix `-oracle-crash`), and do NOT count
against a round's dry verdict. The reverse shape — Rust emitting the
marker while the oracle exits cleanly — still counts as an engine finding
(that was campaign-1 finding 003). Minimization preserves the triage class
so an engine repro can never ddmin-drift into the crash class.

## Rounds

Each round: 800 fresh inputs (fresh seed), 10 command-pairs per input
(~16,000 engine-pair executions), full matrix. A round is DRY when it
files zero new ENGINE signatures.

| round | seed | build under test | divergent inputs | new engine findings | new oracle-crash repros | dry? |
|---|---|---|---|---|---|---|
| smoke | 999 (30 inputs) | pre-campaign | 4 | 004 (maxbytes), 005 (stdin surrogateescape) | 6 | — |
| 1 | 201 | 004+005 fixed | 69 | 006 (export CRLF; 4 sigs, 1 class) | 30 | no |
| 2 | 202 | 006 fixed | 80 | 007 (fence-at-EOF html), 008 (stats tie-break), 009 (heading strip) | 0 | no |
| 3 | 203 | 007+008+009 fixed | TBD | TBD | TBD | TBD |

(Table finalized at campaign close; per-round journal lines in
`rust/fuzz/campaign.log`, `campaign2` prefix.)

## Findings and resolutions

Numbering continues campaign 1 (001–003).

| finding | class | surface | summary | resolution |
|---|---|---|---|---|
| **004** `RAC_MAX_FILE_BYTES` seam | (a) Rust bug + (b) oracle crash zone | every file-reading command | Rust parsed the override with an ASCII-only i64 parser: CPython `int()` accepts non-ASCII Nd digits (`٣٢` = 32) and unbounded magnitude, so such caps silently fell back to 1 MiB (wrong oversize behavior), and huge caps missed the oracle's read-stage crashes: `fh.read(cap+1)` raises `OverflowError: cannot fit 'int' into an index-sized integer` (cap ≥ 2^63−1) or `OverflowError: byte string is too large` (2^63−34 ≤ cap ≤ 2^63−2), boundaries pinned empirically. | **FIXED.** `frontmatter::FileCap` + shared `markdown::py_parse_int` (now saturating beyond i128); the two deterministic crash zones are mirrored as decision-3 markers at the read stage; the machine-dependent `MemoryError` zone (huge-but-allocatable caps) is documented, not mirrored. Vectors: `frontmatter.json` env_cap +7 cases, boundary asserts in `frontmatter_vectors.rs`; parity pins `pin-c2-maxbytes-*`. |
| **005** stdin surrogateescape | (a) Rust bug | `validate -` | The oracle reads stdin as TEXT with `errors="surrogateescape"` (each undecodable byte → lone surrogate U+DC00+b); Rust used the file path's lossy U+FFFD decode. Everything downstream diverged: PyYAML rejects surrogates (`unacceptable character #xdccc … position N`), `repr()` shows `\udccc`, JSON writes `\udccc`, human stdout re-emits the raw byte. | **FIXED.** `pycompat::decode_stdin_surrogateescape` maps each bad byte to a plane-16 PUA sentinel (U+10FC00+b) behind a process-wide flag; sentinel-aware sinks: YAML `check_printable`, `py_repr_str`, the JSON writer, and stdout emission (re-materializes the raw byte). Flag-gated: file-based runs are bit-identical to before. Unit tests in `pycompat.rs`; parity pins `pin-c2-stdin-*` via the harness's new `stdin_file` case field. |
| **006** export universal newlines | (a) Rust bug | `export DIR [--json\|--documents]` | The oracle's `_body_markdown` re-reads artifacts in TEXT mode: universal newlines fold `\r\n`/`\r` to `\n` before `split_frontmatter`; Rust exported the raw CRLF body (`text` field, and `body_html` rendering input). 4 signatures filed in round 1, one root cause. | **FIXED.** `export::body_markdown` now folds `\r\n`/`\r` → `\n`. The same re-read is STRICT utf-8 in the oracle — invalid bytes crash it (`UnicodeDecodeError`) while Rust exports the lossy body; that side is divergence-by-design (catalogued as oracle-crash Class D). Parity pins `pin-c2-export-*-crlf` on `rust/fuzz/pinned/crlf/`. |
| **007** fence-at-EOF html | (a) Rust bug | `export DIR [--json]` (`body_html`) | markdown-it-py builds fence content by slicing the source (`src[first:eMark+1]` truncates silently at EOF), so an UNCLOSED fence whose last line ends the document without a newline has no trailing `\n`; the markdown-it crate's `get_lines` appends one unconditionally → `<code>…inside\n</code>` vs `<code>…inside</code>`. | **FIXED.** Post-parse AST fixup in `mdhtml.rs` (`fix_eof_fence_content`): a CodeFence whose srcmap ends at EOF and whose span holds exactly 1 + content-lines source lines is unclosed-at-EOF; strip the synthetic newline. Container-nesting safe (line counts, not prefixes). Parity pin `pin-c2-export-render-fence-eof-strip`. |
| **008** stats tie-break inversion | (a) Rust bug | `stats DIR [--json]` | `largest_feature` ties: the oracle's key is `tuple(-ord(c))`, where a strict-prefix tuple is SMALLER — so between tied "Feature" and "Feature With Broken Ref" the LONGER name wins `max()`. Rust's `neg_name_gt` had the prefix rule inverted (shorter wins). Found by multi-file corpus mode (two tied single-requirement features). | **FIXED.** Prefix arm flipped in `stats::neg_name_gt` + unit test; parity pins `pin-c2-stats-largest-tie-*` on `rust/fuzz/pinned/stats-tie/`. |
| **009** heading/paragraph Python strip | (a) Rust bug | `export DIR [--json]` (`body_html`) | markdown-it-py computes ATX-heading, setext-heading, and paragraph content as `<lines>.strip()` — CPython whitespace, including `\x0b \x0c \x1c-\x1f \x85 \xa0` — while the markdown-it crate trims only spaces/tabs: for `## Consequences\x0b` the oracle renders `<h2>Consequences</h2>`, Rust rendered `<h2>Consequences\u000b</h2>`. | **FIXED.** Custom core rule `PyStripInlineRule` in `mdhtml.rs`, registered after block parse and before inline parse, re-strips those blocks' pending `InlineRoot` content with `py_strip`. Fixture `rust/fuzz/pinned/render/strip-heading.md` covered by the same parity pin as 007. |

Oracle-crash class (001, divergence by design): campaign 2 confirmed the
class is reachable through EVERY covered command and every new probe
dimension (file/dir/slash/dot/doubled-slash/`.markdown` path arms, stdin,
env variation, review/export/find/resolve/schema-adjacent walks) — 30+
per-command repros filed with the `-oracle-crash` suffix, all deduping to
oracle tracebacks of the known constructor/read/re-read crash families.
Curated repros: `rust/fuzz/pinned/oracle-crashes/` (excluded from the
parity suite; the gap list in PARITY-REPORT.md points there).

Fuzzer/harness work this campaign:

1. Triage now keys on the oracle's stderr traceback, not on the Rust
   marker string — dir-walk commands never print the marker, which had
   mislabeled crash-class hits as engine findings in the smoke run.
2. Minimization predicate preserves the triage class (no ddmin drift
   between engine and crash classes).
3. `parity-harness` grew an optional `stdin_file` case field (raw bytes
   piped to both engines) so stdin regressions are pinnable.
4. Threaded execution (`--jobs`), multi-file case staging, per-command
   env/stdin/file-variant plumbing, coarse per-command dedup for the
   crash class.

## Dry-round evidence

TBD at campaign close: two consecutive 800-input rounds with zero new
engine signatures (journal lines + findings2 catalog state).

## Pinned regressions

- Parity cases (all in `rust/parity-cases.json`, fixtures under
  `rust/fuzz/pinned/`): `pin-c2-stdin-fm-surrogate-{json,human}`,
  `pin-c2-stdin-body-surrogate-{json,human}`,
  `pin-c2-maxbytes-unicode-digits-json`, `pin-c2-maxbytes-underscore-human`,
  `pin-c2-export-documents-crlf`, `pin-c2-export-json-crlf`,
  `pin-c2-export-render-fence-eof-strip`,
  `pin-c2-stats-largest-tie-{json,human}`.
- Rust vector/unit tests: `frontmatter_vectors.rs` (env_cap + crash-zone
  boundary grid), `pycompat.rs` (surrogateescape decode/re-encode/repr),
  `stats.rs` (`neg_name_prefix_tie_prefers_longer`).
- Oracle-crash (001-class) repros: `rust/fuzz/pinned/oracle-crashes/`
  with README — divergence by design, excluded from the parity suite.
