# 13 — Closure gates: gate, doctor

Scope: the B2 enforcement/health commands ported for
roadmap:native-cli-closure — `rac gate`, `rac doctor`. Every claim below
was verified against the oracle (`.venv-oracle/bin/rac`,
`0.1.dev50+g21c8be403`, Python 3.11.15). Source files: `src/asdecided/cli.py`
(`cmd_gate`/`cmd_doctor`), `src/asdecided/services/{gate,doctor,links,drift,
recency,init}.py`, `src/asdecided/output/{human,json,sarif}.py`. Rust: new
`rac-engine/src/gate.rs` (gate service + the STRICT `.decided/config.yaml`
loaders) and `doctor.rs` (doctor service + the links + injection ports),
`review.rs` (`review_from_portfolio` made pub; `suspect_drift`/
`drift_problem` shared with doctor), `frontmatter.rs`
(`yaml_load_config` seam), `output.rs` (`relationship_sarif_parts`
extraction + gate/doctor renderers), `commands.rs`
(`cmd_gate`/`cmd_doctor`), `cli.rs` (`run_gate`/`run_doctor`).

Shared conventions (see 09 §0): one trailing `\n` from `print()`; ANSI
color gated on `sys.stdout.isatty()` (gate only — doctor's renderer
builds plain strings, no color even on a TTY); `✓ ✗ !` and the em-dash
are raw UTF-8. `not a directory: <dir>` → stderr `rac: not a directory:
<dir>`, exit 2, checked in the handler AFTER argparse and BEFORE the
config load (a bad path beside a malformed config still exits 2).

---

## 1. `rac gate <directory> [--json | --sarif] [--top-level]`

### 1.1 Argv surface
`directory` is a REQUIRED positional (unlike doctor/coverage — no
default `'.'`). `--json`/`--sarif` form a mutually-exclusive group
(`rac gate: error: argument --sarif: not allowed with argument --json`,
exit 2). `--top-level` is declared inline; there is NO `--recursive` —
it bubbles to the TOP-LEVEL parser (`rac: error: unrecognized
arguments: --recursive`), as do extra positionals. Missing positional:
`rac gate: error: the following arguments are required: directory`,
exit 2. `-` is accepted as a positional and then fails `is_dir()`.

### 1.2 Exit codes
0 = no blocking finding. 1 = any blocking finding OR
`MalformedRepositoryConfig` (see §1.4). 2 = usage (argparse errors,
not-a-directory). Advisory findings never affect the exit.

### 1.3 Semantics (`build_gate`)
One corpus, three analyses, one policy pass:
- **validate** (`validate_corpus` + ADR-053 overrides + OKF): per-file
  issues carry their line anchor; OKF findings are file-level. Default
  enforcement: `error` → blocking, anything else advisory.
- **relationships** (`validation_from_corpus`): EVERY issue defaults to
  blocking. Message AND path come from the SARIF result builder
  (`_relationship_result` / rust `relationship_sarif_parts`), so the
  finding's `path` is the PERCENT-ENCODED uri — a path with a space or
  non-ASCII shows encoded in gate output while validate/review findings
  keep the raw path (verified: `adr café 1.md` → `adr%20caf%C3%A9%201.md`
  on the relationships finding only). Line is always null.
- **review** (`review_from_portfolio` — portfolio-derived issues ONLY;
  no drift, no cadence — `rac review`'s git advisories never reach the
  gate): message is `{message} — {action}` when an action exists.
  Priority ≤ 2 defaults blocking, 3+ advisory.
- **policy** (`EnforcementPolicy.classify`): `off` (drop) → `blocking`
  → `advisory` → the source default.
- Sort: `(path, line or 0, source, code, message)`.

### 1.4 The enforcement policy + STRICT config loading
`.decided/config.yaml` is discovered by the nearest-ancestor walk
(`find_config_file`). The gate is the ONE command where a malformed
config raises: `rac: malformed repository config <abs path>: <reason>`
on stderr, exit 1, empty stdout. Reasons (byte-verified against the
oracle for the structural class):
- `'enforcement' must be a mapping` (non-mapping, non-null section);
- `'enforcement.{blocking,advisory,off}' must be a list of finding-code
  strings` (non-list value or any non-string entry; null/absent = []);
- `'validation' must be a mapping`, `'validation.{rules,types}' must be
  a mapping`, `'validation.rules.<name>' must map a name to one of
  error, warning, off` (types: `error, warning`) — the gate loads
  overrides through the RAISING `load_overrides` face; the engine's
  lenient reader still supplies the applied values (identical whenever
  the strict check passes, since the lenient reader only drops entries
  the strict one rejects);
