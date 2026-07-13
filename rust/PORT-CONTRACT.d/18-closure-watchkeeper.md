# 18 — Closure watchkeeper

Scope: the B7 command ported for roadmap:native-cli-closure —
`rac watchkeeper`, the product-knowledge review surface (ADR-043
revision materialization). Every claim below was verified against the
oracle (`.venv-oracle/bin/rac`, `0.1.dev50+g21c8be403`, Python
3.11.15). Source files: `src/rac/cli.py` (`cmd_watchkeeper` + parser),
`src/rac/services/{watchkeeper,compare,intent,revisions,diff}.py`,
`src/rac/output/{human,json,github}.py`. Rust: new
`rac-engine/src/revisions.rs` (git archive materialization + a minimal
in-process tar reader), `compare.rs` (`load_state`/`compare_states`),
`intent.rs` (`analyze_intent`), `watchkeeper.rs` (report assembly +
review verdict), plus `output.rs` (human/json/github renderers and
`watchkeeper_annotations`), `commands.rs` (`cmd_watchkeeper`), `cli.rs`
(`run_watchkeeper`, added to the order-aware set). `diff.rs` (B1) is
consumed as-is for the requirement-level diff.

Shared conventions (see 09 §0): one trailing `\n` from `print()`; ANSI
gated on `sys.stdout.isatty()`; `✓ ✗ ! ·`, the arrow ` → ` (U+2192),
the em-dash, and the github markers `⚠️ ℹ️ ✅` are raw UTF-8; `--json`
output is `json.dumps(..., indent=2)` (ensure_ascii).

---

## 1. Argv surface

`rac watchkeeper [directory] [--base REV] [--head REV]
[--format {human,json,github}] [--json] [--fail-on {error,warning,none}]
[--no-annotate] [--version]`.

- `directory` is an OPTIONAL positional, default `None` → resolved in
  the handler to `'rac'` when `Path('rac').is_dir()` else `'.'`
  (ADR-018). The label in every output surface is the argv string as
  given (trailing slash preserved: `Directory:  rac/`).
- `--base` default `'main'`; `--head` default `None` (= the working
  tree at `directory`). Each may name an EXISTING DIRECTORY (used
  as-is, no git at all) or a git revision (any committish: branch,
  tag, `HEAD^`, sha).
- `--json` is an alias that OVERRIDES `--format` (json wins even
  against an explicit `--format github`, either order).
- `--no-annotate` (dest `annotate`, store_false) only affects github
  format's stderr annotations.
- Order-awareness (measured): `--format`/`--fail-on` choice-validate
  when their VALUE is consumed and a missing `--base`/`--head` value
  errors at its own position — each beats a LATER `--version`
  (`watchkeeper --format bogus --version` → exit 2) while an earlier
  `--version` wins (`--version --format bogus` → version, exit 0). A
  bad directory string and extra positionals DEFER (`bogusdir
  --version` and `rac/ extra --version` both print the version), so
  `watchkeeper` is in `cli.rs`'s order-aware set. Unknown flags defer
  to the root parser's `unrecognized arguments`.

## 2. Exit codes

- 0: success under the failure policy.
- 1 (`EXIT_VALIDATION_FAILED`), policy `--fail-on` (v0.12.2): `none` →
  always 0; else 1 when `review_recommended` (recommendations
  non-empty); else with `warning` also 1 when ANY finding has severity
  `warning`. The recommending set is narrow: `validation_regression`
  (newly-invalid non-empty), `broken_relationship` (new relationship
  issues), and the five intent codes `specificity_regression`,
  `constraint_weakened`, `constraint_removed`,
  `acceptance_criteria_removed`, `success_measures_removed`.
  `unlinked_scope`/`ambiguity_introduced` are warnings that do NOT
  recommend (fail only under `--fail-on warning`);
  `relationship_impact` is info and never fails.
- 2 (`_usage_error`, stderr `rac: <msg>`): `not a directory: <dir>`
  (checked BEFORE any git work); `not a git repository: <dir>` /
  `git executable not found` (`NotAGitRepository`); `unknown
  revision: <rev>` (`RevisionNotFound`). Base resolves before head, so
  a bad base wins the message when both are bad.

## 3. Semantics

