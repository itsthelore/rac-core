# 08 — Goldens, Fixtures & Git-Derived Output

Scope: the reusable test/fixture assets for the Rust port, the exact conventions
that make CLI output byte-stable (or deliberately unstable), and a complete
enumeration of the **git-dependent output fields** the parity harness must
control or strip. Paths are repo-relative to `/home/user/rac-core`.

Everything here was read from the frozen oracle under `src/` and `tests/` and,
where cheap, verified by running `.venv-oracle/bin/rac`.

---

## 1. `tests/test_golden.py` — the byte-pinned CLI contract

This is the single most reusable asset: 40 CLI invocations, each with a
committed golden capturing **stdout bytes** and an **expected exit code**. Any
Rust port should replay these exact argv lists and diff stdout byte-for-byte.

### 1.1 How bytes are pinned

- Golden files live in `tests/golden/<name>.txt`, read/written with
  `encoding="utf-8"`. Comparison is `out == golden.read_text(...)` — exact
  string equality, no normalization, no trailing-whitespace tolerance.
- Only **stdout** is captured (`capsys.readouterr().out`). stderr is explicitly
  out of scope for goldens (watchkeeper `--format github` streams annotations to
  stderr; those are pinned separately in `tests/test_watchkeeper.py`).
- Refresh mechanism: env `RAC_UPDATE_GOLDEN=1` rewrites goldens. The Rust
  harness does not need this, but note the goldens are authoritative only for
  the exact repo git state they were captured against for any git-touching case
  (none of the 40 golden cases touch git recency after stripping — see §1.3).

### 1.2 Determinism seams the test sets (CRITICAL — the port must replicate)

The test forces these before every invocation. A Rust reimplementation must
behave *as if* these are set, because the goldens were captured under them:

1. **`monkeypatch.chdir(REPO_ROOT)`** — cwd is the repo root. All fixture paths
   in argv are repo-relative (`tests/fixtures/...`, `examples/...`), and those
   exact relative strings appear verbatim in output (e.g. `"file":
   "tests/fixtures/valid/feature.md"`). The port must echo the path **exactly as
   passed on argv** — no absolutization, no normalization, no separator
   rewriting. (Paths flow through unchanged; on Linux they stay `/`-separated.)
2. **`rac.output.human._USE_COLOR = False`** — forces plain output. In the real
   binary this variable is `sys.stdout.isatty()` evaluated **at module import
   time** (`src/rac/output/human.py:93`). So: **color is emitted only when
   stdout is a TTY.** There is **no** `NO_COLOR` / `FORCE_COLOR` / `CLICOLOR`
   env check — piping (non-TTY) already yields plain output. The Rust port
   should key color off `stdout.is_terminal()` and, for parity/goldens, emit
   plain (no ANSI) whenever not a TTY. Color codes used: `_yellow`, `_red`,
   etc. (ANSI SGR) — only when `_USE_COLOR`.
3. **`rac.services.migrate._DEFAULT_ID_GENERATOR = lambda key: f"{key}-00000000TEST"`**
   — deterministic ID minting for the `migrate` dry-run cases. Real minted IDs
   are ULID/Crockford-base32 and time+random-derived; the golden pins the suffix
   `00000000TEST`. The port needs an injectable ID generator seam for parity.
   See golden `migrate_dry_run_json.txt`: `"id": "RAC-00000000TEST"`.
4. **`monkeypatch.setenv("XDG_STATE_HOME", "tests/fixtures/telemetry/state")`** —
   a **relative** state home so the `mcp-stats` log path prints
   machine-independently. Golden `mcp_stats_human.txt` literally contains
   `Log: tests/fixtures/telemetry/state/rac/guide-telemetry.jsonl`. Only the
   `mcp-stats` cases read it. The port must build that log path as
   `$XDG_STATE_HOME/rac/guide-telemetry.jsonl` and print it verbatim.

