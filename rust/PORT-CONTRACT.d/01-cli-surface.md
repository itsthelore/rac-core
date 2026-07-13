# 01 — CLI argv surface, exit codes, and I/O routing

Scope of this section: the argv/exit-code/stream contract for the **covered command
set** — `validate`, `find`, `resolve`, `relationships`, `review`, `stats`, `schema`,
`export`, plus `--version` and top-level parser behavior. Output *content* (the exact
bytes of each renderer) is a separate section; here we pin argv shapes, exit codes,
which stream each outcome goes to, and the environment/cache neutralization needed for
deterministic runs. Source: `src/rac/cli.py` (single argparse tree, one file). Entry
point is `rac.cli:main` (`pyproject.toml [project.scripts] rac = "rac.cli:main"`).

All claims below verified against `.venv-oracle/bin/rac` unless marked **UNVERIFIED**.

---

## 0. Top-level parser

Built in `build_parser()` (cli.py:1450). Structure:

- `prog="rac"`, `description="Requirements As Code — lint and diff Markdown requirements."`
- Root parser has a `version_parent` (adds `--version`) and a **required** subparser
  group: `sub = parser.add_subparsers(dest="command", required=True)`.
- Every subcommand *also* gets `version_parent` via `parents=[...]`, so `--version`
  works on the root parser **and** on every subcommand (e.g. `rac validate --version`
  prints the version and exits 0, short-circuiting the command). Verified:
  `rac validate --version` → `rac 0.1.dev50+g21c8be403`, exit 0.

### `--version` string format — LANDMINE

`argparse` `action="version"`, `version=f"rac {__version__}"`. Printed to **stdout**,
exit 0. Format is the literal string `rac ` + `__version__` + trailing newline.

`__version__` comes from `importlib.metadata.version(...)` (setuptools-scm dynamic
version derived from git tags — `pyproject.toml` has `dynamic = ["version"]`). In this
working tree it renders as **`rac 0.1.dev50+g21c8be403`** (a dev/untagged build). On a
real tagged release it is `rac X.Y.Z` (SemVer, ADR-111). **The Rust port must treat the
version string as a build-time constant it is told, NOT reproduce the git-describe
algorithm.** For byte-parity testing, pin the oracle to a tagged checkout or inject a
known version; do not assert against `0.1.dev50+g...` which is checkout-specific.

Note: Python argparse `version` action prints via `parser._print_message(... sys.stdout)`
then `parser.exit()` → exit 0.

---

## 1. Argparse error conventions (ALL commands)

Python `argparse` on any parse failure calls `parser.error(msg)`, which prints to
**stderr**:

```
usage: <usage line(s)>
<prog>: error: <message>
```

and exits **2**. This is distinct from the hand-written `rac: <msg>` usage errors in §2.
Verified cases (all exit 2, all stderr):

| Trigger | `<prog>` in error line | `<message>` |
|---|---|---|
| `rac` (no subcommand) | `rac` | `the following arguments are required: command` |
| `rac frobnicate` | `rac` | `argument command: invalid choice: 'frobnicate' (choose from 'validate', 'diff', ... 'hook')` |
| `rac validate` (missing positional) | `rac validate` | `the following arguments are required: file` |
| `rac validate rac/ --json --sarif` | `rac validate` | `argument --sarif: not allowed with argument --json` |
| `rac ingest x --from bogus` | `rac ingest` | `argument --from: invalid choice: 'bogus' (choose from 'obsidian', 'logseq', 'notion', 'roam')` |

The `invalid choice` list is emitted **in declaration order**, quoted with single
quotes, comma-space separated, wrapped in `(choose from ...)`. The full subcommand choice
list (order matters, this is the root `{...}` metavar and the invalid-choice list):

```
validate, diff, stats, ingest, inspect, improve, schema, relationships, rename,
review, doctor, coverage, gate, watchkeeper, portfolio, index, export, explorer,
mcp, mcp-stats, telemetry, usage, new, templates, init, quickstart, resolve, find,
decisions-for, eval, migrate, skill, hook
```

