# 11 — Closure file ops: diff, inspect, improve

Scope: the B1 read-only file-analysis commands ported for
roadmap:native-cli-closure — `rac diff`, `rac inspect`, `rac improve`.
Every claim below was verified against the oracle (`.venv-oracle/bin/rac`,
`0.1.dev50+g21c8be403`, Python 3.11.15). Source files: `src/rac/cli.py`
(`cmd_diff`/`cmd_inspect`/`cmd_improve`, `_read`, `_read_markdown_input`),
`src/rac/services/{diff,inspect,improve}.py`,
`src/rac/output/{human,json,templates,_shared}.py`. Rust:
`rac-engine/src/{diff,inspect,improve}.rs`, `commands.rs`
(`cmd_diff`/`cmd_inspect`/`cmd_improve`, `read_markdown_input`), `cli.rs`
(`run_diff`/`run_inspect`/`run_improve`), `output.rs` renderers.

Shared conventions (see 09 §0): one trailing `\n` from `print()`; ANSI
color gated on `sys.stdout.isatty()`; `--json` via `json.dumps(indent=2)`
(`pyjson::dumps_indent2`); `✓ ✗ • → ×` and the em-dash are raw UTF-8.
All three commands are pure functions of file bytes: no git, no cache
(`RAC_NO_CACHE` irrelevant), no env, no writes, no timestamps.

---

## 1. `rac diff <old> <new> [--json]`

### 1.1 Argv surface
Two required positionals, each a path to a single file; `--json`
(json_parent) and `--version`. No `--sarif`, no `--template`, no
directory or stdin support. Missing positionals: argparse
`rac diff: error: the following arguments are required: old, new`
(neither given) / `... required: new` (only `old` given), exit 2.
**An extra positional is the TOP-LEVEL parser's error** — prog `rac`,
`rac: error: unrecognized arguments: extra.md` — not `rac diff` (argparse
subparsers hand leftovers back to the root parser).

### 1.2 File reading (`_read`)
- `Path(p).is_file()` false (missing, directory, `-`) →
  `rac: file not found: <p>` on stderr, exit 2. **`old` is read before
  `new`**, so a bad `old` wins the error. `-` is NOT stdin here — it is
  rejected as file-not-found.
- `parse_file` producing an `unreadable-artifact` parse issue →
  `rac: cannot read <p>`, exit 2.
- **No extension check** (unlike inspect/improve): `.txt` or anything else
  parses fine (uses `parse_file` directly). Non-UTF-8 bytes go through the
  parser's lossy read path, not a strict decode.

### 1.3 Semantics (`services/diff.py` — pure AST diff)
No git/revisions dependency (`revisions.py` belongs to watchkeeper only).
- Requirements match by ID. `_by_id` is a dict comprehension: on a
  duplicate ID the LAST occurrence wins the value but the key keeps its
  FIRST-insertion position.
- added/modified iterate NEW order; removed iterates OLD order.
- Metrics and risks: ordered set-difference, de-duped, preserving source
  order (`_ordered_difference`).
- `line` in JSON is the parser's 1-based requirement line — must match the
  ported parser exactly.

### 1.4 Output
- Empty diff → stdout exactly `No changes.` + `\n`, exit 0.
- HUMAN: blocks joined by ONE blank line, in fixed order: Added
  Requirements, Removed Requirements, Modified Requirements, Added
  Metrics, Removed Metrics, Added Risks, Removed Risks — each block only
  if non-empty. Titles are bold-wrapped only under a TTY. List blocks:
  `<title>\n\n` then `+ <id> <text>` (green) / `- <id> <text>` (red) per
  line. Modified block: `~ REQ-1` / `` / `Before:` / red old text / `` /
  `After:` / green new text; multiple modifieds separated by ONE extra
  blank line.
- JSON: fixed key order `old, new, added_requirements,
  removed_requirements, modified_requirements, added_metrics,
  removed_metrics, added_risks, removed_risks`. `old`/`new` echo the RAW
  argv strings (no normalization). added/removed items are
  `{id, text, line}` (Requirement asdict order); modified items are
  `{id, old_text, new_text}` (no line).
- Exit 0 on every completed diff. Never returns 1.

---

## 2. Shared single-file input (`_read_markdown_input`) — inspect + improve