Additionally, `tests/conftest.py` has an **autouse** fixture `_isolated_xdg`
that, for *every* test, points `XDG_CONFIG_HOME` / `XDG_STATE_HOME` /
`XDG_CACHE_HOME` at temp dirs and deletes `RAC_CACHE_DIR` / `RAC_NO_CACHE`. The
golden test's explicit `XDG_STATE_HOME` override wins over the autouse one for
the state dir. Rationale (quoted): no test may read/write real user state, and
with a live PostHog key in source (ADR-041) no run may phone home; cache
isolation is load-bearing since the persistent cache is default-on (ADR-112).

### 1.3 Git-derived recency stripping (the crucial parity subtlety)

`find` output embeds a **git-derived `recency` object** per match. Two of its
three fields are wall-clock-relative, so leaving them in a byte-pinned golden
would make it time-fragile. The test excises them:

- `_FIND_JSON_CASES = {"find_json", "find_explain_json"}` — after capture, parse
  the JSON and `match.pop("recency", None)` from every match, then re-serialize
  with `json.dumps(data, indent=2) + "\n"`. So the JSON goldens **do not
  contain `recency` at all**.
- `_FIND_HUMAN_CASES = {"find_human"}` — regex-strip the inline stale marker:
  `_STALE_MARKER_RE = re.compile(r" ⚠ stale \(\d+d\)")` (note the leading space;
  `⚠` is U+26A0). For the `resolve` fixture corpus, matches are fresh, so no
  marker is present anyway — but the strip guards the stale case.

**Implication for the Rust parity harness:** replicate this strip in the diff
layer. The Rust binary *will* emit `recency` (or the marker) when run inside a
git repo on committed files; parity must compare the stripped forms, exactly as
the Python test does. The recency contract itself is pinned separately and
deterministically against controlled git state (see §4 and
`tests/test_recency.py`).

### 1.4 The 40 golden cases (name → argv → expected exit code)

Exit codes are load-bearing. `0` = success/clean, `1` = validation/finding
failure. Full list:

| name | argv | rc |
|---|---|---|
| validate_valid_human | `validate tests/fixtures/valid/feature.md` | 0 |
| validate_valid_json | `validate tests/fixtures/valid/feature.md --json` | 0 |
| validate_invalid_human | `validate tests/fixtures/invalid/duplicate_ids.md` | 1 |
| validate_invalid_json | `validate tests/fixtures/invalid/duplicate_ids.md --json` | 1 |
| validate_dir_human | `validate tests/fixtures/portfolio` | 1 |
| validate_dir_json | `validate tests/fixtures/portfolio --json` | 1 |
| stats_human | `stats tests/fixtures/valid` | 0 |
| stats_json | `stats tests/fixtures/valid --json` | 0 |
| diff_human | `diff examples/example_dashboard_v1.md examples/example_dashboard_v2.md` | 0 |
| diff_json | `diff …v1.md …v2.md --json` | 0 |
| schema_requirement_human | `schema requirement` | 0 |
| schema_requirement_template | `schema requirement --template` | 0 |
| review_human | `review tests/fixtures/portfolio` | 1 |
| review_json | `review tests/fixtures/portfolio --json` | 1 |
| watchkeeper_human | `watchkeeper tests/fixtures/watchkeeper/head --base tests/fixtures/watchkeeper/base` | 1 |
| watchkeeper_json | `… --json` | 1 |
| watchkeeper_github | `… --format github` | 1 |
| templates_human | `templates` | 0 |
| templates_json | `templates --json` | 0 |
| resolve_human | `resolve RAC-01JY4M8X2QZ7 tests/fixtures/resolve` | 0 |
| resolve_json | `resolve RAC-01JY4M8X2QZ7 tests/fixtures/resolve --json` | 0 |
| resolve_not_found_json | `resolve RAC-ZZZZZZZZZZZZ tests/fixtures/resolve --json` | 1 |
| find_human | `find markdown tests/fixtures/resolve` | 0 |
| find_json | `find markdown tests/fixtures/resolve --json` | 0 |
| find_explain_json | `find markdown tests/fixtures/resolve --json --explain` | 0 |
| relationships_resolved_human | `relationships tests/fixtures/resolve` | 0 |
| migrate_dry_run_human | `migrate metadata tests/fixtures/migrate --dry-run` | 0 |
| migrate_dry_run_json | `migrate metadata tests/fixtures/migrate --dry-run --json` | 0 |
| mcp_stats_human | `mcp-stats` | 0 |
| mcp_stats_json | `mcp-stats --json` | 0 |
| mcp_stats_share | `mcp-stats --share` | 0 |
| doctor_unlinked_human | `doctor tests/fixtures/doctor/unlinked` | 0 |
| doctor_unlinked_json | `doctor tests/fixtures/doctor/unlinked --json` | 0 |

