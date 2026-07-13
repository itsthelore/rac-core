# Closure Report

Execution record for `rust/CLOSURE-PLAN.md` (roadmap:native-cli-closure)
on branch `claude/rac-engine-heal`: the 20 previously-unported CLI
commands plus `export`'s three stubbed modes, ported byte-parity against
the frozen Python oracle (`.venv-oracle/bin/rac`, `0.1.dev50+g21c8be403`,
ADR-063 unchanged — the Python tree was never modified). Referee:
`rust/parity-cases-closure.json`, 391 cases, every one proven
oracle-vs-oracle before its port landed, then oracle-vs-Rust green. The
four pre-existing suites (CLI 130, retrieve 44, MCP 56 + 76) stayed green
after every batch; `rust/parity-cases.json` was never modified.

## Commit list (per batch)

| batch | commit | subject |
| --- | --- | --- |
| scope | `ac88757` | docs(roadmap): define native CLI closure scope |
| scope | `e7530e9` | docs(roadmap): pin closure contracts and batch plan |
| scope | `cb55284` | test(engine): regenerate corpus-pinned vectors after corpus additions |
| B0 | `44d4c7b` | feat(parity): add sandbox, setup, capture, and masking referee features |
| B1 | `7f65de2` | feat(engine): port diff, inspect, and improve with pinned parity cases |
| B1 | `31af0a6` | feat(engine): port portfolio, coverage, and decisions-for |
| B2 | `b5d1ab9` | feat(engine): port gate and doctor |
| B3 | `80d5c4d` | feat(engine): port usage, mcp-stats, and telemetry |
| B4 | `74331d8` | feat(engine): port skill, hook, and eval |
| B5 | `a96a981` | feat(engine): port new, init, quickstart, rename, and migrate |
| B6 | `9cea333` | feat(engine): port export html, agent-rules, and okf modes |
| B7 | `5578014` | feat(engine): port watchkeeper |

All `[roadmap:native-cli-closure]`; durable per-command contracts in
`rust/PORT-CONTRACT.d/11`–`18`, authored from the extraction briefs in
`rust/spec/closure-contracts.json` as each port landed.

## Per-command case counts (`parity-cases-closure.json`, 391 total)

| command | cases | | command | cases |
| --- | ---: | --- | --- | ---: |
| B0 smoke (harness features) | 8 | | eval | 23 |
| diff | 11 | | new | 12 |
| inspect | 15 | | init | 20 |
| improve | 13 | | quickstart | 17 |
| portfolio | 11 | | rename | 19 |
| coverage | 12 | | migrate | 16 |
| decisions-for | 13 | | export --html | 11 |
| gate | 18 | | export --agent-rules | 20 |
| doctor | 21 | | export --okf | 12 |
| usage | 16 | | watchkeeper | 31 |
| mcp-stats | 14 | | telemetry | 25 |
| skill | 17 | | hook | 16 |

Fixtures live under `rust/fixtures/closure/` (mini-repo, per-command
corpora, the seeded agent-rules tree, scripted-git doctor/okf corpora);
27 cases additionally referee stderr (`compare_stderr`), 113 referee
written trees (`capture`), 6 referee the executable bit
(`compare_file_mode`).

## Divergence ledger (documented, out of parity scope)

Every entry below is a deliberate, recorded divergence between the
oracle and the engine; exit codes and stdout always match unless stated.
Sources: PORT-CONTRACT.d/11–18 "known divergences" sections.

1. **Oracle-crash class** (PORT-CONTRACT decision 3;
   RAC-KXBPS7SRM6ZB). Hostile markdown anywhere in the oracle's
   walk/read paths kills it with an uncaught traceback; the native
   engine reports the mirrored exception as an
   `internal-oracle-divergence` issue (or a lossy decode) and keeps
   going. Campaign 2 + the closure round confirm the class is reachable
   through EVERY corpus-walking command, including all newly ported
   ones. Catalog: `rust/fuzz/findings2/` (`-oracle-crash` suffix);
   curated: `rust/fuzz/pinned/oracle-crashes/`; pinned natively:
   `rust/fixtures/hostile/` + `rac-engine/tests/hostile_inputs.rs`
   (REQ-004, below).
2. **PyYAML stderr prose.** Malformed `.rac/config.yaml` reasons
   (`gate`, `init`, `migrate`, scaffold writes): the oracle embeds
   PyYAML's multi-line exception text after
   `rac: malformed repository config <path>: invalid YAML: `; the
   engine embeds its bounded loader's problem. Prefix, exit, and empty
   stdout match (d/13 §1.4, d/16 §8).
