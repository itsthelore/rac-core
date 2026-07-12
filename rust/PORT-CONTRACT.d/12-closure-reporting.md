# 12 — Closure reporting: portfolio, coverage, decisions-for

Scope: the B1 read-only corpus-reporting commands ported for
roadmap:native-cli-closure — `rac portfolio`, `rac coverage`,
`rac decisions-for`. Every claim below was verified against the oracle
(`.venv-oracle/bin/rac`, `0.1.dev50+g21c8be403`, Python 3.11.15). Source
files: `src/rac/cli.py` (`cmd_portfolio`/`cmd_coverage`/
`cmd_decisions_for`), `src/rac/services/{portfolio,coverage,scope}.py`,
`src/rac/output/{human,json}.py`. Rust: `rac-engine/src/portfolio.rs`
(pre-existing — built for review), new `coverage.rs`, `retrieve.rs`
(`decisions_for_path`/`ScopeLookupResult`/`scope_lookup_value`),
`commands.rs` (`cmd_portfolio`/`cmd_coverage`/`cmd_decisions_for`),
`cli.rs` (`run_portfolio`/`run_coverage`/`run_decisions_for`),
`output.rs` renderers.

Shared conventions (see 09 §0): one trailing `\n` from `print()`; ANSI
color gated on `sys.stdout.isatty()` (the harness pipes, so plain bytes);
`✓ ✗ ! ↳` and the em-dash are raw UTF-8. All three are read-only pure
functions of corpus bytes (+ `.rac/config.yaml` overrides for portfolio):
no git, no writes, no timestamps, no minted ids, no interactivity.
`not a directory: <dir>` → stderr `rac: not a directory: <dir>`, exit 2,
checked in the handler AFTER argparse (so parse errors win).

---

## 1. `rac portfolio <directory> [--json] [--top-level|--recursive]`

### 1.1 Argv surface
`directory` is a REQUIRED positional — unlike the sibling index/export
parsers (no `nargs='?'`; do not copy their default-`'.'` pattern).
Parents: version_parent + json_parent + scope_parent (`--top-level`
sets `recursive=False`; `--recursive` affirms the default). Missing
positional: `rac portfolio: error: the following arguments are
required: directory`, exit 2. Extra positionals/unknown flags → the
TOP-LEVEL parser's `rac: error: unrecognized arguments: ...`, exit 2.

### 1.2 Semantics (`build_portfolio_summary` — already in portfolio.rs)
Exit 0 ALWAYS on a real directory: happy path, empty corpus, invalid
artifacts — portfolio REPORTS health, it never gates. One walk feeds
per-artifact validation (with ADR-053 overrides via `load_overrides`),
completeness (recommended slots), the relationship summary AND the full
relationship-validation gate (`validation_from_rows(...).ok` →
`relationships_ok`), attention items, and the health score
`py_round(100·(0.5·validity + 0.25·completeness + 0.25·rel_integrity))`
(each sub-score 1.0 when its denominator is 0). `by_type` is pre-seeded
to the five spec types + `unknown` = 0 in declaration order, then
incremented; unknown docs are counted but neither validated nor
completeness-scored (paths land in `unknown_paths`). Attention sort:
(error<warning, path, code). Rel-issue attention message:
`{Label.title()} {phrase}: {target}` with phrase by issue code
(not-found → `references missing artifact`, ambiguous → `has an
ambiguous reference to`, self → `references itself via`).

### 1.3 Output
- HUMAN: `Repository Summary` / `==================` / blank /
  `Directory:  <raw argv dir>` / `Artifacts:  <n>` / blank / `By Type` /
  `-------` / blank, then ONLY count>0 rows `  {type.title():<14} {n}`;
  `Validation` (`  Valid:    n` / `  Invalid:  n`), `Completeness`
  (`  {ratio:.0%} ({filled} / {slots} recommended slots filled)` —
  `py_format_percent0`), `Relationships` (Total/Valid/Broken/Orphaned +
  `  Coverage: {:.0%}`); then either `Attention (<n> items)` with per
  item `  ✗ <id>` (error) / `  ! <id>` (warning) + `      <message>`, or
  `✓ No attention items.`; then `Health Score` / `  <score> / 100`
  (color threshold ≥80 green ≥60 yellow, byte-invisible when piped);
  empty corpus appends blank + `No artifacts yet — create your first
  with: rac quickstart`.
- JSON: `json.dumps(to_dict(), indent=2)` (ensure_ascii=True), key order
  schema_version, directory, recursive, empty, artifacts{total, by_type
  (all six keys, zeros included), unknown_paths}, validation{valid,
  invalid}, completeness{recommended_slots, filled, ratio},
  relationships{total, valid, broken, orphaned, coverage}, attention[]
  {path, identifier, severity, code, message}, health{score},
  validation_status{artifacts_ok, relationships_ok, ok}. `ratio` and
  `coverage` are `round(x, 4)` floats in Python repr (`0.8608`, `1.0` —
  `py_float` + pyjson), never ints.

## 2. `rac coverage [DIRECTORY] [--json]`

### 2.1 Argv surface
DIRECTORY optional positional, default `'.'`. Parents: version_parent +
json_parent ONLY — NO `--top-level`/`--recursive` (always recursive),
NO `--sarif`. An unknown flag (`--top-level`, `--sarif`) bubbles to the
TOP-LEVEL parser → `rac: error: unrecognized arguments: ...`, exit 2
(the main `usage: rac ...` shape, not a coverage-specific usage).

