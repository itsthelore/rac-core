# Heal Plan

Behavior-neutral simplification of the native-engine spike. Scope: `rust/`
only — no output byte may change. Referees: `cargo test -p rac-engine`,
CLI parity 130/130, retrieve parity 44/44, MCP parity 56/56 (primary
oracle) and 76/76 (retrieval-spec oracle), all green after every commit.
Baseline (pre-heal, commit 21b8143): all five green; `cargo clippy
--release --no-deps -p rac-engine` reports 12 warnings; `rust/` Rust tree
is 20,759 LOC. Byte-affecting improvements found during review are
recorded in the wants-spec-change list, not executed.

## Commit groups

Ordered so mechanical passes land first, shared-file restructures land
sequentially, and harness edits (which need an oracle-vs-oracle proof)
land last. Every commit message follows
`refactor(<area>): <summary> [roadmap:native-engine-spike]`.

1. **Clippy pass** — `refactor(engine): clear clippy baseline lints`
   — risk: safe. Clears all 12 baseline warnings:
   frontmatter.rs 341 (`!Range::contains`), 2072 (`Range::contains`),
   3544 (`type_complexity` → named alias), 60/63 (doc indent);
   markdown.rs 679 (`is_some_and`), 299 (`needless_range_loop`);
   validate.rs 116/123 (`eq_ignore_ascii_case` ×3), 246
   (`type_complexity` → alias); identity.rs 69 (`rfind`).
2. **Comment pass** — `refactor(engine): strip porting narration from
   comments` — risk: safe. Deletes phase notes, SEAM(phase3) markers,
   fuzz-campaign/finding citations, "ported from"/"verified against the
   oracle" provenance, walk.rs embedded Python source block, bare
   oracle-signature doc comments (relationships.rs, tools.rs), cli.rs
   wired/stub inventory. Keeps every comment stating a pinned constraint
   (ORACLE DIVERGENCE notes, rayon ordering rationale, getRules order,
   universal-newline/strict-utf8 notes, surrogateescape note,
   longest-tie-wins sort-key explanation).
3. **Dead-code pass** — `refactor(engine): remove ported-but-unused dead
   code` — risk: safe. frontmatter.rs discarded `name`/`tok` bindings;
   commands.rs `classified_type` (zero call sites); cli.rs `let _ =
   live`; classify.rs `TypeScore.display` (never read, not asserted by
   vectors); review.rs unused `_recursive` param; stats.rs
   `DecisionStat.supersedes` (computed, never emitted).
4. **Idiom pass** — `refactor(engine): replace manual idioms with std
   equivalents` — risk: safe (byte-neutral by construction).
   markdown.rs `trim_matches(is_whitespace)`→`trim`, merge duplicate
   space predicates; frontmatter.rs `map_contains`+`map_get` double scan
   → single `map_get`; resolve.rs redundant `previous.is_none()`,
   TierMatch double struct literal; pyjson.rs sentinel double lookup,
   `push_str(&format!)`→`write!`; pycompat.rs same `write!` change;
   output.rs `quote_uri` per-byte alloc → `write!`; classify.rs
   `expected()` intermediate alloc; rac-mcp main.rs redundant
   `Arg::Missing` arm, add `a_opt_list_str` accessor; graph.rs
   precompute relationship rank before sort.
5. **frontmatter dedup** — `refactor(engine): factor repeated scanner
   helpers in frontmatter` — risk: needs-care (300+ vectors referee).
   `repr_char` helper for the 21× `py_repr_str(&c.to_string())` idiom;
   merge byte-identical `scan_directive_ignored_line` /
   `scan_block_scalar_ignored_line` (drop unused `_ctx`); `skip_spaces`
   helper for the 6× space-skip loop.
6. **output dedup** — `refactor(engine): dedupe output shaping helpers`
   — risk: needs-care (all bytes pinned). `json!(opt)` for the ~10
   hand-written Option→null matches; issue-line helper shared by three
   renderers; PASS/FAIL header helper; module-level `ljust`; invalid-line
   helper; consolidate mid-file `use` imports to the top.