### 3.1 Revision materialization (`revisions.rs`)
Three read-only git subprocess forms, all `capture_output`:
`git rev-parse --show-toplevel` (cwd = the CORPUS directory);
`git rev-parse --verify --quiet <rev>^{commit}` (cwd = repo root, rc≠0
→ RevisionNotFound); `git archive --format=tar <rev> -- <pathspec>`
(cwd = repo root). The pathspec is
`os.path.relpath(os.path.abspath(directory), root)` (lexical —
`pycompat::py_relpath`/`py_abspath`), `'.'` when the corpus IS the
root. A NONZERO archive exit is NOT an error: the subpath does not
exist at that revision and an EMPTY corpus is materialized (the
fresh-adoption "everything added" comparison). The tar stream is
extracted into a `rac-watchkeeper-`-prefixed temp dir (std temp root,
removed on guard drop); the corpus dir is `tmp/<subpath>`
(`mkdir -p`). The temp path never appears in any output — all reported
paths are corpus-relative — so no seam or mask is needed. The Rust tar
reader handles ustar name+prefix, git's pax global header (`g`,
skipped), pax `path=` overrides (`x`), GNU longname (`L`), dirs,
regular files, and best-effort symlinks; absolute/`..` entries are
skipped where tarfile's `filter="data"` would raise (git never emits
them).

### 3.2 State loading (`compare.rs::load_state`)
One walk per side (`corpus_items`), then: portfolio summary (counts
valid/invalid WITHOUT the ticketing provider), resolved relationship
edges, relationship-validation issues, and PER-FILE statuses via the
directory-validation rules (WITH the provider + ADR-053 overrides;
unknown type → `skipped`). Artifacts key on
`os.path.relpath(display_path, directory)`; raw file BYTES are the
modified-detector (== the oracle's `read_text` string equality for the
valid UTF-8 the corpus contract requires). Issue refs are the
five-field tuple (code, corpus-relative path — duplicate-identifier
findings join their SORTED paths with `", "` — relationship, target,
identifier), sorted by (code, path, relationship, target, identifier)
with `None` → `""`.

### 3.3 Comparison (`compare_states`)
Changes: added (head−base), modified (raw bytes differ; requirement
diff via `diff.rs`, omitted when empty), removed (base−head), each
path-sorted, then ordered added→modified→removed. Renames report as
removed+added. `newly_invalid` = invalid in head and not-invalid-or-
absent in base (an ADDED invalid file counts); `newly_valid` =
invalid→valid on the same path. Relationship delta = the issue-ref set
differences, sorted; summaries come from each portfolio. Stats
`by_type` iterates head's portfolio order (the six standard slots)
then base-only extras; human output prints only rows with a nonzero
side plus `Total`.

### 3.4 Intent (`intent.rs`)
Pure token-boundary checks (`\b<term>\b` IGNORECASE ≡ Python `\w`
boundary table + ASCII-case-insensitive match; `\d` ≡ the `re_digit`
table): specificity regression (digits→none on a modified
requirement), ambiguity introduced (the pinned 10-term vocabulary,
matches reported sorted and quoted), constraint weakened
(mandatory `must/shall` → none + hedge `should/may/could`; note the
VALIDATOR only accepts UPPERCASE normative keywords, so lowercase
weakening usually also flags a validation regression), constraint
removed (removed requirement, or every mandatory requirement of a
removed artifact), acceptance-criteria/success-measures section
emptied (casefolded section keys, `strip()`-nonempty), relationship
impact (info; incoming resolved-edge sources, `sorted(set(...))`
count and evidence), unlinked scope (added known-type artifact with no
outgoing declarations and no incoming resolved edges). Findings sort
by (severity≠warning, code, path, detail).