- `invalid YAML: <PyYAML exception>` — the oracle embeds PyYAML's exact
  multi-line exception prose; the Rust reason is the engine's own parse
  problem. NOT byte-reproducible, but stderr is out of parity scope
  (the harness referees stdout only) and stdout is empty on both sides,
  so the case (`gate-err-config-invalid-yaml`) pins exit + stdout.
- Load order mirrors the oracle: enforcement first, then validation —
  a doubly-malformed config reports the enforcement error.
- YAML 1.1: a bare `off:` key parses as boolean False; both the `off`
  string key and the False key are read (`off` winning). A non-mapping
  top-level document is "no section" (lenient), not an error.

### 1.5 Output
- HUMAN: bold `Corpus Gate` / `===========` / blank / `Directory:
  <raw argv>` / `Blocking:   <n>` / `Advisory:   <m>`; then per
  non-empty group: blank, bold `Blocking (<n>)` + dashes to the header
  width, per finding `  ✗ <path[:line]>` (blocking, red icon) or
  `  ! ...` (advisory, yellow) + `      [<source>] <code>: <message>`;
  final blank + `✓ Gate passed — nothing blocking.` (green) or
  `✗ Gate failed — <n> blocking finding(s).` (red).
- JSON: `json.dumps(indent=2)` — **ensure_ascii=True** (the em-dash is
  `—`; the extraction brief said ensure_ascii=False — the code
  says otherwise and the oracle bytes agree with the code). Key order:
  schema_version, directory, recursive, ok, blocking_count,
  advisory_count, findings[{source, code, severity, enforcement, path,
  line, message}].
- SARIF: one combined 2.1.0 run over ALL findings (blocking and
  advisory); level from the intrinsic severity (`info` → `note`);
  results sorted by `(uri, line or 0, ruleId, message)`;
  `driver.version` is the setuptools-scm string (mask-version / the
  `DECIDED_RS_VERSION` seam). A relationship finding's already-encoded path
  is quoted AGAIN by the SARIF renderer (oracle double-`quote()`;
  `%` → `%25` on exotic paths) — mirrored by construction.

---

## 2. `rac doctor [DIRECTORY] [--json] [--top-level|--recursive] [--hub-threshold N]`

### 2.1 Argv surface
DIRECTORY optional positional, default `'.'`. Parents: version_parent +
json_parent + scope_parent (so `--recursive` IS accepted here, unlike
gate). `--hub-threshold` is `type=int`, default 20: `x` →
`rac doctor: error: argument --hub-threshold: invalid int value: 'x'`,
exit 2; missing value → `... expected one argument`, exit 2; a negative
number is consumed as a value (argparse negative-number matcher), and
`--hub-threshold -1` flags every known artifact (degree 0 > -1).
`doctor -5` parses `-5` as the positional → `rac: not a directory: -5`.
Extra positionals bubble to the top-level `unrecognized arguments`.

### 2.2 Exit codes
0 = no error-severity finding (orphan/hub/injection/unlinked/suspect
warnings all exit 0, REQ-007). 1 = any error finding (invalid-artifact
or an error-severity relationship issue). 2 = usage/not-a-directory.

### 2.3 Semantics (`diagnose` — phases in insertion order, then one sort)
1. **invalid-artifact** (error): per STATUS_INVALID file,
   `structural validation failed: <sorted deduped error codes>`, fix
   `Run: rac validate <path>`.
2. **relationship issues** (upstream codes): severity =
   `RELATIONSHIP_SEVERITY.get(code, "error")`; path = source_path else
   paths[0] else ""; problem shapes (Python repr quoting): duplicate →
   `duplicate artifact identifier '<id>' in: <paths ', '-joined>`;
   cycle → `relationship cycle in '<rel>': <paths ' -> '-joined>`;
   else `<code> via '<rel>' -> '<target>'`. Fix
   `Run: rac relationships <raw argv dir> --validate`.
3. **degree pass** (one resolution over resolved, unique, non-self
   edges): orphaned-artifact (inbound 0 — matches the portfolio's
   "never a resolved target" count) and high-fan-out-hub
   (`inbound+outbound > threshold`), problem
   `high-fan-out hub: <degree> resolved relationship edges (threshold
   <t>)`. Both warnings.