7. **cli dedup** — `refactor(cli): factor repeated argparse guards` —
   risk: needs-care (argparse bytes pinned; 130 CLI cases referee).
   `unrecognized(extras)` helper (10 verbatim copies); `mutex_check` →
   `Option<u8>` dropping the FlagError ceremony; `take_opt_value` helper
   for the 7× flag-value consumption pattern.
8. **relationships dedup** — `refactor(relationships): collapse
   duplicated reference-resolution loops` — risk: needs-care (pinned
   issue order). Delete local `snake` (use `spec::snake`);
   `resolve_references` becomes a wrapper over
   `resolve_references_full`; factor the empty/ambiguous/self
   classification (3 copies) into one enum-returning helper.
9. **resolve/retrieve dedup** — `refactor(retrieve): reuse
   governing-decisions path and identity-only index entries` — risk:
   needs-care (f64 paths untouched; structure only).
   `find_decisions_path_payload` Some-branch reuses
   `governing_decisions`; identity-only `entry_from_item` variant to
   drop discarded clones; shared `first_nonempty_line` primitive
   (artifact_status, stats::first_line, validate::first_value,
   relationships::is_retired — identical splitlines/strip today);
   scope-entry classification dedup (relationships ↔ retrieve) after
   verifying the two copies are behaviorally identical.
10. **budget + MCP shaping dedup** — `refactor(mcp): consume shared
    engine budget and payload shapers` — risk: needs-care (payload
    bytes pinned; both MCP suites referee). Single engine budget module
    (serialize, with_marker, truncate_items, char_len, py_slice_to,
    marker/hint constants) consumed by retrieve.rs and rac-mcp;
    engine-owned shapers for ResolvedArtifact/evidence/recency,
    search-result payload, resolution-error payloads, shared by
    output.rs and rac-mcp; one `isoformat_roundtrip` in gitinfo
    (currently ×3); `annotate_search_recency` made pub (currently ×2);
    provenance.rs reuses gitinfo `run_git`/`pathspec`/`repository_root`
    (preserving its universal-newline variant); shared
    `read_text_universal`; shared `canonical_value` (each caller keeps
    its own `first_line` — see wants-spec-change); review/stats
    `path_stem` → `identity::path_stem` after confirming reachable
    inputs agree.
11. **harness/tools heal** — `refactor(tools): heal parity harness and
    python tools` — risk: needs-care (must prove oracle-vs-oracle green
    before and after). parity-harness: shared object-walk for
    `strip_recency_json`/`mask_version`, reuse `serialize_json` for the
    scoreboard, `get_mut` instead of contains_key+Index; tools/perf.py
    dead `time_bin`, `env.pop`; tools/mcp_parity.py dead `READ_TIMEOUT`,
    hoist `import os`, `med` lambda→def; tools/gen_corpus.py unused
    `stem` param and discarded `title` return (keep the title
    computation — it consumes rng draws).
12. **CI gate** — `chore(ci): hold rac-engine to clippy -D warnings`
    — risk: safe. Remove the `|| true` carve-out in
    `.github/workflows/rust-spike.yml`; whole workspace builds under
    `clippy --no-deps -D warnings`. Followed by one dry fuzz round
    (seed 401) which must report zero new engine findings.

## Per-file item list

Tags: **safe** (mechanical, byte-neutral by construction),
**needs-care** (byte-neutral but touching pinned semantics — referee
attention), **wants-spec-change** (byte-affecting; recorded only),
**keep** (looks like a scar, is contract-cited — do not touch).

### rac-engine/src/frontmatter.rs

- safe/dup 1545,1800–2351 (21 sites): `py_repr_str(&c.to_string())` →
  `repr_char` helper. (commit 5)
- safe/dup 1881–1899, 2191–2209: byte-identical
  `scan_*_ignored_line` pair → one `scan_ignored_line`; drop unused
  `_ctx`. (commit 5)
- needs-care/dup 1731,1816,1856,1867,1882,2192: 6× space-skip loop →
  `skip_spaces`. (commit 5)
- safe/dead 1902/1916: discarded `name` binding; 2717–2718: discarded
  `tok` binding. (commit 3)