### 2.2 Semantics (`analyze_coverage` — new coverage.rs)
Exit 0 ALWAYS on a valid run (`cmd_coverage` hardcodes EXIT_OK) — gaps
are advisory, never a build failure. Identity index = (path, id, type)
per corpus item, unknown docs included (they never gap). Over
`relationships_from_corpus`: skip unresolved (`resolved_path` None —
covers external edges and broken refs) and self edges
(`resolved_path == source_path`); collect resolved incoming SOURCE
types and outgoing TARGET types per path. Gap rules (edge-typed):
unscheduled = requirement with no incoming `roadmap`; unapplied =
decision with no incoming `requirement`/`roadmap`; unscoped = roadmap
with no outgoing `requirement`. Sort: gap-class order
{unscheduled:0, unapplied:1, unscoped:2}, then ascending path.

### 2.3 Output
- HUMAN: `Traceability coverage — <raw dir>` + blank; no gaps →
  `✓ No coverage gaps — every artifact has its expected traceability
  edge.`; else up to three groups in fixed order, each
  `<heading>: <count>` + per gap `  <id>  <path>` + trailing blank line,
  headings exactly `Unscheduled requirements (no roadmap schedules
  them)` / `Unapplied decisions (no requirement or roadmap applies
  them)` / `Unscoped roadmaps (reference no requirement)`; final line
  `<total> coverage gap[s] (<u> unscheduled, <a> unapplied, <s>
  unscoped) — advisory, not a build failure.` (singular `gap` iff
  total==1).
- JSON: **`json.dumps(indent=2, ensure_ascii=False)`** — raw UTF-8
  (pyjson `dumps_indent2_no_ascii`, added for this command; portfolio
  and decisions-for stay ensure_ascii=True). Shape:
  {schema_version:"1", directory, gaps:[{path, id, type, gap, missing}],
  summary:{unscheduled, unapplied, unscoped, total}}. `missing` text per
  class: `no roadmap schedules this requirement` / `no requirement or
  roadmap applies this decision` / `this roadmap references no
  requirement`.

## 3. `rac decisions-for <path> [directory=.] [--top-level|--recursive] [--json]`

### 3.1 Argv surface
`path` required positional (repo file/dir; need not exist on disk —
pure string matching); `directory` optional positional default `'.'`.
`--top-level`/`--recursive` declared inline (NOT scope_parent), same
semantics. Missing `path`: `rac decisions-for: error: the following
arguments are required: path`, exit 2. Extra positionals → top-level
`unrecognized arguments`, exit 2.

### 3.2 Semantics (`scope.decisions_for_path` — retrieve.rs)
Exit 0 for EVERY valid query — governed, ungoverned in-repo, and
outside-repository paths all succeed (REQ-004). The whole scope engine
was already ported for the MCP `find_decisions` path mode and is
byte-identical to the CLI service (documented in
`derived_cache.governing_decisions`): `repository_root` (nearest
ancestor `.rac/config.yaml`), `normalize_query` (POSIX repo-relative;
`..`/outside-root → None), `scope_rows_from_items` (live decisions with
declared `## Applies To`), `entry_covers` (segment-aware globs),
first-covering-entry-in-declared-order wins, sort by
`(py_casefold(id), path)`. The port adds `decisions_for_path(directory,
path, recursive)` threading the CLI's `--top-level` through the walk —
the pre-existing `find_decisions_path_payload` HARDCODED recursive=true
and now delegates with `recursive=true` (byte-identical payload). The
walk is skipped entirely for an outside-repository query.

### 3.3 Output
- HUMAN governed: per decision `{id:<id_w}  {status or '—':<status_w}
  {title or '—'}` then `{' '*id_w}  {' '*status_w}  ↳ applies to:
  {matching_entry}`; then blank line and `<n> decision(s) govern
  '<query>'.` (query via Python repr — `py_repr_str`). Widths are
  code-point `str.ljust`; the status column is padded even though title
  follows.
- HUMAN empty in-repo: `No decisions declare scope over '<query>'.`
  (query = normalized POSIX repo-relative form).
- HUMAN outside repo: `'<raw stripped input>' is outside the repository
  — no governing decisions.`
- JSON: `json.dumps(indent=2)` (ensure_ascii=True) of
  {schema_version:"1", query, in_repository, decisions:[{id, title,
  status, path, matching_entry}]} — the same `ScopeLookupResult`
  payload the MCP `find_decisions` path argument serializes (ADR-031);
  `query` is the raw stripped input when outside the repository.

---

## 4. Parity evidence

`rust/parity-cases-closure.json`: `portfolio-*` (11), `coverage-*` (12),
`decisions-for-*` (13). Fixtures under
`rust/fixtures/closure/{portfolio,coverage}/` (attention corpus with an
invalid artifact + broken reference; one corpus per coverage gap class,
a clean fully-traced corpus, and a mixed corpus with a non-ASCII path
pinning ensure_ascii=False); decisions-for cases run against the live
`rac/` corpus (repo root carries `.rac/`). Proven oracle-vs-oracle over
the whole closure file (82/82) before the port, then oracle-vs-rust
11/11, 12/12, 13/13. Pinned nuances: portfolio's required positional,
`--top-level` empty-corpus branch (hint + 100/100), float reprs in JSON,
error-vs-warning attention icons; coverage's advisory exit 0, top-level
argparse bubble for `--top-level`, singular/plural summary, group order
and within-group path sort, default-`'.'` directory; decisions-for's
multi-row casefold+path sort and column alignment, outside-repo raw
query, `--top-level` recursion threading, and not-a-directory exit 2.