3. **CPython `json` extensions** (state surfaces — usage, mcp-stats,
   telemetry consent). `NaN`/`Infinity` literals, integers beyond i64,
   and lone-surrogate escapes in state logs/consent files parse in the
   oracle and are tolerated/skipped by serde. Pathological inputs RAC
   never writes (d/14).
4. **OSError tails.** Write-failure messages: the oracle embeds
   `[Errno N] <strerror>: '<internal subpath>'` (or lets the OSError
   escape as a traceback — scaffold writes, eval `--update-baseline`);
   the engine prints `io::Error` Display text behind the same
   `rac: cannot write …` prefix and exit code (d/16 §8, d/17 §4,
   d/15 §3.7).
5. **argparse usage bodies.** Usage/`--help` wrapping is argparse's
   formatter; out of byte-parity scope. The final
   `<prog>: error: <message>` line, stderr routing, and exit 2 are
   pinned (d/01 §1; argparse-error watchkeeper cases do not set
   `compare_stderr`).
6. **`re.IGNORECASE` exotics.** Python's Unicode case pairs (Kelvin
   sign → `k`) vs the engine's ASCII-case-insensitive matchers over
   pinned ASCII vocabularies (watchkeeper intent terms, doctor
   injection matchers) — unreachable for the pinned term lists
   (d/18 §6).
7. **Non-UTF-8 strict re-reads.** `diff`'s `read_text` (uncaught
   `UnicodeDecodeError`, exit 1, empty stdout — the engine mirrors exit
   and stdout, stderr differs), watchkeeper's revision re-read, and the
   export/agent-rules body re-reads (the engine degrades lossily where
   the oracle crashes — class D of the crash catalog) (d/11 §2,
   d/17 §4, d/18 §6).
8. **eval malformed-input tails.** CPython vs serde JSON parser
   message tails after the matching `malformed <what>: <path>: `
   prefix; Python-repr of non-string case ids; `float()` accepting
   numeric strings in gate configs (d/15 §3.7).
9. **tarfile / git edge process failures** (watchkeeper). tarfile
   `filter="data"` raises on escaping archive entries where the engine
   skips them (git never produces such archives); non-NotFound git
   spawn failures traceback in the oracle vs degrade to the usage
   error (d/18 §6).
10. **Interactive consent prompt** (`init`/`quickstart`). Real-TTY
    only; not byte-parity-testable without a PTY harness mode. The
    non-TTY suppression is pinned by the two
    `*-stdin-pipe-suppresses-prompt` cases; the answer classification
    is unit-pinned (d/16 §5).
11. **`rename --apply` stale-plan path.** Oracle uncaught `ValueError`
    vs engine stderr line, same exit — unreachable in a single CLI run
    (d/16 §8).

## Harness extensions (B0 + B7)

`parity-harness` grew, proven feature-by-feature with oracle-vs-oracle
smoke cases and adversarial negative tests (the 130 pre-existing cases
byte-identical before/after):

- **Per-engine sandboxes**: each engine run gets a fresh directory from
  a `fixture` tree copy plus ordered `setup` steps — `write`, `mkdir`,
  `chmod-exec`, `copy-tree`, and scripted `git` fixtures with pinned
  `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` (offsets preserved, fixed
  identity, HOME isolation; no wall clock anywhere). `{SANDBOX}`
  resolves per engine in argv/env/cwd.
- **Written-tree captures**: post-run `capture` globs; captured file
  SETS must be identical and each file byte-identical after the case's
  normalizations (`.git` trees excluded unless a pattern names them).
  `compare_file_mode` additionally referees the executable bit (hook
  installs).
- **`compare_stderr`**: opt-in stderr byte refereeing for
  contract-shaped stderr (watchkeeper github annotations, `rac:` usage
  errors, empty-stderr proofs); default stays stdout-only because
  usage bodies and traceback tails are documented divergences.
- **Masking normalizations**: `mask-ids` (Crockford minted-id tails —
  the `new`/`quickstart`/`migrate` id seam), `mask-json-field` (dotted
  path — eval `generated_at`), `mask-sandbox-path`.
- **stdin plumbing**: `stdin_text` (literal prompt feeds) joining
  campaign 2's `stdin_file`.

## Differential fuzz round (closure extension)