1. `target == "-"` → `sys.stdin.read()` immediately (text decode with
   `errors="surrogateescape"` under the harness locale — same seam as
   `validate -`; sentinels re-materialize on stdout).
2. `Path(target).is_file()` false → `rac: file not found: <t>`, exit 2.
3. `Path(target).suffix.lower()` not in `(".md", ".markdown")` →
   `rac: <command> expects a Markdown file; convert it first with:
   rac ingest <t>`, exit 2. Case-insensitive (`.MD` accepted); pathlib
   suffix semantics (dotless, leading-dot-only, and trailing-dot names
   have no suffix).
4. `path.read_text(encoding="utf-8")` — STRICT decode. `OSError` →
   `rac: cannot read <t>: <exc>`, exit 2. Invalid UTF-8 raises
   `UnicodeDecodeError`, which nothing catches: **unhandled traceback,
   exit 1, empty stdout** (verified; the Rust port mirrors exit 1 + empty
   stdout, stderr text is out of parity scope).

---

## 3. `rac inspect <file|dir|-> [--verbose] [--top-level] [--recursive] [--json]`

### 3.1 Argv surface
One positional. `--recursive` is a no-op affirmation of the default;
`--top-level` disables recursion (directory mode only); `--verbose` is
single-file only; `--json` via json_parent. Always exit 0 on a completed
inspection (Unknown and an empty directory are valid outcomes).

### 3.2 Mode dispatch order (landmines)
- Directory detection PRECEDES the extension check: `inspect <dir>` works
  for any directory name; a single non-`.md` FILE is rejected. `-` is
  stdin and never gets the dir/extension checks.
- `--verbose` is ignored when `--json` is also passed
  (`if args.verbose and not args.json` — JSON wins), and ignored entirely
  for directories (the dir branch emits before verbose is consulted).

### 3.3 Single-file result assembly (`build_inspection`)
- `classify(product)`: type, confidence (= `round(fit, 2)` banker's,
  `pycompat::py_round`), present/missing sections. Unknown keeps
  `present_sections = list(product.sections)` and empty missing.
- Decision metadata only when type == `decision`: for each spec metadata
  field (`status`, `category`) with a truthy section body, the value is
  `canonical_value(first non-empty line, allowed)` — case-insensitive
  match returning the spec's canonical spelling, else the stripped
  candidate passes through. `supersedes` is the first non-empty line,
  unvalidated.
- Relationships for ANY type with a spec, via the inspect-facing extractor
  (`services/references.extract_relationships`) — spec.optional order,
  only sections with ≥1 parsed reference, **excluding `supersedes`**
  (rust: `relationships::extract_relationships`, sharing a core with the
  `_full` variant used by `rac relationships`).
- `supersedes` stays a TOP-LEVEL scalar in JSON (v0.4.2/ADR-007
  exception), never inside `relationships`.

### 3.4 Single-file output
- HUMAN: bold `Artifact Type: <Type.title()>`, `Confidence: <conf:.0%>`
  (Python `%`-format: ×100 in binary then zero-decimal half-to-even —
  `pycompat::py_format_percent0`), blank, bold `Present Sections:` with
  green `  ✓ <Section.title()>` lines or `  (none)`; then (only if any)
  blank + bold `Missing Sections:` with red `  ✗ ...`; then optional
  `Decision Metadata:` block (`  Status: Accepted` etc — only TRUTHY
  values, empty string dropped); then optional `Relationships:` block
  (`  Related Decisions:` label = snake→spaces→title, then
  `    - ADR-002` per ref).
- JSON (`to_dict`): `{type, confidence(2dp float), present_sections,
  missing_sections}` (sections snake_cased), plus additive
  `status`/`category`/`supersedes` **only when not None** (an empty
  string WOULD be emitted — `is not None`, unlike the human truthy
  filter), plus `relationships` only when non-empty.
- VERBOSE (single-file, not json): type + confidence lines; for unknown a
  `Closest match: <TypeScore.display>` line; `chosen` = the TypeScore
  whose name == result.type, else `scores[0]` (best-fit; stable sort keeps
  registry order on full ties, so a no-section doc explains via
  Requirement). Blocks (each preceded by a blank line): bold
  `Required Matches:` / `Recommended Matches:` (green ✓ or `  (none)`),
  `Missing:` only if non-empty (red ✗). Score line:
  `Score:` (bold) + ` <req> + 0.5 × <rec> = <points:g> / <ceiling:g>
  = <round(fit, 2)>` — `:g` drops trailing zeros (`2` not `2.0`, `3.5`
  stays); the rounded fit prints via `str()` (`0.0`, `0.57`, `1.0`).
  For unknown a final `(below the 50% threshold → Unknown)` line
  (`CONFIDENCE_THRESHOLD:.0%`).