**Usage-line wrapping is Python-specific.** argparse wraps the usage line to terminal
width (falls back to `COLUMNS` env or 80 when not a TTY). The wrap points and continuation
indentation (aligned under the first token after `usage: `) are argparse's
`HelpFormatter` algorithm. Reproducing usage/`--help` text byte-for-byte requires
re-implementing argparse's formatter; treat `--help`/usage bodies as **out of scope for
byte parity** unless a later section commits to it. What IS load-bearing and reproducible:
the final `<prog>: error: <message>` line, exit code 2, stderr routing.

`-h`/`--help`: prints help to **stdout**, exit **0** (verified `rac --help` exit 0).

---

## 2. Hand-written usage errors — `rac: <message>` (exit 2)

`_usage_error(message)` (cli.py:161) prints `rac: <message>` to **stderr** and raises
`SystemExit(2)`. These are semantic/IO guards *inside* handlers, checked after argparse
succeeds. They always use the literal `rac: ` prefix (note: lowercase `rac`, colon,
single space), one line, trailing newline. Distinguish from §1 (which is
`<prog>: error: ...` with a usage block above it) — §2 has **no usage block**, just the
one line.

Exhaustive list of `_usage_error` messages relevant to covered commands (f-strings; `{}`
shows the interpolated value):

