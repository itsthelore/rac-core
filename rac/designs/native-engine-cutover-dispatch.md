---
schema_version: 1
id: RAC-KXGWYPNTR6H4
type: design
---
# Native Engine Cutover — Distribution and Dispatch Design

## Status

Proposed

## Context

ADR-116 sanctions the Rust engine as the default for the covered surfaces (the
parity-proven CLI command set and the six-tool stdio MCP), with the Python
reference as arbiter and as the engine for the fenced surfaces (Explorer TUI,
`ingest`, HTTP MCP transport). roadmap:native-engine-cutover records the what
and why. This design records the how: how the compiled Rust binary reaches
users, how a single `rac` invocation routes to the right engine, and the order
in which the switch is made safe.

Today the product installs from PyPI as `rac-core`, exposing one console entry
point: `rac = "rac.cli:main"` (Python). The Rust engine builds two binaries in
`rust/target/release/` — `rac` and `rac-mcp` — that are byte-parity-proven
against the Python engine but ship to no one. The cutover closes that gap
without changing any output byte.

## User Need

A user installing RAC wants the fast engine on the surfaces where it is proven,
without having to know two engines exist, choose one per command, or manage a
second install. They also need the slow-but-complete surfaces (Explorer,
`ingest`, HTTP serving) to keep working, and — when something looks wrong — a
one-switch way to fall back to the reference engine to check whether the native
engine is at fault.

## Design

Three parts: a dispatcher, a distribution mechanism, and a sequenced rollout.

### 1. Dispatch (`rac.cli:main` becomes a thin router)

The Python console entry point stays `rac = "rac.cli:main"`, but `main` becomes
a router, not the engine:

- A static `COVERED` set lists the subcommands the Rust engine is
  parity-proven for (the exact set the parity batteries cover:
  `validate`, `relationships`, `find`, `resolve`, `review`, `stats`, `schema`,
  `export`, `index`, `--version`, and the error/exit paths — the covered set is
  pinned to the battery, not guessed).
- On invocation, the router inspects the subcommand. If it is in `COVERED` and a
  bundled Rust binary is present, it `exec`s the Rust binary with the identical
  argv/stdin/env (a true process replacement, so exit code, stdout/stderr, and
  signals pass through unchanged). Otherwise it falls through to the existing
  Python `cli:main` logic.
- The stdio MCP server (`rac mcp`) routes to `rac-mcp` the same way when covered;
  HTTP transport (ADR-098) stays Python.
- Escape hatch: `RAC_ENGINE=python` forces the Python path for any command;
  `RAC_ENGINE=rust` forces Rust and errors if a covered command's binary is
  missing (so CI can assert the binary is really being used). Unset = the
  default routing above.

The router is deliberately logic-free: it decides by subcommand membership and
binary presence only. It never parses beyond the subcommand token, so it cannot
itself introduce a divergence.

### 2. Distribution (binary rides the wheel)

The Rust binaries ship as package data inside the existing `rac-core`
distribution, one platform per wheel:

- Build platform wheels (via `cibuildwheel`/`maturin`-style jobs) that compile
  the release binaries and place them under `rac.bin/` package data
  (`rac.bin` = a new bundled subpackage, the ADR-021 packaging pattern already
  used for templates/hooks/skills). The router resolves the binary via
  `importlib.resources`, so it works from an installed wheel with no repo.
- Platform matrix at cutover (maintainer-decided): **Linux x86_64, macOS arm64,
  Windows x86_64** get a bundled binary. Every other platform (including Linux
  aarch64) installs the binary-less form and runs the Python engine via the
  automatic fallback — correct by construction, just not accelerated, and added
  later without a code change.
- A pure-Python sdist (no binary) remains installable everywhere; on a platform
  with no bundled binary the router simply always falls through to Python. The
  native speedup is a platform-availability enhancement, never a hard dependency
  — install never breaks for lack of a binary.
- The Rust binary compiles its version string in from the same
  `setuptools-scm`-derived version the wheel carries, retiring the
  `RAC_RS_VERSION` seam so `--version` parity holds without a harness pin.

### 3. Sequenced rollout (each step independently safe)

1. **CI first.** Wire rac-spec in as a fetchable dependency, set `RAC_SPEC_DIR`,
   and promote to required pre-merge checks: the Guard 1 sync gate, the Guard 2
   conformance certification of both engines, and the byte-parity batteries
   (CLI/closure/retrieve/index, MCP cache-on and cache-off). This makes drift a
   merge blocker *before* users depend on the native path.