`rust/fuzz/difffuzz.py` extended over the newly ported
read-only/reporting surface: `diff` (vs a pinned synthetic template and
self), `inspect` (file/dir/stdin/verbose), `improve`
(file/stdin/json/template), `portfolio`, `coverage`, `decisions-for`,
`gate` (bare, `--json`, `--sarif`, pinned policy config, and the mutated
primary as a HOSTILE `.rac/config.yaml`), `doctor` (`--json`,
`--hub-threshold 0`; non-git sandbox keeps the drift phase empty),
`export --graph`, `export --agent-rules --check`, and the
`--html`/`--okf` write arms with per-engine staging/cleanup so both
engines see an identical pre-run tree (stdout + exit refereed; written
bytes remain the parity suite's job). EXTENDED sample raised 5 → 8
(13 command pairs per input). Write/scaffold and state commands (`new`,
`init`, `quickstart`, `rename`, `migrate`, `skill`, `hook`, `telemetry`,
`eval`, `watchkeeper`) are excluded by design: both engines run
sequentially in one shared case dir, so corpus-mutating commands would
leak the oracle's writes into the Rust run — those surfaces are refereed
by the harness's per-case sandboxes instead.

Round (matching the heal's scale):

```text
difffuzz: seed=501 corpus=174 operators=33 core=5+8 jobs=8
round 0: campaign2 seed=501 round=0 batch=800 divergent_inputs=88
         new_engine_findings=0 new_oracle_crash_repros=0 engine=[] crash=[]
difffuzz: done — 88 divergent inputs (1x800 files)
```

**Zero engine findings.** All 88 divergent inputs are the documented
oracle-crash class (the oracle dies, the engine reports gracefully),
and every one deduplicates into the already-catalogued crash classes —
zero new repros filed. No input produced a divergence where the oracle
survived.

## RAC-KXBPS7SRM6ZB delivery status (REQ-002 / REQ-004)

- **REQ-002** (`rac new` succeeds despite hostile markdown in the
  walk): delivered by the B5 native `new` port. The oracle crashes in
  the id-collision walk, so the class is excluded from the parity file
  and pinned as cargo tests:
  `scaffold::tests::new_survives_hostile_markdown_in_the_walk` (single
  pinned repro) and `hostile_inputs::new_mints_an_id_over_the_full_catalog`
  (the whole fixture catalog in the walk).
- **REQ-004** (the fuzz oracle-crash catalog pinned as native
  regression fixtures): delivered this pass. `rust/fixtures/hostile/`
  distills `rust/fuzz/findings2/` to one minimized fixture per crash
  class — A: unhashable YAML mapping keys (list and dict variants),
  B: the two deterministic `RAC_MAX_FILE_BYTES` read-crash zones,
  C: undecodable stdin bytes (surrogateescape), D: strict-UTF-8
  re-read of a classified artifact (invalid bytes on disk) — each
  verified to still crash the oracle. The NATIVE-ONLY cargo test
  `rac-engine/tests/hostile_inputs.rs` (5 tests) walks the fixture set
  and asserts: parse/validate total with graceful per-class issues
  (marker error for A, `non-utf8-content` warning for C/D), the
  directory walk yields a per-file verdict for every fixture, `new`
  mints an id over the full catalog, the class-B cap zones classify as
  the graceful `FileCap::OracleCrash` marker, and the surrogateescape
  stdin decode is total. The fixtures are consumed ONLY by this test —
  no parity-case sandbox or fixture tree includes
  `rust/fixtures/hostile/` (verified against every `sandbox.fixture`
  and argv path in both case files).
- REQ-001/REQ-003 were already satisfied by the native engine by
  construction (campaign-2 evidence); the closure round re-confirms
  them across the new command surface.

## Gap list (final)

`PORT-CONTRACT.d/01 §7` now lists exactly the three fenced surfaces —
everything else in the parser is ported and refereed:

- `explorer` — TUI delivery surface, out of scope per the
  native-engine-spike roadmap fence.
- `ingest` — ADR-072: the ingestion parser IS markitdown, a Python
  sidecar by decision.
- `index` — fenced by the native-derived-index roadmap item, which
  also gates the ADR-063 flip.

(`mcp` is served by the separate `rac-mcp` binary, PORT-CONTRACT.d/10.)

## Final verification — clean rebuild, batteries twice

From one `cargo clean` (full rebuild), then the test + parity batteries
run twice against that build:

- `cargo build --release`: success in 1m 04s (297.4 MiB removed by the
  clean), zero warnings
- `cargo clippy --workspace --release --no-deps -- -D warnings`:
  exit 0, zero warnings
- `cargo test --release` (workspace): run 1 — 20 test binaries, all
  ok, 0 failed (includes the 5 new `hostile_inputs` tests); run 2 —
  identical
- Closure suite (oracle-vs-rust, `parity-cases-closure.json`):
  run 1 391/391; run 2 391/391
- CLI suite (`parity-cases.json`): run 1 130/130; run 2 130/130
- Retrieve suite (`parity-cases-retrieve.json`, retrieval-spec
  oracle): run 1 44/44; run 2 44/44
- MCP (primary oracle, `--exclude-tags six,list`): run 1 56/56; run 2
  56/56
- MCP full (retrieval-spec oracle): run 1 76/76; run 2 76/76
