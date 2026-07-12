# Heal Report

Behavior-neutral simplification of the native-engine spike (`rust/`),
executed on branch `claude/rac-engine-heal` against base `21b8143` per
`rust/HEAL-PLAN.md`. Every commit was gated on the full referee battery
— `cargo test -p rac-engine --release` plus CLI parity 130/130,
retrieve parity 44/44, MCP parity 56/56 (primary oracle) and 76/76
(retrieval-spec oracle) — and pushed only at green boundaries. No
output byte changed anywhere in the pass.

## Before / after

| Surface | Before (21b8143) | After | Delta |
| --- | ---: | ---: | ---: |
| rac-engine/src (LOC) | 18,519 | 18,310 | −209¹ |
| rac-mcp/src (LOC) | 1,578 | 1,250 | −328 |
| parity-harness/src (LOC) | 662 | 655 | −7 |
| tools/*.py (LOC) | 934 | 930 | −4 |
| **Code total** | **21,693** | **21,145** | **−548** |
| clippy warnings (rac-engine) | 12 | **0** | −12 |
| clippy gate in CI | rac-mcp + harness only; engine `\|\| true` | whole workspace `-D warnings` | carve-out removed |

¹ rac-engine absorbed the 189-line shared `budget.rs` module from
rac-mcp; its own pre-existing code shrank by ~398 lines.

Tracked diff `21b8143..HEAD -- rust/ .github/`: 32 files,
+1,002/−1,206 (the +343-line HEAL-PLAN.md accounts for most of the
insertions; code-only movement is the −548 above). 14 commits.

## Commit list

1. `5fb9331 docs(engine): add heal plan scar map` — Phase 0 deliverable
   (108 findings from 12 parallel area reviews).
2. `f1aa3a2 refactor(engine): clear clippy baseline lints` — all 12
   warnings, std-equivalent rewrites only.
3. `c957e99 refactor(engine): strip porting narration from comments` —
   phase notes, SEAM markers, fuzz-campaign citations, embedded oracle
   source; every pinned-constraint comment kept. Comment-only diff.
4. `65a2a4a refactor(engine): remove ported-but-unused dead code` —
   discarded bindings, zero-call-site helper, never-read fields/params.
5. `c5f90d3 refactor(engine): replace manual idioms with std
   equivalents` — trim, single-lookup guards, write! over
   push_str(format!), collapsed duplicate arms, precomputed sort rank.
6. `8de9c05 refactor(engine): factor repeated scanner helpers in
   frontmatter` — repr_char (21 sites), merged ignored-line scanners,
   skip_spaces (6 sites).
7. `6e5d343 refactor(engine): dedupe output shaping helpers` —
   json!(opt) over hand-written null matches, shared issue-line /
   pass-fail / ljust / invalid-reason helpers; output.rs −87 lines.
8. `4473840 refactor(cli): factor repeated argparse guards` —
   unrecognized(), mutex_check → Option<u8>, take_opt_value; byte
   equality re-checked against the pre-edit binary on 12 edge
   orderings.
9. `6299bb3 refactor(relationships): collapse duplicated
   reference-resolution loops` — spec::snake reuse, wrapper over
   resolve_references_full, one classification enum for the
   empty/ambiguous/self decision.
10. `477d327 refactor(retrieve): reuse governing-decisions path and
    shared scope helpers` — governing_decisions call over the inlined
    copy, identity-only index entries, pycompat::first_nonempty_line
    (4 copies), scope-entry classification shared from relationships.
11. `8ba1d94 refactor(mcp): consume shared engine budget and payload
    shapers` — the big seam: one engine budget module (was ×2), one
    isoformat_roundtrip (was ×3), one annotate_search_recency (was
    ×2), shared pathspec / run_git_text, engine-owned shapers for
    resolved-artifact / evidence / recency / search-result /
    resolution-error payloads, pycompat::read_text_universal,
    identity::path_stem everywhere; net −268.
12. `52532ec refactor(engine): share the canonical-value vocabulary
    match` — casefold-match tail in spec.rs; each caller keeps its own
    first-line extraction.
13. `e83bb70 refactor(tools): heal parity harness and python tools` —
    shared normalizer traversal, serialize_json reuse, get_mut over
    contains_key+index, dead Python; proven score-neutral
    oracle-vs-oracle (before AND after, scoreboards byte-identical),
    gen_corpus regeneration byte-identical across two seeds.
14. `0cc9de7 chore(ci): hold the whole rust workspace to clippy -D
    warnings` — carve-out removed.

## Verification

Executed by an independent adversarial verifier from a clean rebuild;
overall verdict **PASS**, no discrepancy attributable to the heal.

- **Clean rebuild** (`cargo clean` — 279 MiB removed — then
  `cargo build --release`): success in 55s, zero warnings.
  Workspace-wide `cargo clippy --release --no-deps -- -D warnings`
  (all four crates): exit 0, zero warnings.
- **cargo test -p rac-engine --release**: 55 passed, 0 failed across
  14 test binaries + doc-tests. The single ignored test is the
  pre-existing opt-in differential driver in
  `frontmatter_differential.rs` (unchanged by the heal).
- **All four referee suites, twice each, from the clean rebuild**:
  CLI 130/130 + 130/130, retrieve 44/44 + 44/44, MCP 56/56 + 56/56,
  MCP full 76/76 + 76/76 — each pair's scoreboards byte-identical
  (per-case records, so the clean diffs are a real determinism proof).
- **Fuzz round** (`difffuzz.py --seed 401 --rounds 1 --batch 800
  --jobs 8`): **zero new engine findings**. 64 divergent inputs, all 30
  catalogued repros are the documented oracle-crash divergence class
  (the Python oracle crashes; the engine does not) — pre-existing
  behavior, not introduced by the heal. A verifier-initiated
  fresh-seed round (seed 7777) was likewise clean for everything it
  filed before being cut short: 25 repros, every one oracle-crash
  class, zero engine findings.
- **Pinned-asset audit**: `git diff 21b8143..HEAD` changes **zero
  .json files anywhere** — parity-cases*.json, mcp-parity-cases.json,
  fixtures/, spec JSONs, fuzz/pinned, and all vector JSONs untouched;
  the only file outside `rust/` is
  `.github/workflows/rust-spike.yml`. The single test-file edit is the
  `retrieve_vectors.rs` import path following the budget-module move
  (no assertion changed).
- **Adversarial spot checks** (nine, off-basket inputs): merged
  scan_ignored_line error bytes on hand-made malformed YAML;
  json!(None)→null in rendered output; full-corpus byte-compares of
  validate/relationships/stats/review/resolve/schema against the
  oracle; export identical after the documented version mask;
  vocabulary case/whitespace edges through the shared canonical_value;
  13 argparse flag-edge invocations; oracle-crash classification of a
  dirty-cwd resolve divergence; audit that no harness comparison logic
  was weakened; code-level review of the risky merges (budget
  py_slice_to superset, classify_reference guards, gitinfo
  universal-newline split, decorate-sort stability). All byte-identical
  or pre-existing-at-baseline.
- **Commit hygiene**: `git log 21b8143..HEAD` shows exactly one
  identity — Tom Ballard <tom@armytage.co> — on both author and
  committer of all 14 commits; attribution grep over every commit body
  is empty.

## Deliberately NOT simplified

Contract-pinned (kept on purpose — do not "clean up" later without a
spec change):

- `spec.id_field` dead-at-value-level branch — PORT-CONTRACT.d/04
  §3.2/§8 mandates porting it; identity.rs reads it.
- `HtmlSeq::Cdata` unreachable variant in markdown.rs —
  PORT-CONTRACT.d/03 §5 cites the fall-through.
- The oversized markdown block rules (rule_blockquote, rule_list,
  rule_reference, match_open_close_tag_line, 120–180 lines each) —
  kept structurally aligned with markdown-it-py so parity remains
  auditable line-against-line.
- All f64 accumulation order, skip-vs-add-zero, py_round placement,
  and ln usage in resolve.rs/retrieve.rs (PORT-CONTRACT.d/06).
- pycompat/pyjson table-driven semantics (casefold, repr, splitlines
  tables) — the tables are the contract.

Risk/benefit said no this pass:

- The full argparse scan-skeleton driver for the ten `run_*` functions
  (~−60 LOC): exact positional-vs-option precedence, `--` cutover, and
  first-error-wins ordering are not provably covered by the 130-case
  basket; the smaller helpers landed instead.
- `repository_root` unification (retrieve's canonicalize+ancestors vs
  validate's resolve_path walk): differ on symlinked/edge paths the
  suites don't pin. Same for provenance's `repository_root` over its
  normalizing run_git (differs only for a toplevel containing a bare
  CR).
- `pure_posix_parts` / walk `normalize_root` / `py_path_parent`
  unification: feeds pinned walk display prefixes (d/09 §1.6).
- `retrieve::add_item` provenance-carrier enum: byte-neutral but
  churny, no LOC win.
- rac-mcp `sidecar::observe()` no-op seam: documented deliberate
  audit-port seam; the stdout-purity constraint stays with it.
- render_stats_json/human size, validation_from_rows phase extraction,
  comparator casefold precompute, bucket() set lookup: order-sensitive
  or trivial; churn outweighed clarity.
- identity.rs `first_value_list_stripped` inert empty-body guard:
  mirrors the oracle's structure, harmless.
- relationships explicit warning-code match arm: redundant with the
  wildcard but documents the contract's intrinsic warning set (§6.1).

## Wants-spec-change list (input to the post-flip spec revision)

Byte-affecting fixes deliberately NOT made; each needs a contract
decision first.

1. **export.rs `first_line` splits on `'\n'`; the oracle's
   `_first_line` uses `str.splitlines()`.** stats.rs ports the same
   oracle function correctly via py_splitlines. export therefore
   diverges from the oracle for status bodies containing \r, \v, \f,
   \x1c–\x1e, \x85, U+2028/U+2029. One-line fix once the spec revision
   authorizes the byte change; the shared canonical_value tail (commit
   12) already isolates it.
2. **cli.rs ASCII-only int parsing for argparse `type=int` flags** vs
   the canonical Unicode-Nd `py_parse_int` in markdown.rs (used by
   file caps). Unifying would start accepting Unicode digits on
   `--top-k`/`--budget`-style flags. Needs a decision on whether the
   argparse surface matches CPython `int()`.
3. **`run_review --stale-after` parses via `raw.trim().parse::<i64>()`**
   — rejects underscores and py-strip whitespace forms a true CPython
   `int()` accepts. Same decision as (2).
4. **Argparse edge-ordering divergences found while probing commit 8**
   (pre-existing at 21b8143, outside the 130 pinned cases):
   `find q --decisions --type` fires the mutex error before the
   missing-value error where argparse orders them the other way
   around; `--tag -` and `--client -` bare-dash consumption differs
   from the oracle. Candidates for new pinned cases + fixes in the
   spec revision.
5. **The oracle-crash divergence class should close from the Python
   side** (RAC-KXBPS7SRM6ZB). The Python engine crashes with a raw
   traceback on Markdown with malformed frontmatter (e.g. unhashable
   YAML mapping keys) anywhere in its walk — observed making `rac new`
   unusable in a checkout carrying the fuzz repro fixtures. The Rust
   engine already handles every catalogued input gracefully. Hardening
   the oracle changes bytes on inputs the port contract currently
   classifies as oracle-crash divergences, so the fix, the spec's
   divergence catalog, and new pinned regression cases must move
   together in the spec revision.

## Evidence trail

Referee scoreboards for the final verification live under
`/tmp/v1cli`..`/tmp/v2mf` in the session container; per-commit gate
logs under `/tmp/referee-c1`..`/tmp/referee-c11`. The fuzz repros are
under `rust/fuzz/findings2/` (gitignored, oracle-crash class only).
