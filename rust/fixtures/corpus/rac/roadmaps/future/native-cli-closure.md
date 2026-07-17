---
schema_version: 1
id: RAC-KXBS8RW55TGX
type: roadmap
---
# Native CLI Closure — Full Command Parity in the Rust Engine

## Status

Planned

Maintainer-directed follow-up to the native-engine spike: close the CLI
gap so command parity is a closed hole, not a covered subset. Measured
gap at kickoff (2026-07-12): the oracle parser carries 32 subcommands;
the Rust engine dispatches 10 (plus `retrieve` and the separate
`rac-mcp` binary). Three surfaces stay fenced by recorded decisions and
are NOT in this item's scope: `explorer` (TUI, out of scope by the
spike roadmap), `ingest` (parser is markitdown by ADR-072; stays a
Python sidecar unless that decision is reopened), and `index` (the
derived-index cache and store are the native-derived-index roadmap
item, which also gates the ADR-063 flip).

## Outcomes

- Every oracle subcommand outside the three fenced surfaces runs
  natively with byte parity: `coverage`, `decisions-for`, `diff`,
  `doctor`, `eval`, `gate`, `hook`, `improve`, `init`, `inspect`,
  `mcp-stats`, `migrate`, `new`, `portfolio`, `quickstart`, `rename`,
  `skill`, `telemetry`, `usage`, `watchkeeper` — plus the three
  stubbed `export` modes (`--agent-rules`, `--okf`, `--html`).
- Each command lands with its own PORT-CONTRACT.d section and pinned
  parity cases before the port, oracle-refereed like the covered set:
  identical stdout bytes and exit codes, human and JSON alike.
- Write commands (`new`, `init`, `quickstart`, `rename`, `migrate`)
  are refereed on written-file bytes as well as stdout, with an
  id-injection seam so minted ids are deterministic under the harness
  (delivering RAC-KXBPS7SRM6ZB REQ-002 on the way through).
- The gap list in PORT-CONTRACT.d/01 §7 empties to the three fenced
  surfaces, each annotated with the decision that fences it.

## Initiatives

- Contract extraction first: per-command briefs from the oracle source
  and live probing — argv shape, exit codes, output surfaces, env and
  filesystem touchpoints, interactivity, nondeterminism — before any
  Rust is written.
- Extend the parity harness for the new referee shapes: id-injection
  seam for minted ids, stdin-driven cases for the `init`/`quickstart`
  prompt, written-tree byte comparison for scaffold and rename
  commands, and git-fixture cases for `doctor`/`gate`/`watchkeeper`
  exit-code nuance.
- Port in dependency-ordered batches (inspection and reporting
  commands first, gates and git-backed commands next, write commands
  last), each batch landing only when its parity class is green and
  the full existing battery stays green.
- Convert the fuzz oracle-crash catalog into pinned regression
  fixtures for the walking commands as they land (RAC-KXBPS7SRM6ZB
  REQ-004).
- One differential fuzz round over the newly covered command set at
  the end; divergences become pinned fixtures.

## Constraints

- ADR-063 remains in force throughout: the Python tree is the frozen
  oracle and the authoritative engine; this item never modifies it.
- Byte-parity is the gate, unchanged from the spike; unavoidable
  divergences are enumerated with root cause, and the oracle-crash
  class is handled as recorded in RAC-KXBPS7SRM6ZB.
- `watchkeeper` ports against ADR-043 revision-materialization
  semantics; `telemetry`/`usage` port against ADR-040/ADR-041/ADR-046
  and the ADR-086 hard-lock exactly as the oracle implements them.
- No new workspace dependencies without a recorded decision.

## Success Measures

- The parity scoreboard covers the full closure set and reports
  byte-parity on fixture corpora and the live corpus.
- `cargo test`, the existing four suites, and the new per-command
  suites are green from a clean rebuild, twice.
- PORT-CONTRACT.d/01 §7 lists only `explorer`, `ingest`, and `index`,
  each with its fencing decision cited.

## Assumptions

- The oracle's remaining commands are deterministic given fixed argv,
  cwd, env, stdin, and seeded fixtures — interactivity is confined to
  the `init`/`quickstart` prompt, and id minting is the only
  nondeterminism needing a seam.
- The existing pycompat/pyjson/output primitives cover the remaining
  commands' formatting needs; new primitives, if any, get
  oracle-generated vector tables like the originals.

## Risks

- `init`/`quickstart` interactivity and consent prompts prove harder
  to pin than stdin-driven cases allow; mitigated by contract-first
  extraction and, if needed, enumerating the interactive paths as a
  documented divergence pending a spec decision.
- Write-command parity discovers oracle behavior coupled to wall-clock
  or filesystem ordering; mitigated by seams (like the version seam)
  recorded per command in its contract section.
- Scope creep into the fenced surfaces; mitigated by this artifact
  naming them and their fencing decisions explicitly.

## Related Decisions

- ADR-063
- ADR-072
- ADR-043
- ADR-046
- ADR-086

## Related Roadmaps

- native-engine-spike
- native-derived-index

## Related Requirements

- rac-cli-hostile-input-robustness