- clippy 341 (needs-care: pinned numeric guard in `float_eq_int`;
  half-open range is exactly `<`/`>=`), 2072, 3544, 60/63. (commit 1)
- safe/comment 19–21, 28–30, 2067, 3247, 3311, 3473: phase-note and
  SEAM(phase3) narration. Keep ORACLE DIVERGENCE constraint notes.
  (commit 2)
- safe/idiom 4095–4102: `map_contains`+`map_get().unwrap()` → single
  `map_get`; delete `map_contains` if unused. (commit 4)

### rac-engine/src/markdown.rs, mdhtml.rs

- safe/dup 249–257: `is_space_09_20` == `is_str_space`; merge. (4)
- clippy 679, 299. (1)
- safe/idiom 65: `trim_matches(|c| c.is_whitespace())` → `trim()`. (4)
- safe/comment mdhtml.rs 30/37/89 fuzz-campaign citations; markdown.rs
  466/526 provenance phrasing (keep the getRules order listing). (2)
- **keep** 1866–1875: `HtmlSeq::Cdata` unreachable branch —
  PORT-CONTRACT.d/03 §5 cites it; contract-pinned fidelity.
- **keep** 812–1864 oversized block rules: line-by-line ports kept
  structurally aligned with markdown-it-py for auditability; splitting
  would obscure the correspondence.
- needs-care/dup 103–120: `max_file_bytes_from` vs frontmatter
  `file_cap_from` env-read overlap — divergent return types; **skip**,
  low value.

### rac-engine/src/output.rs

- needs-care/dup 73–79, 703–706, 711–729, 1650–1653, 1694–1700,
  1716–1750, 1886–1892: hand-written Option→Value matches → `json!(opt)`
  (serde serializes None as null; all sites are plain
  Option<String/i64/bool/Vec<String>>). (6)
- safe/dup 99–116, 198–215, 305–312: issue-line pair helper. (6)
- safe/dup 93–97, 192–196: PASS/FAIL header helper. (6)
- safe/dup 1804–1811, 1926–1933, 1258–1261: code-point `ljust`. (6)
- safe/dup 1267–1278, 1302–1319: invalid-list reason line helper. (6)
- safe/idiom 425–435: `quote_uri` `write!`. (4)
- safe/idiom 873, 1059, 1368, 1556, 1668–1670: consolidate mid-file
  `use` statements. (6)
- **skip** 1078–1364 render_stats_json/human size: pinned key-order
  shaping; splitting is churn without clarity gain.

### rac-engine/src/relationships.rs

- safe/dup 162–164: local `snake` → `spec::snake`. (8)
- safe/dup 435–468 vs 1085–1118: `resolve_references` = subset of
  `resolve_references_full` → wrapper. (8)
- needs-care/dup 1019–1059: third copy of empty/ambiguous/self
  classification → shared enum helper; each loop keeps its shaping. (8)
- safe/comment 265, 328, 894, 899, 953, 959: bare oracle-signature doc
  comments. Keep 55–62 field notes and 922–929 rayon rationale. (2)
- **keep** 32–43 explicit warning arm: documents the contract's
  intrinsic warning set (§6.1).
- **skip** 658 comparator casefold precompute and 629–766 phase
  extraction: order-sensitive, low value.

### rac-engine/src/validate.rs, classify.rs, parse.rs, spec.rs

- safe/dup validate.rs 428–486: decision/prompt/design validators
  byte-identical → one `validate_typed` helper; roadmap stays separate.
  (8)
- safe/idiom validate.rs 56–58: `is_word_char` pass-through wrapper →
  direct `pycompat::is_re_word`. (4)
- clippy validate.rs 116/123, 246. (1)
- safe/dead classify.rs 23/104: `TypeScore.display` never read. (3)
- safe/idiom classify.rs 94–98: filter over borrowed sections instead of
  `expected()` alloc. (4)
- **keep** spec.rs 42–43/143 `id_field`: PORT-CONTRACT.d/04 §3.2/§8
  mandates the branch; identity.rs reads it.

### rac-engine/src/cli.rs, commands.rs