### 3.5 Directory mode
`walk_corpus` (= `find_markdown_files` sorted walk + parse + classify;
rust `walk::find_markdown_files` + rayon map, order-preserving).
- HUMAN: bold `Files Inspected: <n>`, blank, then one line per spec in
  ARTIFACT_SPECS order — `<Display>s: <count>` — then `Unknown: <n>`.
- JSON: `{schema_version: "1", directory: <raw argv string>, recursive,
  summary: {total_files, counts: {requirement, decision, roadmap, prompt,
  design, unknown}, unknown}, files: [{path, type, confidence}]}` — files
  in walk-sorted order, paths as the walk displays them (normalized-root
  joined), confidence a 2dp float (`0.0` stays `0.0`).
- Empty directory: `Files Inspected: 0`, all zero counts, exit 0.

---

## 4. `rac improve <file|-> [--json | --template]`

### 4.1 Argv surface
One positional; `--json` and `--template` form a LOCAL mutually-exclusive
group (improve does NOT inherit json_parent — no `--sarif`). Conflict:
`rac improve: error: argument --template: not allowed with argument
--json` (order follows which flag came second), exit 2. Parent:
version_parent only. No directory support: a directory target fails
`is_file()` → `rac: file not found: <dir>`.

### 4.2 Semantics (`improve_product`)
- `supports_improve(spec)` = every `spec.expected` section has guidance.
  All five current specs pass, so the known-but-unsupported branch is
  DEAD in practice — ported for fidelity, unreachable by real input; only
  `unknown` hits the unknown message.
- `missing_sections(product, spec)` → (missing_required,
  missing_recommended), schema order, synonym-aware.
- `guidance` = `{section: spec.guidance[section]}` for missing sections
  with truthy guidance, required-first then recommended.

### 4.3 Output (exit 0 on every completed analysis)
- HUMAN unknown: exactly
  `Unable to generate improvement guidance.\nArtifact type could not be
  determined.` (`_UNKNOWN_MESSAGE`, shared with --template).
- HUMAN unsupported (unreachable): `Artifact Type: <Type>\n\n
  Improvement guidance is not currently available for this artifact
  type.`
- HUMAN with gaps: bold `Artifact Type: <Type.title()>`, blank, bold
  `Missing Required:` then per section `  - <Section.title()>` followed by
  `      • <question>` guidance bullets (or `  (none)`), blank, bold
  `Missing Recommended:` same shape; the joined text is `.rstrip()`ed
  (no trailing blank line).
- HUMAN no gaps: `Artifact Type: <Type>` + blank +
  `Nothing to improve — all expected sections present.` (em-dash).
- JSON (`to_dict`): `{type, missing_required, missing_recommended,
  guidance}` — sections snake_cased, guidance `{snake_section:
  [questions]}`; unknown yields type `"unknown"` with empty arrays and
  `{}`.
- TEMPLATE: for each missing section (required first) a block
  `## <Section.title()>\n\n_TODO_` plus, when guidance exists,
  `\n\n` + `<!-- <question> -->` lines; blocks joined by `\n\n` with a
  trailing `\n` (so stdout ends `\n\n` after print). Unknown/unsupported
  reuse the section-4.3 messages verbatim; nothing missing →
  `# Nothing to add — all expected sections present.`.

---

## 5. Parity evidence

`rust/parity-cases-closure.json`: `diff-*` (11), `inspect-*` (15),
`improve-*` (13). Fixtures under `rust/fixtures/closure/{diff,inspect,improve}/`.
Proven oracle-vs-oracle before the port (46/46 including the B0 smoke
cases), then oracle-vs-rust 11/11, 15/15, 13/13. Off-suite probes
verified: duplicate-ID ordering, de-duped metric diffs, `.MD`/`.markdown`
suffixes, non-canonical decision metadata casing, synonym-mapped sections
(`success criteria` → `success metrics`), unknown-with-sections verbose
scoring, surrogate-escape stdin bytes, empty stdin, invalid-UTF-8 exit 1,
and argparse error lines for every rejection path.