### 3.5 Report + verdict (`watchkeeper.rs`)
Reason codes dedupe in order: `validation_regression`,
`broken_relationship`, then finding-driven codes in finding order;
each carries its Core-owned sentence (e.g. "A mandatory requirement
was weakened.").

## 4. Output surfaces

- **human**: bold `RAC Watchkeeper` / `===============`, `Directory:`
  / `Comparing:  <base> → <head>` (two spaces after the label),
  sections Changed Artifacts (`  + <path>  (<type>)`, icons `+ ~ -`;
  else `  No product artifact changes detected.`), Validation
  (`  Valid:    <b> → <h>`, newly invalid red `✗` / newly valid green
  `✓`), Relationships (new issues yellow `!` with
  `<path> — <Label> reference '<target>' (<code>)`, or
  `<identifier-or-path>: <code>` for relationship-less findings;
  resolved green `✓`), Repository Changes (`str.title()` type names
  ljust-14), optional `Findings (N)` (`--------` fixed 8 dashes;
  warning `!` yellow, info `·`; detail + diff-style evidence indented
  6), Review (yellow `Review recommended.` + `    · <reason>  [<code>]`
  or green `✓ Nothing requiring attention.`).
- **--json**: `report.to_dict()` via `json.dumps(indent=2)`,
  schema_version "1"; keys directory/base/head/changes[]/validation/
  relationships/stats/findings[]/review. `coverage` is a FLOAT (`0.0`,
  `0.5` — `pyjson::py_float`); a modified change carries `diff` (the
  `rac diff` JSON shape, requirements with their `line`) only when
  non-empty; statuses are `valid|invalid|skipped|null`.
- **--format github**: Markdown step-summary on STDOUT (`# RAC
  Watchkeeper`, change + delta tables, `Newly invalid:` / `New
  relationship issues:` lists, `## Findings (N)` with `⚠️`/`ℹ️`,
  `## Verdict` with `**Review recommended.**` reasons or `✅ Nothing
  requiring attention.`) AND workflow-command annotations on STDERR in
  the SAME invocation (suppressed by `--no-annotate` → stderr 0
  bytes): `::error` for newly-invalid (`validation_regression:
  Artifact became invalid.`), new relationship issues
  (`broken_relationship: reference '<target>' (<code>)` — a `None`
  target prints the LITERAL `None`, and a duplicate-identifier
  finding annotates the FIRST of its `", "`-joined paths) and
  recommending findings; `::warning` for other warnings; `::notice`
  for info. Annotation paths are repo-relative:
  `PurePosixPath(directory) / corpus_relative` (`walk::py_join`).

## 5. Harness

`parity-harness` gained the per-case `compare_stderr: true` flag —
stderr is normalized with the case's declared normalizations and
byte-refereed exactly like stdout (github-mode annotations, `rac:`
usage errors, and empty-stderr proofs are contract bytes). Proven
neutral: 130/130 CLI and the pre-existing closure cases
oracle-vs-oracle before any watchkeeper case landed; smoke case
`closure-smoke-compare-stderr-usage-error` pins the feature on a
previously-ported command. Argparse-error cases do NOT set the flag
(usage bodies stay out of scope, 01 §decision 9).

## 6. Divergences (documented)

- `re.IGNORECASE` can match exotic non-ASCII case pairs (Kelvin sign
  → `k`); the Rust matcher is ASCII-case-insensitive over the pinned
  ASCII vocabulary. Unreachable divergence for the term lists.
- A non-UTF-8 corpus file crashes the oracle's `read_text` re-read
  (UnicodeDecodeError traceback); Rust compares raw bytes and
  degrades (PORT-CONTRACT decision 3). Closure fixtures stay healthy.
- tarfile `filter="data"` RAISES on absolute/`..`/escaping archive
  entries (oracle traceback); the Rust reader skips them. Git-produced
  archives never contain such entries.
- Non-`NotFound` git spawn failures: the oracle tracebacks; Rust
  degrades to the `git executable not found` usage error.

## 7. Parity coverage

31 `watchkeeper-*` cases in `parity-cases-closure.json` (all
oracle-vs-oracle proven before the port, then oracle-vs-Rust green),
plus the harness smoke case: added artifact in human/json/github/
github-no-annotate (stderr refereed on all four), `--fail-on
warning`/`none`, validation regression in human/json/github (three
`::error` annotations), the five-finding intent battery human+json
(diff payload with requirement lines), dir-vs-dir removal with broken
references + `relationship_impact` info (human + github `::error`/
`::notice` mix, no git), resolved issues human+json (coverage `0.5`),
newly-valid, duplicate-identifier human+github (`reference 'None'`,
first-path annotation), `--head main` no-changes double
materialization, fresh adoption (subpath absent at rev → empty base),
`.` corpus at the repo root, default-directory resolution, unknown
base/head revision, not-a-directory, not-a-git-repository (all four
error stderr bytes refereed), and the argparse ordering set
(`--format`/`--fail-on` choice beats `--version`, missing `--base`
value beats `--version`, `--version` beats bad dir / extra
positional).