- safe/dup cli.rs (10 sites): `unrecognized arguments` guard →
  helper. (7)
- safe/dup cli.rs ~6 sites: `mutex_check` → `Option<u8>`, drop
  FlagError ceremony (keep FlagError for `set_mode` if needed). (7)
- needs-care/dup cli.rs 203–216, 591–602, 872–881, 421–452:
  flag-value consumption pattern → `take_opt_value` covering separated
  and `=`-joined forms with exact argparse error bytes. (7)
- safe/dead commands.rs 770–773 `classified_type`; cli.rs 583
  `let _ = live`. (3)
- safe/comment cli.rs 7–9, 137 phase inventory (keep 105–108 pinned
  parity-scope note); commands.rs 1–3, 476–514 "named gap" narration
  (keep surrogateescape and parallel-order notes). (2)
- **skip** full argparse scan-skeleton driver (~-60 LOC): must preserve
  exact positional-vs-option precedence, `--` cutover, first-error-wins;
  the parity basket does not provably cover every ordering edge.
  Risk/benefit says no this pass.

### rac-engine/src/resolve.rs, retrieve.rs

- needs-care/dup retrieve.rs 494–531: Some(query) branch re-inlines
  `governing_decisions` → call it. (9)
- safe/idiom resolve.rs 622–625 redundant `is_none()`; 504–517 TierMatch
  double literal. (4)
- safe/over-specific resolve.rs 301–315: identity-only
  `entry_from_item` variant; keep the constraint comment. (9)
- needs-care/dup resolve.rs 833 / stats.rs 281 / validate.rs 46 /
  relationships.rs 238: shared `first_nonempty_line`. (9)
- needs-care/dup retrieve.rs 88–139 vs relationships.rs 385–416:
  scope-entry classification + path normalization dedup after
  equivalence check. (9)
- safe/comment retrieve.rs 751. (2)
- **skip** retrieve.rs 597–660 `add_item` provenance enum: byte-neutral
  but churny, no LOC win.
- **skip** retrieve.rs 141–156 `repository_root` unification with
  validate.rs: canonicalize-vs-resolve_path differ on symlinked/edge
  paths the suites don't pin; risk/benefit says record, not do.
- **skip** retrieve.rs 100–118 `pure_posix_parts` unification with
  walk.rs `normalize_root` / commands.rs `py_path_parent`: feeds pinned
  walk display prefixes (d/09 §1.6); record, not do.
- **f64 paths untouched throughout** (PORT-CONTRACT.d/06).

### rac-engine/src/pycompat.rs, pyjson.rs, identity.rs

- needs-care/dup identity.rs 196: inline strip+upper →
  `frontmatter::normalize_id` (same operation; pinned upper-not-casefold
  preserved). (9)
- clippy identity.rs 69–72 → `rfind`. (1)
- needs-care/idiom pyjson.rs 135–138: sentinel double lookup → single
  `if let`. (4)
- safe/idiom pyjson.rs 130–148, pycompat.rs 296–307:
  `push_str(&format!)` → `write!`. (4)
- **skip** identity.rs 52–54 inert empty-body guard: mirrors oracle
  structure; harmless.

### rac-engine/src/stats.rs, review.rs, export.rs, walk.rs, gitinfo.rs

- needs-care/dup stats.rs 262–270 / review.rs 92–98: `path_stem` →
  `identity::path_stem` (corpus paths always `*.md`; verify). (10)
- safe/dead review.rs 333 `_recursive`; stats.rs 31–32/349–353/398
  `DecisionStat.supersedes` never emitted. (3)
- needs-care/dup export.rs 39–48 / stats.rs 292–301: shared
  `canonical_value`; each keeps its own `first_line` (divergence is
  load-bearing — see wants-spec-change). (10)
- safe/comment stats.rs 196/463–465, export.rs 70–86 fuzz-campaign
  provenance (keep the constraint sentences); walk.rs 3–13 embedded
  Python source (keep the landmine list). (2)
- **skip** stats.rs 250–257 bucket() O(n·m): vocab is tiny.

### rac-mcp/src/*

- needs-care/dup budget.rs 22–184 vs retrieve.rs 845–913: entire budget
  concern ×2 → one engine budget module. (10)