(There are also `skill_*` and `export_json` goldens in `tests/golden/` that are
**not** in `test_golden.py`'s `CASES` — they are consumed by `test_skill.py` and
`test_export_cmd.py` respectively. `export_json.txt` was verified git-clean:
zero occurrences of `recency`/`created`/`updated`.)

### 1.5 JSON serialization format (byte-exact)

All JSON goldens are produced by Python `json.dumps(..., indent=2)` semantics:

- 2-space indentation, `", "` / `": "` separators become `","`+newline and
  `": "` under `indent=2` (i.e. item separator is `,` + newline+indent, key/value
  separator is `": "`).
- A **trailing newline** is appended (`+ "\n"`) — every JSON golden ends with
  exactly one `\n`.
- Non-ASCII is **escaped by default** unless the code passes `ensure_ascii=False`
  — verify per renderer. (The find/human goldens contain literal UTF-8 `↳`
  `⚠`; JSON renderers must be checked case-by-case for `ensure_ascii`.)
- Key ordering is **insertion order** (Python dict preserves insertion order).
  The Rust port must emit keys in the exact order the Python builds them — e.g.
  `schema_version, query, type, match_count, matches`, and within a match
  `id, type, title, path[, section, snippet]`. `null` is emitted for present-but-
  None keys (e.g. `"type": null`).
- Floats use Python `repr`: golden `stats_json.txt` shows
  `"average_requirements_per_feature": 2.0` (note `.0`), and
  `find_explain_json.txt` shows scores like `0.024458`, `0.160562` (6-dp values
  as produced upstream — see the retrieval-scoring contract section for the
  rounding rule; these are pre-rounded, not `json`-formatted floats). **Float
  repr parity is a landmine** — Python `json` uses `float.__repr__` (shortest
  round-trip). The port must match digit-for-digit.

---

## 2. Fixture corpora inventory

All under `tests/fixtures/`. Counts are `.md` files (artifacts) unless noted.