- validate: `--corpus applies to stdin ('-') or a single file`
- validate: `--sarif applies to directory validation`
- validate: `--corpus is not a directory: {corpus}`
- `_read`: `file not found: {path}` (single named file that isn't a regular file)
- `_read`: `cannot read {path}` (parse produced an `unreadable-artifact` issue)
- stats / review / resolve / find / export etc.: `not a directory: {directory}`
- schema: `--template cannot be used with --list`
- schema: `schema name cannot be used with --list`
- schema: `schema name required unless --list is passed`
- relationships: `relationships --sarif requires --validate`
- relationships: `relationships expects a Markdown file or directory; convert it first with: rac ingest {path}`
- relationships: `path not found: {path}`
- export: `--check requires --agent-rules`
- export: `--client requires --agent-rules`
- export: `--json cannot combine with --html or --okf`
- export: `--out requires --html or --okf (--json writes to stdout)`
- export `--agent-rules`: `unknown --client: {bad} (choose from claude, agents, cursor, copilot)`
- export `--okf`/`--html`: `cannot write {out}: {exc}` (OSError on write)

Schema unknown-name is a **special case**: `rac schema bogus` does NOT use `_usage_error`.
It prints `outputs.render_unknown_schema(name, names)` (first line `Unknown schema: bogus`,
plus a suggestion body) to **stderr** and `raise SystemExit(2)`. Verified: exit 2, stderr,
first line `Unknown schema: bogus`.

---

## 3. Exit-code model (three codes only)

`EXIT_OK = 0`, `EXIT_VALIDATION_FAILED = 1`, `EXIT_USAGE = 2` (cli.py:156-158).

- **0** — success, including "valid empty outcome" (no matches, no relationships, empty
  corpus, Unknown classification, dry-run preview).
- **1** — a *finding* (validation errors, broken/ambiguous/self/dup references, review
  priority 1-2, resolve not-found/duplicate, gate blocking, agent-rules `--check` drift).
  The corpus/input was read fine; the command's own verdict is "fail".
- **2** — usage/IO error (argparse §1, hand-written `rac:` §2, schema unknown).

`main()` (cli.py:2464) dispatches `args.func(args)` and returns its int. `SystemExit`
raised inside a handler propagates (its `.code` is the exit code). `BrokenPipeError` is
caught → returns 1 silently (redirects stdout fd to devnull to suppress the interpreter's
exit-time flush error). `__main__` does `raise SystemExit(main())`.

---

## 4. Per-command contracts (covered set)

Notation: `[--flag]` optional; `POS` positional; default shown as `=x`.

### 4.1 `validate`

```
rac validate FILE [--json | --sarif] [--top-level] [--recursive]
             [--corpus DIR] [--cache | --no-cache] [--verify]
```

- `FILE` (required positional): a Markdown file path, a directory, or `-` (stdin).
- `--json` / `--sarif`: **mutually exclusive group** (argparse-enforced, §1 error on both).
- `--top-level` (store_true) / `--recursive` (store_true): NOT a mutex group here; both
  default False; recursion is the default and `--top-level` disables it. If both passed,
  `--top-level` wins (code uses `recursive=not args.top_level`). `--recursive` is a no-op
  affirmation.
- `--corpus DIR` (metavar `DIR`, default None): single-file/stdin only.
- `--cache` (store_true, **default True**) / `--no-cache` (store_false, dest `cache`):
  the cache toggle. NOT a mutex group; last-wins by argparse (both set `cache`).
- `--verify` (store_true, default False): full-hash freshness floor for the cache.

Dispatch logic (cli.py:233):
1. If `FILE != "-"` and is a **directory**:
   - if `--corpus` given → `_usage_error("--corpus applies to stdin ('-') or a single file")` (exit 2).
   - else validate the tree. Cache path (`validate_directory_incremental`) vs
     uncached (`validate_directory`) chosen by `_cache_enabled(args)` = `args.cache and
     not os.environ.get("RAC_NO_CACHE")`. **Both paths are byte-identical** (ADR-106/112) —
     see §6.
   - Output: `--sarif` → SARIF, `--json` → dir-json, else human — all to **stdout**.
   - Exit **0 if result.ok else 1**.
2. If `--sarif` and not a directory → `_usage_error("--sarif applies to directory validation")` (2).
3. Read the single file/stdin (`_read_validate_input`): stdin via `parse(sys.stdin.read(),
   source_path="-")`; a named file via `_read` (missing → `file not found:` exit 2;
   unreadable → `cannot read` exit 2).
4. If `--corpus`: must be a dir (else `--corpus is not a directory:` exit 2). Emits
   corpus-result human/json to stdout. Exit **0 if ok else 1**.
5. Else single-file validation: human/json to stdout, exit **1 if has_errors else 0**.

Verified: `rac validate <valid file>` → exit 0, 72 bytes stdout, 0 stderr.

### 4.2 `find`

```
rac find QUERY [DIRECTORY=.] [--json] [--top-level | --recursive]
         [--type T | --decisions] [--tag TAG ...]
         [--cache | --no-cache] [--verify] [--explain]
```

- `QUERY` (required positional): case-insensitive substring.
- `DIRECTORY` (positional, `nargs="?"`, **default `"."`**).
- `--json` (from `json_parent`), `--top-level`/`--recursive` (from `scope_parent`).
- `--type T` **XOR** `--decisions` (store_true): mutually exclusive group (find_scope).
- `--tag TAG` (`action="append"`, dest `tags`, metavar `TAG`, default None): repeatable;
  ALL required (AND semantics).
- `--cache`(default True)/`--no-cache`(dest cache) + `--verify` (same as validate).
- `--explain` (store_true).

Dispatch (cli.py:1086): dir must exist (`not a directory:` → exit 2). Cache-enabled path
serves from persistent store (`_find_from_store`), byte-identical to the uncached walk
(`find_artifacts`/`find_decisions`). Recency annotation joined post-ranking (git-derived;
degrades to null outside git — non-deterministic across environments, see §6). Human/json
to **stdout**. **Always exit 0** (empty result is valid). Verified: no-match → exit 0.

### 4.3 `resolve`

```
rac resolve ID [DIRECTORY=.] [--json] [--top-level | --recursive]
```

- `ID` (required positional), `DIRECTORY` (`nargs="?"`, default `"."`), `--json`,
  scope flags. No mutex beyond scope_parent's two store_true flags (not grouped).
- Dispatch (cli.py:1022): dir must exist (`not a directory:` exit 2).
- Outcomes: RESOLVED → human/json stdout, exit 0. DUPLICATE → **stderr**
  `rac: duplicate artifact ID: {id}\n\nFound in:\n- p1\n- p2...`, exit 1. NOT-FOUND →
  **stderr** `rac: artifact not found: {id}`, exit 1. With `--json` the result (incl.
  error field) always goes to **stdout** and the error text is NOT printed to stderr.
- Verified: `rac resolve ZZZ-NOPE rac/` → stderr `rac: artifact not found: ZZZ-NOPE`, exit 1.

### 4.4 `relationships`

```
rac relationships PATH [--validate] [--sarif] [--json]
                  [--top-level | --recursive]
```

- `PATH` (required): directory or single `.md`/`.markdown` file.
- `--validate` (store_true), `--sarif` (store_true), `--json` (json_parent), scope flags.
  `--sarif` is NOT in a mutex group with `--json` here (unlike validate); guarded in code.
- Dispatch (cli.py:528): `--sarif` without `--validate` → `_usage_error(
  "relationships --sarif requires --validate")` (2). Non-`.md`/`.markdown` file →
  `relationships expects a Markdown file or directory; convert it first with: rac ingest
  {path}` (2). Missing path → `path not found: {path}` (2).
- With `--validate`: emit (sarif > json > human via `_emit`) to **stdout**; exit
  **0 if report.ok else 1**.
- Without `--validate`: report to stdout; **always exit 0** (finding no relationships is valid).

### 4.5 `review`

```
rac review DIRECTORY [--json] [--top-level | --recursive] [--sarif]
           [--stale-after [DAYS]]
```

- `DIRECTORY` (required positional). `--json`, scope flags (from parents),
  `--sarif` (store_true, inline).
- `--stale-after` (dest `stale_after`, `nargs="?"`, `type=int`, `const=DEFAULT_STALE_AFTER_DAYS`,
  **default None**, metavar `DAYS`): absent → None; bare `--stale-after` → the default
  const (`review.DEFAULT_STALE_AFTER_DAYS`); `--stale-after N` → N. A **negative** value
  → `_usage_error("--stale-after must be a non-negative number of days")` (2).
- Dispatch (cli.py:630): dir must exist (`not a directory:` 2). Emit sarif>json>human to
  **stdout**. Exit **0 if report.ok else 1** (priority 1-2 findings fail).

### 4.6 `stats`

```
rac stats DIRECTORY [--json]
```

- `DIRECTORY` (required), `--json`. No scope flags.
- Dispatch (cli.py:322): dir must exist (`not a directory:` 2). Human/json to **stdout**.
- Exit **0 if (has_meaningful_content OR is_empty) else 1**. I.e. exit 1 only when files
  exist but none are valid known artifacts; an empty corpus exits 0.
- Verified: `rac stats /nonexistent` → stderr `rac: not a directory: /nonexistent`, exit 2.

### 4.7 `schema`

```
rac schema [SCHEMA] [--list] [--json | --template]
```

- `SCHEMA` (positional, `nargs="?"`, default None). `--list` (store_true).
- `--json` **XOR** `--template`: mutually exclusive group (schema_mode).
- Dispatch (cli.py:497):
  - `--list`: if `--template` → `_usage_error("--template cannot be used with --list")` (2);
    if `SCHEMA` given → `_usage_error("schema name cannot be used with --list")` (2);
    else list (json/human) to **stdout**, exit 0.
  - No `SCHEMA` and no `--list` → `_usage_error("schema name required unless --list is
    passed")` (2).
  - Unknown `SCHEMA` → `render_unknown_schema` to **stderr**, `SystemExit(2)`.
  - Known: json/template/human to **stdout**, exit 0.
- Verified: `rac schema bogus` → stderr `Unknown schema: bogus`, exit 2.

### 4.8 `export`

```
rac export [DIRECTORY=.]
           [--json] [--html | --okf | --documents | --graph | --agent-rules]
           [--check] [--client CLIENT ...] [--out PATH]
```

- `DIRECTORY` (`nargs="?"`, default `"."`).
- `--html`/`--okf`/`--documents`/`--graph`/`--agent-rules`: **mutually exclusive group**
  (export_mode). `--json` is deliberately NOT in the group (see below).
- `--json` (store_true, inline): for default mode it is an explicit no-op (default mode
  writes JSON to stdout regardless); with `--agent-rules` it selects JSON output.
- `--check` (store_true), `--client` (`action="append"`, choices
  `claude|agents|cursor|copilot`, metavar `CLIENT`, default None, repeatable),
  `--out` (default None).
- Dispatch (cli.py:796): dir must exist (`not a directory:` 2). Order of guards:
  1. `--agent-rules` → `_cmd_agent_rules` (owns `--out`/`--client`/`--check`/`--json`).
     Unknown client → `unknown --client: ... (choose from claude, agents, cursor, copilot)`
     (2). `--check` + drift → exit 1; else 0. OSError writing → `cannot write under {root}` (2).
  2. `--check` without `--agent-rules` → `--check requires --agent-rules` (2).
  3. `--client` without `--agent-rules` → `--client requires --agent-rules` (2).
  4. `--json` with `--html`/`--okf` → `--json cannot combine with --html or --okf` (2).
  5. `--out` without `--html`/`--okf` → `--out requires --html or --okf (--json writes to
     stdout)` (2).
  6. `--documents` → JSONL to **stdout**, exit 0.
  7. `--graph` → graph JSON to **stdout**, exit 0.
  8. `--okf` → writes bundle dir (default `okf-bundle`, or `--out`); OSError →
     `cannot write {out}: {exc}` (2); on success prints `wrote {out}/ — N artifact(s), E
     relationship(s)` to **stdout**, exit 0.
  9. Default / bare `--json` → JSON payload to **stdout**, exit 0.
  10. `--html` → writes file (default `lore-export.html`, or `--out`); PortalShellMissing/
      PortalSeamMissing → `_usage_error(str(exc))` (2); OSError → `cannot write {out}` (2);
      success prints `wrote {out} — N artifact(s), E relationship(s)` to **stdout**, exit 0.
- Export **always exits 0** on success (no finding-based exit 1; write failures are exit 2).

---

## 5. Environment variables & deterministic-run neutralization

### 5.1 Color — LANDMINE

`src/rac/output/human.py:93`: `_USE_COLOR = sys.stdout.isatty()`, evaluated **at module
import time** (not per call). ANSI codes wrap PASS/FAIL/etc via `_c(text, code)` =
`\033[{code}m{text}\033[0m`. Colors used: green=32, red=31, yellow=33, bold=1.

- **There is NO `NO_COLOR` support and NO `--color`/`--no-color` flag.** Color is purely
  `stdout.isatty()`. When stdout is a pipe/file (any parity harness), color is **off** and
  output is plain. To match: the Rust port must emit ANSI **only when stdout is a TTY**,
  using the exact same wrapper form. For byte-parity testing, always capture with stdout
  redirected (non-TTY) → both sides produce plain text. JSON/SARIF renderers never color.
- Because it is import-time, `isatty()` is checked once; irrelevant for a single process.

### 5.2 Cache & env toggles

- `RAC_NO_CACHE` (any non-empty value): disables cache environment-wide. `_cache_enabled`
  = `args.cache and not os.environ.get("RAC_NO_CACHE")`. Affects `validate` (dir), `find`,
  `mcp`. **Does NOT change output bytes** — cached and uncached paths are contractually
  byte-identical (ADR-106/112); only latency differs. So cache on/off can never change
  stdout/exit. **BUT** `--verify` and the cache both touch git/stat freshness; still
  output-neutral. For deterministic parity, run with `RAC_NO_CACHE=1` to force the simple
  walk and eliminate any cache-state variability.
- `RAC_CACHE_DIR`: overrides cache location (default `$XDG_CACHE_HOME/rac/derived`,
  `$XDG_CACHE_HOME/rac`). Output-neutral.
- `RAC_MAX_FILE_BYTES` (`core/limits.py`): per-file byte cap. A file exceeding the cap
  produces a parse issue whose message references the cap — **this CAN change output
  bytes** (validation issues). For parity, leave unset (use the built-in default) and
  document the default in the parsing section.
- `RAC_TIMING`, `RAC_PARALLEL_BUILD_FAULT`, `RAC_PARALLEL_BUILD_MIN_FILES`: perf/test
  instrumentation. `RAC_TIMING` writes a `rac-timing:`/scorecard line to **stderr** only
  — leave unset for clean stderr.
- `RAC_AUDIT_PATH`, `RAC_AUDIT_PRINCIPAL`: MCP audit only (out of covered set).
- `COLUMNS` / terminal width: affects argparse usage/help wrapping (§1) only.

### 5.3 Telemetry / consent — output-neutral but touches the filesystem

- Consent lives at `$XDG_CONFIG_HOME/rac/telemetry.json` (default `~/.config`). Missing/
  corrupt = no consent (never raises).
- CLI usage log: `$XDG_STATE_HOME/rac/rac-usage.jsonl` (default `~/.local/state`).
  `main()` calls `usage.record_command(...)` in a `finally` after every command — but it is
  **write-only, silent-fail, and gated on recorded consent** (`load_consent().share_usage`).
  It never alters stdout/stderr/exit codes. Default state (no consent file) = records
  nothing. **For deterministic runs, no action strictly required** (it's output-neutral),
  but to guarantee zero filesystem side effects point `XDG_STATE_HOME`/`XDG_CONFIG_HOME`
  at a scratch dir, or simply ensure no consent is recorded (the default).
- The only interactive prompt in the whole CLI is `_maybe_ask_usage_sharing()` after
  **successful `init`/`quickstart`** (NOT in the covered set), and only when BOTH
  `stdin.isatty()` and `stdout.isatty()` AND no consent recorded. Non-TTY (any harness) →
  never prompts. None of the covered commands prompt.
- PostHog network ping is only in `rac.mcp.ping` and never fires for covered commands.

**Recommended deterministic invocation for the covered set:**
```
RAC_NO_CACHE=1  (force simple walk; output-neutral, removes cache-state variance)
XDG_STATE_HOME, XDG_CONFIG_HOME, XDG_CACHE_HOME → scratch dirs (no stray writes/consent)
stdout redirected to a file/pipe (color off)
RAC_MAX_FILE_BYTES unset; COLUMNS irrelevant when stdout non-TTY
```

### 5.4 Git-derived recency — LANDMINE for parity

`find` (and others) annotate results with git-derived recency (`annotate_search_recency`,
ADR-045). Outside a git repo these fields degrade to `null`; inside git they reflect commit
history. **This makes JSON output environment-dependent.** For byte-parity, both oracle and
port must run against the identical git state (or a non-git dir where fields are null). Flag
this to the output/JSON section; the argv contract itself is stable.

---

## 6. Cache on/off vs output bytes — explicit answer

Per ADR-106/ADR-112 and the code comments, the cached (`validate_directory_incremental`,
`_find_from_store`) and uncached (`validate_directory`, `find_artifacts`) paths are
**contractually byte-identical**. Cache state, `--cache`/`--no-cache`, `RAC_NO_CACHE`, and
`--verify` change *latency and freshness detection*, never stdout bytes or exit code. The
Rust port need not implement the persistent store to match output; it only needs the
uncached walk semantics. (Any observed divergence would be an oracle bug worth logging in
the divergence hunt, not intended behavior.)

---

## 7. Commands NOT ported (gap list — the three fenced surfaces)

Every other subcommand in the parser is ported and refereed: the original covered set
above plus the roadmap:native-cli-closure batch — `diff`, `inspect`, `improve`,
`portfolio`, `coverage`, `decisions-for`, `gate`, `doctor`, `usage`, `mcp-stats`,
`telemetry`, `skill`, `hook`, `eval`, `new`, `templates`, `init`, `quickstart`, `rename`,
`migrate`, `watchkeeper`, and `export`'s `--html`/`--agent-rules`/`--okf` modes — pinned
in `rust/parity-cases-closure.json` with per-command contract sections
PORT-CONTRACT.d/11–18. What remains unported is exactly the three fenced surfaces:

- `explorer` — the TUI delivery surface; out of scope per the native-engine-spike
  roadmap fence (interactive, no byte-parity referee).
- `ingest` — fenced by ADR-072 (RAC-KVJK92SM2A1R): the document-ingestion parser IS
  markitdown, which stays a Python sidecar; the native engine does not reimplement it.
- `index` — fenced by the native-derived-index roadmap item
  (`rac/roadmaps/future/native-derived-index.md`), which also gates the ADR-063
  (RAC-KV6ADYFGC3H4) flip to the native engine as the shipping CLI.

(`mcp` is served by the separate `rac-mcp` binary — PORT-CONTRACT.d/10.)

---

## 8. Machine-readable table (covered commands)

`argv-shape`: `<>` required, `[]` optional, `|` mutex, `...` repeatable, `=x` default.
Exit codes: `0` ok, `1` finding, `2` usage/IO. `stdout kind`: what lands on stdout on the
primary success path (errors/usage always → stderr).

| command | argv-shape | exit codes | stdout kind |
|---|---|---|---|
| (root) | `rac [--version] [-h] <subcommand> ...` | 0 (version/help), 2 (no/invalid subcommand) | version string / help |
| `--version` | `rac --version` (also `rac <cmd> --version`) | 0 | `rac <__version__>\n` (stdout) |
| validate | `rac validate <file\|dir\|-> [--json\|--sarif] [--top-level] [--recursive] [--corpus DIR] [--cache\|--no-cache] [--verify]` | 0 ok/valid, 1 errors found, 2 usage/IO | human \| json \| SARIF |
| find | `rac find <query> [dir=.] [--json] [--top-level\|--recursive] [--type T\|--decisions] [--tag T ...] [--cache\|--no-cache] [--verify] [--explain]` | 0 always (missing dir → 2) | human \| json |
| resolve | `rac resolve <id> [dir=.] [--json] [--top-level\|--recursive]` | 0 resolved, 1 not-found/duplicate, 2 usage/IO | human \| json (stdout); not-found/dup human → stderr |
| relationships | `rac relationships <path> [--validate] [--sarif] [--json] [--top-level\|--recursive]` | 0 (no --validate always; --validate ok), 1 (--validate finding), 2 usage/IO | human \| json \| SARIF |
| review | `rac review <dir> [--json] [--top-level\|--recursive] [--sarif] [--stale-after [DAYS]]` | 0 ok, 1 priority 1-2 findings, 2 usage/IO | human \| json \| SARIF |
| stats | `rac stats <dir> [--json]` | 0 (meaningful or empty), 1 (non-empty, none valid), 2 usage/IO | human \| json |
| schema | `rac schema [name] [--list] [--json\|--template]` | 0 ok, 2 usage/unknown-name | human \| json \| template (unknown → stderr) |
| export | `rac export [dir=.] [--json] [--html\|--okf\|--documents\|--graph\|--agent-rules] [--check] [--client C ...] [--out P]` | 0 ok (agent-rules --check drift → 1), 2 usage/IO/write | JSON \| JSONL \| graph-JSON \| `wrote ...` line \| agent-rules human/json |

Notes on the table:
- `--top-level`/`--recursive` are two independent store_true flags (not an argparse mutex);
  recursion is default, `--top-level` disables it, both-set → top-level wins.
- `--cache`(default True)/`--no-cache`(store_false dest=cache) are also not a mutex; they
  set the same dest, last-wins. `RAC_NO_CACHE` overrides to off. Output-neutral (§6).
- `validate` `--json|--sarif` and `schema` `--json|--template` and `find` `--type|--decisions`
  and `export` `--html|--okf|--documents|--graph|--agent-rules` ARE argparse mutex groups
  (violation → `<prog>: error: argument X: not allowed with argument Y`, exit 2).