- needs-care/dup tools.rs 60–103 vs output.rs 1740–1781 (+ recency
  1714–1736, evidence retrieve.rs 665): ResolvedArtifact/evidence/
  recency shapers → engine-owned `to_value()`s. (10)
- needs-care/dup tools.rs 106–123 vs output.rs 1882–1905: search-result
  payload → shared engine shaper. (10)
- needs-care/dup tools.rs 37–56 vs output.rs 1704–1709:
  resolution-error/unreadable payloads → shared shaper. (10)
- needs-care/dup provenance.rs 52–75 (+commands.rs 641, review.rs 301):
  isoformat round-trip ×3 → `gitinfo::isoformat_roundtrip`. (10)
- needs-care/dup provenance.rs 200–225 vs commands.rs 671–692:
  `annotate_search_recency` → pub engine fn. (10)
- needs-care/dup provenance.rs 16–47 vs gitinfo.rs 30–63:
  `run_git`/`pathspec`/`repository_root` reuse; preserve provenance's
  universal-newline behavior explicitly. (10)
- needs-care/dup tools.rs 22–26 vs retrieve.rs 77 (+export.rs 83–85):
  `read_text_universal` shared helper. (10)
- safe/idiom main.rs 185–191 redundant Missing arm; 237–240
  `a_opt_list_str` accessor. (4)
- safe/other graph.rs 119–122: precompute relationship rank before
  sorts. (4)
- safe/comment tools.rs 20–59 source-map narration (dissolves with the
  dedup). (2/10)
- **skip** sidecar.rs `observe()`: deliberate documented seam; the
  side-channels-never-touch-stdout constraint stays.

### parity-harness/, tools/ (oracle-vs-oracle proof required)

- needs-care/dup main.rs 132–148/185–208: shared object-walk for the two
  normalizers. (11)
- needs-care/dup main.rs 214–218/639–640: reuse `serialize_json` for the
  scoreboard. (11)
- needs-care/idiom main.rs 193–200: `get_mut` over contains_key+Index.
  (11)
- safe/dead tools/perf.py 82–83 `time_bin`; tools/mcp_parity.py 45
  `READ_TIMEOUT`; tools/gen_corpus.py 172/212/252 unused `stem` param +
  discarded `title` return (keep the title computation — rng stream).
  (11)
- safe/idiom tools/perf.py 43–46 `env.pop`; tools/mcp_parity.py 52
  hoist `import os`; 346 `med` lambda→def. (11)
- **skip** main.rs 220–232 `Cow` return for `apply_normalizations`:
  harness perf only; not worth the churn.

## Wants-spec-change list

Byte-affecting fixes recorded for the post-flip spec revision. Do NOT
execute this pass.

1. **export.rs 28–36 `first_line` uses `split('\n')`; oracle uses
   `str.splitlines()`.** stats.rs ports the same oracle function
   correctly with `py_splitlines`. export diverges for any status body
   containing \r, \v, \f, \x1c–\x1e, \x85, U+2028/U+2029. Fix is
   one-line but byte-affecting; fold into the canonical_value
   unification when the spec revision lands.
2. **cli.rs 484–516 ASCII-only `py_parse_int` for argparse `type=int`
   flags** vs the canonical Unicode-Nd version in markdown.rs. Unifying
   would start accepting Unicode digits on CLI int flags. Needs a spec
   decision on whether the argparse surface matches CPython `int()`.
3. **cli.rs 711–745 `run_review --stale-after` parses via
   `raw.trim().parse::<i64>()`** — diverges from `py_parse_int`
   (underscores, py-strip whitespace set). Same spec decision as (2).

## Evidence

Every commit in this plan must leave `cargo test -p rac-engine
--release` and all four parity suites green (130/130, 44/44, 56/56,
76/76). Harness commits additionally require an oracle-vs-oracle run
proving the harness change is score-neutral. Phase 2 removes the clippy
carve-out and runs one fuzz round (seed 401, zero new engine findings).
Phase 3 re-proves everything from a clean rebuild, twice, and writes
HEAL-REPORT.md.