| Path | Files | Exercised by (commands) |
|---|---|---|
| `valid/` | 4: `bullet_requirements.md`, `feature.md`, `minimal.md`, `warnings.md` | `validate`, `stats` (golden: 4 features / 8 reqs / 2 metrics / 2 risks) |
| `invalid/` | 8: `duplicate_ids.md`, `empty_req_text.md`, `malformed_id.md`, `missing_id.md`, `missing_problem.md`, `missing_requirements.md`, `missing_title.md`, `multiple_titles.md` | `validate` (negative cases; `duplicate_ids.md` → golden, rc 1) |
| `portfolio/` | `broken.md`, `feature_a.md`, `feature_b.md`, `sub/feature_c.md` | `validate` (dir, rc 1), `review` (rc 1) |
| `portfolio/sub/` | `feature_c.md` | recursion test |
| `resolve/` | 2: `markdown-first.md` (id `RAC-01JY4M8X2QZ7`, decision), `v0-canonical-format.md` (id `v0-canonical-format`, roadmap) | `resolve`, `find`, `relationships` |
| `relationships/` | 5: `{decision,design,prompt,requirement,roadmap}_with_links.md` | `relationships` |
| `relationship_validation/` | subdirs: `resolved/`, `broken/`, `ambiguous_target/`, `duplicate/`, `self_reference/` | `relationships --validate` |
| `migrate/` | 3: `adr-001-legacy.md` (→migrated), `canonical.md` (→already-canonical), `notes.md` (→skipped-unknown); plus `.rac/` config dir | `migrate metadata --dry-run` |
| `watchkeeper/base/` & `watchkeeper/head/` | each has `decisions/`, `requirements/`, `roadmaps/` subtrees | `watchkeeper --base` (dir-to-dir, **git-free** by design — see §4) |
| `doctor/unlinked/` | 2: `adr-001-alpha.md`, `adr-002-beta.md` | `doctor` (advisory unlinked-reference, rc 0) |
| `telemetry/state/rac/guide-telemetry.jsonl` | 1 jsonl (6 lines, one deliberately invalid) | `mcp-stats` (via `XDG_STATE_HOME`) |
| `decision/portfolio/`, `design/`, `diff/`, `export/`, `graph/`, `ingest/`, `inspect/`(+`nested/`), `mcp/`(`corpus/`,`duplicate/`), `no_relationships/`, `note-ingest/`(`obsidian-vault/`,`obsidian-golden/`), `okf_conformance/`(`clean/`,`reserved_collision/`,`reserved_ok/`), `portfolio_summary/`(`all_types/`,`broken_rels/`,`invalid_known/`,`unknown_only/`,`valid_clean/`), `prompt/`, `roadmap/` | — | consumed by the matching `test_*.py` (e.g. `test_okf_conformance.py`, `test_portfolio.py`, `test_note_ingest.py`) |

`tests/eval/corpus/` backs the grounding benchmark (`test_eval.py`).

The `telemetry/state` jsonl fixture is the determinism anchor for `mcp-stats`:
6 physical lines, one is the literal text `this line is not valid json and must
be skipped, not raised over` → golden reports `Events: 5`, `Sessions: 2`,
`Skipped Unreadable Lines: 1`. Per-tool `avg N ms` is an **integer** average
(get_artifact durations 7 and 9 → `avg 8 ms`) — confirm the rounding mode
(appears to be integer division / round; verify against golden values).

---

## 3. Other output/exit-code-pinning test files

Beyond `test_golden.py`, ~59 test files assert exit codes (`assert rc == …`,
`pytest.raises(SystemExit)`, `.returncode ==`). The high-value reusable ones:

- **`tests/test_char_*.py`** (10 files: `core, author, compare, enforce, graph,
  ingest, mcp, ops, report, retrieve`) — **characterization tests**. Explicitly
  a divergence-detection harness: they "pin the *current* observable behavior …
  so that a reimplementation cannot change any of these behaviors silently." A
  Rust port should treat these as a primary conformance battery. They freeze
  **sharp edges deliberately**, e.g. (`test_char_core.py`): a leading UTF-8 BOM
  (`\xef\xbb\xbf`) **defeats** frontmatter parsing because `parse_file` decodes
  with plain `"utf-8"` (not `utf-8-sig`) and `str.strip()` does **not** treat
  U+FEFF as whitespace, so line 0 is `"﻿---"` ≠ `"---"` and the whole file
  (BOM+frontmatter+body) is treated as body. **The Rust port must reproduce
  this** — decoding with BOM-stripping would flip identity/type/validation for
  the same bytes. Other frozen edges mentioned: a symlinked directory not being
  descended. See the classification/frontmatter contract section for the full
  edge list; this file is the test oracle for it.
