# PARITY-REPORT — Rust engine spike (roadmap:native-engine-spike)

<!-- DRAFT: campaign-2 results and final verification pending; sections marked
     [PENDING] are spliced in at phase close. -->

Status of the byte-parity claim for the experimental Rust port of the
rac-core engine against the frozen Python oracle (`src/` at commit
`21c8be4`, installed as `.venv-oracle`, version `0.1.dev50+g21c8be403`).
Everything here is machine-checked: the referee is `rust/parity-harness`,
whose own correctness was adversarially verified (it detects single-byte
stdout corruption, exit-code corruption, and corruption on normalized
cases) before any engine claim was accepted.

## Headline

**118/118 parity cases pass byte-for-byte** — identical stdout bytes and
identical exit codes — across the covered command set, on the live `rac/`
corpus (417 artifacts) and the fixture corpora, in human, `--json`, and
`--sarif` output modes. Verified twice per run with byte-identical
scoreboards, from forced clean rebuilds, by an independent verifier agent,
plus dozens of fresh adversarial probes outside the case list.

## Covered command set

`validate` (file / dir / stdin / `--corpus`, human+json+sarif),
`relationships` (inspection + `--validate`, human+json+sarif), `find`,
`resolve`, `review` (human+json+sarif), `stats`, `schema` (+ `--template`),
`export` (default/`--json`/`--graph`/`--documents` JSONL), `--version`
(root and per-subcommand), and the error/exit-code paths of each.

## Fuzzing (divergence hunt)

Campaign 1 (validate/relationships/stats matrix): 4,866 distinct generated
inputs, ~72,000 engine-pair command executions, 32 mutation operators.
Outcome:

- **1 real Rust bug** (`003-rust-bug-bigint-i64-seam`): integers beyond
  i64 aborted the frontmatter load instead of following Python bignum
  semantics. Status: fixed in phase 3 close; pinned as vectors. [PENDING
  verification splice]
- **1 port-consistency finding** (`002`): one oracle-crash constructor
  path emitted a regular issue instead of the documented divergence
  marker. Status: aligned in phase 3 close. [PENDING]
- **1 intentional divergence class** (`001-oracle-crash-unhashable-key`):
  unhashable YAML keys, constructor/tag mismatches (`!!int ''`), and
  out-of-range timestamps crash the Python oracle uncaught (traceback,
  empty stdout). The Rust engine deliberately reports a marked
  `internal-oracle-divergence` issue instead of mirroring the crash
  (PORT-CONTRACT decision 3). Repros preserved under
  `rust/fuzz/pinned/oracle-crashes/`.
- Oracle nondeterminism: none observed.

Campaign 2 (full command matrix, loop until two consecutive dry rounds):
[PENDING]

## Known, documented divergences

1. **Oracle crash inputs (001 class)** — divergence by design, see above.
   These inputs are unreachable from any valid corpus; the maintainer
   should decide at mainline time whether a native engine should mirror a
   crash or fix it (we recommend: report, don't crash — and patch the
   Python oracle separately).
2. **Version strings** — the oracle emits a setuptools-scm git-describe
   version. The Rust binary takes `RAC_RS_VERSION` (spike seam); the
   harness pins it to the oracle's exact string, so comparisons stay
   byte-for-byte. A mainline port would build the same version string in.
3. **argparse usage/help bodies** — width-wrapped by Python's
   HelpFormatter; out of parity scope by contract decision 9. The final
   `<prog>: error: <msg>` line, stderr routing, empty stdout, and exit
   code 2 are matched.

## Normalizations (declared, case-scoped)

Only where output is environment-derived, mirroring the golden tests'
conventions: `strip-recency-json` / `strip-stale-human` (git-derived
recency in `find`), `mask-version` (build-derived version in
`export --json` / SARIF `driver.version`). 16 of 118 cases; all other
cases compare raw bytes. The verifier audited every normalization against
the contract and confirmed none hides real bytes.

## Gap list (not covered by the parity suite)

- Commands out of spike scope by the roadmap artifact: explorer TUI,
  `ingest`, MCP serving (`mcp`, `mcp-stats`), and the derived-index
  cache/store (the Rust engine has no cache by design; the oracle's cache
  is contractually byte-neutral and was verified so).
- Non-covered commands with no parity cases: `diff`, `inspect`, `improve`,
  `rename`, `doctor`, `coverage`, `gate`, `watchkeeper`, `portfolio`
  (ported only as far as review needs it), `index`, `telemetry`, `usage`,
  `new`, `templates`, `init`, `quickstart`, `decisions-for`, `eval`,
  `migrate`, `skill`, `hook`.
- `export --html` / `--okf` / `--agent-rules` success paths are covered
  only where parity cases exercise them; file-writing side effects are
  compared on the `wrote ...` stdout lines and exit codes.
- Exit-2 usage-error cases compare stdout (empty) and exit code, not the
  argparse-wrapped stderr body (contract decision 9).
- TTY-gated ANSI color: asserted by code inspection and spot check, not
  by the piped-stdio scoreboard.
- Unreadable-file (EACCES) paths: untestable as root in this container;
  both engines agreed on the substituted probes (dangling symlink,
  directory-named-`.md`).

## Reproduce

```sh
cd rust && cargo build --release
target/release/parity-harness \
  --engine-a ../.venv-oracle/bin/rac --engine-b target/release/rac \
  --cases parity-cases.json --scoreboard-dir parity-out
python3 fuzz/difffuzz.py --seed 99 --rounds 4 --batch 100
```