4. **injection-style-content** (warning): six deterministic Python-`re`
   idioms re-scanned over each artifact's stored bytes (strict UTF-8;
   unreadable → skipped); the problem lists the SORTED matching labels
   (ai-impersonation, chat-role-injection, conceal-from-user,
   decision-steering, instruction-override, role-reassignment).
   Hand-compiled matchers in `doctor.rs` mirror the exact semantics:
   IGNORECASE; `.{0,N}` gaps never cross a newline while `\s+` DOES
   (`from now on,\nyou\nshall` matches; `disregard the earlier\nprompt`
   does not); `\s` includes CPython's `\x1c-\x1f`; `\b` is the Unicode
   word boundary; group 2 of conceal-from-user has no leading `\b`
   (`foretell them nothing` → `never revealing ... anyone` semantics
   verified byte-identical off-suite).
5. **unlinked-reference** (warning, links.py port): body candidate
   tokens (`[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*`) outside the nine
   relationship-section headings, resolved through the SAME index
   resolver search uses; self/declared/duplicate-target mentions are
   skipped; one finding per (source, target) sorted by
   `(source_path, target_id)`. Problem `body references <token> but
   declares no <Related X> link to it`; fix quotes the suggested line
   (shortest `^[A-Za-z]+-\d+$` alias, stable on length ties, else the
   filename stem).
6. **suspect-artifact** (warning): the drift primitive SHARED with
   `rac review` (rust `review::suspect_drift`) — resolved edges whose
   target's git last-committed is strictly newer than the referrer's;
   problem embeds both `isoformat()` dates. Empty outside git and for
   untracked files (verified: a mixed tracked/untracked corpus drops
   only the untracked edges).

Sort: `(severity rank {error:0,warning:1}, path, code, problem)` —
stable, so the phase insertion order breaks exact ties.

### 2.4 Output
- HUMAN (NO color, even on a TTY): `Repository health: <raw argv dir>`
  + blank; no findings → `✓ No issues found.`; else `<E> error(s), <W>
  warning(s)` + blank, then per finding `ERROR    <path>` /
  `WARNING  <path>` (label ljust-7 + two-space gap — ERROR carries four
  spaces total), `  [<code>] <problem>`, `  fix: <fix>`, blank; verdict
  `✓ No errors (warnings are advisory).` / `✗ Errors present.`.
- JSON: **`json.dumps(indent=2, ensure_ascii=False)`** — raw UTF-8
  em-dashes (the opposite of gate's dump). Shape: {schema_version:"1",
  directory, hub_threshold, ok, summary:{errors,warnings},
  findings:[{path, code, severity, problem, fix}]}.

### 2.5 Determinism boundary (the L-effort crux)
Suspect-artifact findings are a pure function of git state — the
problem text embeds commit dates, not ages, so NOTHING in doctor is
wall-clock-relative and no mask-json-field was needed. Parity is pinned
with the B0 scripted-git sandbox (`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`
`2024-03-05T10:00:00+02:00` → `2024-04-01T09:30:00-05:00`, offsets
preserved through `%cI` → `datetime.fromisoformat().isoformat()`
round-trip, epoch comparison across offsets). Fixture corpora WITH
resolved edges run sandboxed (non-git) so the drift phase stays
deterministically empty; edge-free fixtures run in-tree (drift
short-circuits before any git call). The live-repo case is the empty
`doctor rac/ --top-level` walk.

---

## 3. Parity evidence

`rust/parity-cases-closure.json`: `gate-*` (18), `doctor-*` (21).
Fixtures under `rust/fixtures/closure/{gate,doctor}/` — each fixture
corpus carries its own `.decided/config.yaml` (`repository_key: RAC` plus
the policy/malformed variants) so the nearest-config walk never reaches
the live repository root's overrides. Proven oracle-vs-oracle over the
whole closure file (121/121) before the port, then oracle-vs-rust
18/18 and 21/21; full battery after: CLI 130/130, retrieve 44/44,
MCP 56/56 + 76/76 (output/frontmatter/review were touched), `cargo
test --release` green, workspace clippy `-D warnings` clean.
Off-suite probes verified byte-identical: percent-encoded gate paths
(space + non-ASCII filename) across human/json/sarif; flow-style
`enforcement: {advisory: [...]}`; null/empty policy keys; bare `off:`
(False-key) suppression; non-string policy entries; strict-override
errors (`validation: nope`, bad rule values); invalid/duplicate/cycle
doctor corpora; overrides interplay (`requirement-missing-id: off` +
type ceiling); mixed tracked/untracked drift; `doctor -5`, `gate --
--json`, file positionals, empty directories, and the six injection
matchers against gap/newline/boundary edge inputs.

Known divergence (documented, out of parity scope): the
`invalid YAML:` stderr reason text — PyYAML exception prose vs the
engine's parse problem (§1.4). Exit code and (empty) stdout match.