- **`tests/test_watchkeeper.py`** — pins the **stderr** github-annotation stream
  (out of scope for goldens' stdout). Needed for `--format github` parity.
- **`tests/test_recency.py`** — the deterministic recency/staleness contract
  (builds throwaway git repos with controlled `GIT_AUTHOR_DATE`/
  `GIT_COMMITTER_DATE`; see §4).
- **`tests/test_export_cmd.py`** (uses `export_json.txt`), **`tests/test_skill.py`**
  (uses `skill_*` goldens), **`tests/test_mcp_tools.py`**, **`test_note_ingest.py`**
  (obsidian-golden) — additional byte/JSON pinning outside the golden harness.
- **`tests/test_cli.py`, `test_validate.py`, `test_stats.py`, `test_diff.py`,
  `test_resolve.py`, `test_doctor.py`, `test_review.py`, `test_migrate.py`,
  `test_schema.py`, `test_templates.py`, `test_find_*.py`** — per-command exit
  code + substring assertions.

---

## 4. Git-derived / recency behavior (ADR-045) — the parity control surface

RAC artifacts carry **no stored timestamp**; recency is **derived from `git
log`**, never stored (ADR-045). This makes several outputs depend on git state.
The parity harness **must control or strip every field below.** Git is touched
read-only in exactly these modules: `src/rac/services/recency.py`,
`src/rac/services/revisions.py` (watchkeeper materialization),
`src/rac/services/drift.py`, `src/rac/services/watchkeeper.py`.

### 4.1 The git primitives (exact commands)

From `recency.py`:
- Repo root: `git rev-parse --show-toplevel` (cwd = target dir). Non-zero rc or
  no git binary (`FileNotFoundError`) → `None` = "not a repo / unknown". **Never
  raises across the boundary.**
- Last-committed: `git log -1 --format=%cI -- <pathspec>`. `%cI` = **strict ISO
  8601 committer date in the committer's stored timezone offset.**
- First-committed (OKF `created` only): `git log --reverse --format=%cI -- <path>`,
  take first non-empty line.
- Status history (MCP provenance only): `git log --reverse
  --format=%H\x1f%cI\x1f%an <%ae> -- <path>` then `git show <sha>:<path>` per
  commit. Field separator is **U+001F (unit separator)** — chosen because it
  never appears in a date/name/email.
- Pathspec: path made **relative to repo root** via `Path.resolve()`; if outside
  the work tree, the absolute path is passed through.

### 4.2 `%cI` timezone — VERIFIED LANDMINE

`git log --format=%cI` renders the **committer's stored timezone offset**, and
**ignores the `TZ` environment variable.** Verified empirically:

```
$ git log -1 --format=%cI -- rac/decisions/adr-025-…md
2026-07-07T12:50:13+01:00
$ TZ=UTC git log -1 --format=%cI -- …           # same file
2026-07-07T12:50:13+01:00        # offset unchanged by TZ
```

So `last_committed` strings embed whatever offset was baked into each commit
(`+01:00` here) — this is **repo/commit-specific, not machine-local, and not
UTC-normalized.** The value is parsed by `datetime.fromisoformat(stamp)` (tz-
aware) and re-serialized by `.isoformat()`, preserving the offset verbatim. The
Rust port must:
1. Shell out to real `git` (or a git lib that reproduces `%cI` byte-for-byte,
   including the offset) — do **not** normalize to UTC.
2. For parity, run against the same committed git history, or strip these fields.

### 4.3 `staleness()` — the derived fields (`recency.py`)

Given `last_committed` (tz-aware) and a `reference` ("now", default
`datetime.now(UTC)`):
- `age_days = (reference - last_committed).days` — Python `timedelta.days`
  **floors toward negative infinity**. A commit dated in the future yields a
  **negative** `age_days`. Whole-day truncation, not rounding.
- `stale = age_days > threshold_days` — strictly greater-than. **Boundary is not
  stale**: at exactly `threshold_days`, `stale=False` (frozen in
  `test_staleness_boundary_is_not_stale_at_exactly_threshold`).
- Unknown date → `Staleness(None, None, None)` → dict
  `{"last_committed": None, "age_days": None, "stale": None}`.
- `DEFAULT_STALE_AFTER_DAYS = 180`.
- Threshold config: `load_freshness_threshold` reads `freshness.stale_after_days`
  from the nearest `.rac/config.yaml` (walked upward via `find_config_file`).
  Defaults to 180 when absent, malformed YAML, non-mapping, or value is not a
  **positive int** — and **`bool` is explicitly rejected** (`isinstance(value,
  bool)` guard: `true`/`false` are not day counts even though `bool` is an
  `int` subclass in Python). This bool-rejection is a Python-specific edge worth
  porting faithfully.

### 4.4 Per-command enumeration of git-dependent output fields

| Command | Git-dependent output | Mechanism / notes |
|---|---|---|
| `find` (human) | inline ` ⚠ stale (Nd)` marker per stale match | `render_find_human`, `human.py:1053`. Marker only if `recency.stale` truthy; `(Nd)` from `age_days`, or bare ` ⚠ stale` if age is None. Fresh matches unchanged. |
| `find` (JSON) | `recency: {last_committed, age_days, stale}` object per match | `annotate_search_recency` wired at `cli.py:1117-1119`. Additive; sits beside metadata. Golden strips it entirely. |
| `mcp search_artifacts` | same `recency` object per match | `mcp/server.py`; within response budget (REQ-007). |
| `mcp` provenance tool | `last_committed, last_author, first_committed, first_author, status_history[]` | `artifact_provenance` (recency.py). MCP-only; **no CLI command exposes provenance** (`grep` of `cli.py` for `provenance` → none). `%an <%ae>` author strings + status reconstructed via `git show`. |
| `review` (`--stale-after [DAYS]`) | `stale-corpus` info finding: `"No product knowledge recorded in the last {window} days (newest artifact is {age.days} days old)."` | `_cadence_finding` (review.py:250). Fires only if `most_recent` known AND `age > window_days`. **`--stale-after` default DAYS = 14** when the flag is given without a value (verified via `--help`). Suppressed outside git / unknown recency. Priority below all blocking findings — never changes verdict. |
| `review` / `doctor` | `suspect-artifact` drift advisory: "a referrer whose resolved target changed more recently" | `suspect_drift` (drift.py) — pure function of git commit times + resolved graph, **no wall-clock**, so byte-stable for a fixed git history (unlike recency's age). One record per referrer→target where target's `last_committed` > referrer's (both known). Empty outside git. |
| `export --format okf` (OKF bundle) | per-artifact frontmatter `created:` (first_committed) and `updated:` (last_committed); `log.md` grouped by commit **date** newest-first | `okf.py`; `cli.py:842-845` calls `artifact_recency(dir, with_creation=True)`. `_log` groups by `committed.date().isoformat()` (YYYY-MM-DD), `sorted(reverse=True)`; empty history → `"# Log\n\n_No commit history available._\n"`. |
| `export --json` (corpus payload) | **none** | Verified git-clean: golden `export_json.txt` has 0 `recency/created/updated`. |
| `watchkeeper` | **none (by design)** for `--base <dir>` | Directory-to-directory compare. Golden cases use `head` vs `base` fixture dirs, no git. Git enters **only** when `--base <rev>` names a revision → `revisions.materialized_revision` uses `git archive` (never mutates `.git`). A rev missing the subpath → empty base = "everything added". |
| `stats`, `portfolio`, `index`, `validate`, `relationships`, `resolve`, `schema`, `templates`, `diff`, `mcp-stats`, `migrate`, `inspect` | **none** | No recency wiring found. `mcp-stats` timestamps come from the jsonl fixture, not git. |
| `recency` aggregate `to_dict()` | `most_recent`, `by_type{}`, per-artifact `last_committed` (all ISO strings) | `RecencyReport.to_dict` — `schema_version:"1"`, `by_type` is **sorted by type name**, unknowns omitted; `most_recent` = `max()` of known dates. Aggregate ignores `None`. (Surfaced via services; check whether any CLI command prints it — primarily internal.) |

### 4.5 Determinism recipe for the parity harness

To get byte-stable git-dependent output, the harness must either (a) run both
oracles against **the same committed git history**, or (b) strip the same fields
`test_golden.py` strips. `test_recency.py`'s approach for (a): build a throwaway
repo and commit with fixed `GIT_AUTHOR_DATE` **and** `GIT_COMMITTER_DATE`
(`recency` reads committer date, so both must be pinned), `-c
commit.gpgsign=false`, `-c user.name`/`user.email` inline. Inject a fixed
`reference` datetime to pin `age_days`/`stale` (the service accepts a
`reference` kwarg precisely so tests are wall-clock-free).

---

## 5. Environment variables tests set for determinism

There is **no `TZ`, `LANG`, `LC_*`, or `NO_COLOR`** set by the test suite.
Determinism is achieved via the seams in §1.2 (in-process monkeypatches), not
env. Enumerated env vars actually set/deleted across `tests/*.py` (by frequency):

| Var | Uses | Purpose |
|---|---|---|
| `XDG_STATE_HOME` | 20 | telemetry/audit log location; golden points it at a relative fixture path |
| `XDG_CONFIG_HOME` | 17 | consent/config isolation (autouse conftest) |
| `RAC_CACHE_DIR` | 12 | override derived-index cache dir |
| `EDITOR` / `VISUAL` | 10 / 9 | explorer/editor launch tests |
| `RAC_MAX_FILE_BYTES` | 7 | file-size limit override (`limits.py`, default `DEFAULT_MAX_FILE_BYTES`) |
| `RAC_AUDIT_PRINCIPAL` / `RAC_AUDIT_PATH` | 6 / 4 | read-access audit recorder (ADR-084) |
| `XDG_CACHE_HOME` | 5 | cache isolation (autouse) |
| `RAC_NO_CACHE` | 4 | disable persistent cache (default-on per ADR-112) |
| `HOME` | 3 | home-relative path tests |
| `RAC_TIMING` | 2 | timing instrumentation toggle |
| `RAC_PARALLEL_BUILD_FAULT` | 1 | fault-injection for parallel cold build |
| `RAC_UPDATE_GOLDEN` | (golden refresh) | rewrite goldens when `=1` |

**Consequence for the Rust port:** TZ/locale are **not** normalized by tests, so
any locale-sensitive formatting in the port is a risk. Recency offsets come from
git commit data (§4.2), not from `TZ`. Color keys off TTY only, not `NO_COLOR`.
For a clean parity run the harness should still set `LC_ALL=C`, `TZ=UTC`, and
run non-TTY to avoid *incidental* divergence, while knowing the oracle itself
does not depend on them for the pinned outputs.

---

## 6. Open items / UNVERIFIED

- Per-renderer `ensure_ascii`: I confirmed `↳`/`⚠` appear literally in the
  **human** goldens; whether each **JSON** renderer passes `ensure_ascii=False`
  (vs escaping non-ASCII to `\uXXXX`) was not exhaustively checked per command —
  the port must match each renderer. UNVERIFIED per-command.
- `mcp-stats` `avg N ms` rounding mode (int truncation vs round-half-even) —
  inferred integer from `7,9→8`; exact rounding rule UNVERIFIED (only one data
  point). Check `mcp_stats` service source.
- `find_explain_json` score values (`0.024458`, `bm25 0.160562`, etc.) are
  pre-rounded upstream; the exact rounding/formatting belongs to the
  retrieval-scoring contract section, not here — flagged as a float-repr parity
  landmine.
- Whether any CLI command prints `RecencyReport.to_dict()` directly (vs it being
  internal to review/okf) — not fully traced; provenance is MCP-only.