2. **Version compiled in.** Replace the `RAC_RS_VERSION` seam with a build-time
   version; re-run the version parity cases without the pin.
3. **Packaging.** Add the platform-wheel build and the `rac.bin` bundling; prove
   the binary is discoverable via `importlib.resources` from an installed wheel.
4. **Dispatcher.** Land `rac.cli:main` routing behind `RAC_ENGINE`, defaulting
   to Rust for `COVERED` when the binary is present. Cover the routing table
   with tests (each covered subcommand execs Rust; each fenced one stays Python;
   the escape hatch forces each way).
5. **Retrieval sequencing.** Adopt the `retrieve` argparse delta only after
   roadmap:grounding-retrieval-surface merges into the reference.
6. **Docs.** Document the two-engine reality, the covered/fenced split, and the
   `RAC_ENGINE` escape hatch.

## Constraints

- Byte-parity is the safety property: the dispatcher must pass argv, stdin, env,
  stdout, stderr, exit code, and signals through untouched — `exec`, not a
  captured subprocess that re-emits output.
- Covered-surface only: the `COVERED` set is exactly the parity-battery command
  set; fenced surfaces (Explorer, `ingest`, HTTP MCP) route to Python.
- Install must never fail for lack of a binary: the Python path is the universal
  fallback, and the sdist has no binary at all.
- The Python reference stays installed and importable (arbiter, fenced surfaces,
  CI referee). The cutover changes delivery, not the engine.
- No new runtime behavior: same bytes out; the only observable change is
  latency.

## Rationale

Routing inside the existing `rac` entry point (rather than shipping a separate
`rac` binary as the primary) keeps one install, one command, and one name, and
makes the Python fallback automatic on any platform or command the binary does
not cover. Bundling the binary as package data reuses the distribution channel
users already have and the packaging pattern the repo already uses, so the
cutover adds no new install workflow. `exec`-based dispatch is the only form that
preserves byte-parity for free — anything that captures and re-emits output is a
new divergence surface. CI-first sequencing means the guards are enforced before
any user depends on the native path.

## Alternatives

- **Ship the Rust binary as the primary `rac`, Python as a library.** Cleaner
  single-binary story, but loses the automatic per-command/per-platform fallback
  and forces the fenced surfaces to shell back into Python from Rust — the wrong
  direction (Rust does not own the fenced surfaces). Rejected for the covered
  default; revisit if/when a full flip is decided.
- **PyO3 in-process bindings.** The strongest single-source end state (ADR-116,
  ADR-031), but it makes the binding layer new contract surface and is
  unnecessary to deliver the covered-surface default. Deferred, not rejected.
- **Subprocess-capture dispatch** (run the binary, capture stdout, re-print).
  Rejected: capturing and re-emitting is a byte-divergence risk (encoding,
  buffering, partial writes on signal) for zero benefit over `exec`.
- **Separate `rac` (rust) and `rac-py` commands, user chooses.** Rejected:
  pushes the two-engine split onto users, defeating the "one `rac`" outcome.

## Accessibility

Not a UI change. The one user-facing affordance is the `RAC_ENGINE` environment
variable; it is documented in plain terms (force `python` or `rust`) and unset
by default, so no user must act. Error messages when a forced engine is
unavailable name the missing binary and the platform.

## Style Guidance

The dispatcher stays in `rac.cli` and reads as routing, not logic: a `COVERED`
constant, a binary-resolution helper, and an `exec` call. No per-command
branching beyond membership. The `COVERED` set is defined once, next to a
comment tying it to the parity-battery case files, so it cannot silently drift
from what is actually proven.

## Open Questions

- Binary signing/notarization (macOS arm64, Windows x86_64) — required for the
  bundled binary to run without gatekeeper/SmartScreen warnings, and does that
  add a signing-secret dependency to the release job? (Both are in the decided
  platform matrix, so this must be answered before their wheels ship.)
- Wheel size: two bundled binaries add ~8 MB; acceptable, or gate the binary
  behind an extra (`rac-core[native]`)?
- Does `rac mcp` (stdio) route to `rac-mcp` transparently, or stay an explicit
  opt-in until the HTTP-transport story (ADR-098) is settled?
- Should CI assert `RAC_ENGINE=rust` on the covered battery so a missing/broken
  binary fails loudly rather than silently falling back to Python?

## Related Requirements

- rac-cli-hostile-input-robustness

## Related Decisions

- ADR-116
- ADR-115
- ADR-063
- ADR-021
- ADR-098
- ADR-075

## Related Roadmaps

- native-engine-cutover
- native-derived-index
