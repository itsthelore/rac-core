# Closure Plan — native CLI closure (roadmap:native-cli-closure)

Close the CLI gap: 20 unported commands plus `export`'s three stubbed
modes, byte-parity refereed against the frozen Python oracle. Fenced
and NOT here: `explorer` (TUI, spike fence), `ingest` (ADR-072),
`index` (native-derived-index roadmap item). Per-command contracts —
oracle-probed argv shapes, measured exit codes, quoted output bytes,
seams, landmines, and proposed cases — live in
`spec/closure-contracts.json` (extraction pass, 2026-07-12); each
command's durable PORT-CONTRACT.d section is authored from its brief
as the port lands.

## Ground rules

- The 130/44/56/76 existing suites stay green after every commit; the
  existing `parity-cases.json` is never modified — closure cases land
  in a new `parity-cases-closure.json` refereed by the same harness.
- Every batch: cases pinned from the oracle FIRST (proven
  oracle-vs-oracle where the harness itself changed), then the port,
  then the full battery.
- Commits: `feat(<area>): ... [roadmap:native-cli-closure]`; harness
  work `feat(parity): ...`.
- The Python tree is never modified (ADR-063).

## Batches

- **B0 — harness extensions** (`feat(parity)`): written-file/tree byte
  comparison with per-file masks; pre-run sandbox seeding (state
  files, target files, malformed configs); scripted git fixtures with
  pinned `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` + offsets; id seam
  plumbing (oracle: `DECIDED_ID_SEED`-style env consumed by the id
  generator — see `new` brief; engine mirrors it); JSON field masking
  (eval `generated_at`/`lore_version`); file-mode assertion (hook);
  cwd-isolated sandboxes for default-output-path cases. Prove: 130
  existing cases oracle-vs-oracle before/after, plus one smoke case
  per new feature.
- **B1 — read-only, no new infra**: `diff`, `inspect`, `improve`,
  `portfolio`, `coverage`, `decisions-for`. All S/M; reuse parser,
  walk, validate, output. decisions-for must match the retrieve-side
  `governing_decisions` shaping exactly per its brief.
- **B2 — gates**: `gate` (config fixture variants; malformed config →
  stderr `rac:` + exit 1), `doctor` (L: git-recency suspect-artifact
  path needs the pinned-date git fixture; exit-code nuance per brief).
- **B3 — state reporting**: `usage`, `mcp-stats`, `telemetry`
  (state-file seeding; ADR-040/041/046 semantics, ADR-086 hard-lock;
  telemetry writes state — sandboxed).
- **B4 — agent integration + eval**: `skill` (writes bundled skills;
  all-or-nothing install), `hook` (writes + executable bit), `eval`
  (L: deterministic per ADR-066; masks `generated_at`).
- **B5 — scaffold/writes**: `new` (id seam; walks past hostile
  markdown — RAC-KXBPS7SRM6ZB REQ-002, pinned as a case), `init`,
  `quickstart` (stdin-driven prompt cases), `rename` (--apply mutates
  corpus), `migrate` (id masking).
- **B6 — export modes**: `--html` (vendor
  `lore-portal-shell.html` via include_str! with a byte-identity test
  against the Python package asset), `--agent-rules` (digest over
  canonical JSON; splice rules per brief), `--okf` (L: add
  `gitinfo::first_committed`; pinned-date git fixture; written-tree
  comparison).
- **B7 — watchkeeper** (L): needs native `diff` (B1) plus new
  compare/intent/revisions modules and `git archive` extraction;
  stdout AND stderr refereed separately (github mode).

## Definition of done

- Closure suite green plus all four existing suites green, twice, from
  a clean rebuild; `cargo test` green; workspace clippy `-D warnings`.
- One differential fuzz round extended over the newly covered
  commands; zero engine findings; oracle-crash catalog pinned as
  native regression fixtures (REQ-004).
- PORT-CONTRACT.d/01 §7 gap list reduced to the three fenced surfaces
  with their fencing decisions cited; per-command contract sections
  committed; CLOSURE-REPORT.md with per-command case counts and the
  divergence ledger.
