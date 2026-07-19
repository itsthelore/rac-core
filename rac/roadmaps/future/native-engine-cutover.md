---
schema_version: 1
id: RAC-KXGWYPNTBNHK
type: roadmap
---
# Native Engine Cutover — Ship Rust as the Default Engine for Covered Surfaces

## Status

Planned

This historical covered-surface plan remains resolvable for its implementation
evidence, but its permanent Python-arbiter end state is replaced by
`rust-authority-and-python-retirement` under ADR-118. ADR-118 is normative where
the two roadmaps differ.

The native-engine phase after native-derived-index. ADR-116 is ratified: the
Rust engine is a sanctioned second implementation, and the Python reference
stays the arbiter. This item makes the sanctioned arrangement real for users —
Rust becomes the engine that actually runs on the covered surfaces, rather than
a parity-proven binary sitting unused in `rust/target/`.

Scope boundary, recorded as maintainer intent: this is the **covered-surface
default**, not a full authority flip. Python remains installed, remains the
arbiter, and remains the engine for `ingest` — kept on Python by decision, not
pending a port. Document conversion is out of scope for the native engine:
turning a DOCX/PDF/PPTX/XLSX into Markdown is preprocessing, not engine work
(ADR-010, documents are not artifacts), and it wraps a third-party Python
library whose output RAC does not own (markitdown, ADR-072). Its accepted end
state is an optional Python extra (`pip install rac-core[ingest]`) that produces
Markdown the Rust engine then handles — so a deployment that never ingests
foreign documents needs no Python for its engine at all. The HTTP MCP transport
(ADR-098) was ported as part of this work — wire and audit, byte-parity-proven
against both oracles — so it is covered, not fenced. The Explorer TUI is
explicitly out of scope for this cutover — not a Python-retention driver and a
candidate for separate deprecation. Retiring Python entirely is a separate,
larger decision that ADR-116 deliberately left for later.

The Rust-only end state this defines: Rust serves the engine, the covered CLI,
and the six-tool MCP (stdio and HTTP); Python survives only as the conformance
arbiter and the optional `ingest` document-conversion extra — neither on the hot
path.

## Outcomes

- A user running the covered CLI commands and the six-tool MCP surface (stdio
  and HTTP transport) executes the Rust engine by default, and gets its latency
  (the log-scale
  ladder: warm `find` 43 ms vs the Python cache's 446 ms; serving startup
  35 ms vs 2.2 s) without opting in.
- The experience is one `rac`: covered commands run Rust, fenced commands
  (`ingest`) transparently run Python, and the user does not
  choose an engine per command. A documented escape hatch forces Python for
  debugging or parity re-checks.
- The lockstep guards ADR-116 made permanent are live in CI: the Guard 1 sync
  gate and the Guard 2 conformance certification run with `RAC_SPEC_DIR` set,
  and the byte-parity batteries (CLI / closure / retrieve / index, MCP cache-on
  and cache-off) are required merge gates on `main` (ADR-075, ADR-027).
- The Rust binary builds its version string in, retiring the `RAC_RS_VERSION`
  spike seam, so `--version` parity holds without a harness pin.

## Initiatives

- Distribution: build and ship the `rac` / `rac-mcp` Rust binaries per
  supported platform, packaged so an ordinary install places them on the user's
  path alongside the Python reference.
- Dispatch and fallback: a single `rac` entrypoint that routes covered
  subcommands to the Rust binary and fenced subcommands to the Python engine,
  with an `RAC_ENGINE` escape hatch to force one engine.
- CI activation: wire rac-spec in as a fetchable dependency, set `RAC_SPEC_DIR`,
  and promote the guard gates plus the byte-parity batteries to required
  pre-merge checks.
- Sequencing with the retrieval branch: adopt the `retrieve` existing-surface
  argparse delta only once roadmap:grounding-retrieval-surface merges into the
  reference — the port follows, never leads (ADR-116).
- Version and docs: compile the version string into the Rust binaries; update
  install/usage docs for the two-engine reality and the escape hatch.

## Constraints

- Covered-surface only. `ingest` (ADR-072) stays on Python by decision — an
  optional document-conversion extra, not a pending port; the cutover routes it
  to Python and must not strand it. The HTTP MCP transport (ADR-098) is covered
  — ported wire-and-audit under this codename. The Explorer TUI (ADR-028) is out
  of scope — not preserved as a cutover concern.
- Byte-parity remains the gate: on every covered command and MCP frame the Rust
  engine must produce identical stdout bytes and exit codes to the Python
  arbiter, cache on or off — this is the property that makes the swap safe.
- The Python reference stays installed and importable — it is the arbiter, it
  runs the fenced surfaces, and CI runs it to referee the Rust engine.
- No behavior change is introduced by the cutover itself: it is a delivery
  switch, not an engine change. The same bytes come out; only faster.

## Success Measures

- On a fresh install, the covered CLI commands and the stdio MCP server execute
  the Rust engine by default (verified by a runtime engine probe), and every
  fenced surface still works through Python.
- The guard gates and byte-parity batteries run in CI with `RAC_SPEC_DIR` set
  and block a merge that breaks parity or drifts the shared spec.
- `rac --version` and per-subcommand version output match between engines with
  no harness pin — the version is compiled in.
- The performance ceiling is realized for real invocations, recorded against the
  Python baselines in `rust/PERF-REPORT.md`.

## Assumptions

- The covered surface is genuinely covered: the parity batteries on this branch
  (CLI 130, closure 391, retrieve 44, index 45; MCP 56/76 cache-off, 52/71
  cache-on) enumerate exactly the commands the cutover routes to Rust; anything
  outside that set stays on Python.
- A compiled binary can be distributed through the same channel users already
  install from, so the cutover does not force a new install workflow.
- rac-spec can be made a fetchable CI dependency so the guard gates can run.

## Risks

- A covered command has an untested code path that diverges only in production;
  mitigated by the merge-gated parity batteries and the `RAC_ENGINE=python`
  escape hatch as an instant per-user rollback.
- Per-platform binary distribution is new operational surface (build matrix,
  signing, size); mitigated by scoping the platform set explicitly and keeping
  the Python path as the universal fallback.
- The dispatch layer becomes a new, untested seam between the two engines;
  mitigated by keeping it thin (route-by-subcommand, no logic) and covering the
  routing table with tests.
- Cutover scope creeps toward retiring Python or porting a fenced surface;
  mitigated by this item's explicit covered-surface boundary.

## Related Decisions

- ADR-116
- ADR-063
- ADR-115
- ADR-075
- ADR-027
- ADR-098
- ADR-072
- ADR-010
- ADR-028

## Related Roadmaps

- native-engine-spike
- native-cli-closure
- native-derived-index
- artifact-specs-extraction
- conformance-fixtures
