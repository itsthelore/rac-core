---
schema_version: 1
id: RAC-KX8608PXS0B4
type: roadmap
---
# Native Engine Spike — Rust Rewrite with Byte-Parity Harness

## Status

Planned

Maintainer-sponsored experimental spike, unscheduled. This is the
evidence-gathering path ADR-063's exception clause sanctions: a native
port explored on a branch, gated on a language-neutral spec extraction
and cross-language conformance parity. It does not override ADR-063 —
the Python engine remains authoritative until the maintainer decides
otherwise on the strength of the evidence this spike produces.

## Outcomes

- An experimental Rust implementation of the engine core lives in a
  `rust/` cargo workspace on the spike branch: frontmatter, markdown
  sectioning, classification, validation, identity, corpus walk,
  relationships, resolve search, output formatting, and the CLI argv
  surface for the covered command set.
- A parity harness drives both engines with identical argv, cwd, and
  environment over fixture corpora and the live corpus, and byte-compares
  stdout and exit codes for JSON and human output alike. Its scoreboard
  is the single definition of "agrees with the oracle".
- A performance harness measures startup, single-file validation, fresh
  corpus walk, cold-build throughput, and peak memory on synthetic
  corpora, against recorded Python baselines and the ADR-107 budget line.
- Parity and performance reports, committed beside the code, give the
  maintainer the numbers for a go/no-go decision on a mainline port.

## Initiatives

- Extract `ARTIFACT_SPECS` to a derived language-neutral data file via a
  generator that reads the Python module without modifying it — a spike
  stand-in for the full artifact-specs-extraction item, which remains
  the mainline precondition.
- Build the parity harness before the engine, and prove it deterministic
  by running it green oracle-vs-oracle first.
- Port conformance-first, one workstream per subsystem, each landing
  only when its parity fixture class is green; ship no derived-index
  cache — a fresh deterministic walk per invocation is the v0 posture.
- Hunt divergences by differential fuzzing over generated and mutated
  artifacts until consecutive rounds find nothing new; every divergence
  becomes a pinned regression fixture.

## Constraints

- The Python tree is the frozen oracle; the spike never modifies it.
- Byte-parity is the gate: identical stdout bytes and exit codes for
  every covered command; any unavoidable divergence is enumerated in the
  report with root cause.
- Out of scope for v0: the explorer TUI, ingest (markitdown remains a
  Python sidecar), MCP serving, and the derived-index cache and store.
- Branch-only work: no PRs, no publishing, no changes to recorded
  decisions; ADR-063 remains in force throughout.

## Success Measures

- The parity scoreboard reports full byte-parity on the covered command
  set over the fixture corpora and the live corpus.
- The performance report meets the spike targets — sub-25 ms single-file
  validation, a fresh live-corpus walk faster than Python's warm-cache
  path, and cold-walk throughput an order of magnitude above the Python
  serial baseline — or explains each miss with numbers.
- The reports give a concrete go/no-go recommendation grounded in
  measured evidence, not estimates.

## Assumptions

- The engine core's observable surface — bytes out, exit codes — is
  fully pinned by the existing golden tests plus fixtures the spike
  adds, so parity is decidable mechanically.
- Python's frontmatter (bounded YAML-1.1 subset), markdown sectioning
  (commonmark token line ranges), and float scoring semantics can be
  reproduced exactly in Rust; where a library cannot, a bespoke minimal
  implementation is in scope.

## Risks

- Float formatting and `math.log` ulp differences produce rare ordering
  divergences in resolve scoring; mitigated by replicating operation
  order and pinning any sensitive case as a regression fixture.
- YAML-1.2 semantics leak in from a Rust YAML crate; mitigated by
  preferring a bespoke parser for the restricted grammar.
- Spike results are mistaken for a decision; mitigated by the reports
  framing everything as evidence for ADR-063's existing gates.

## Related Decisions

- ADR-063
- ADR-107

## Related Roadmaps

- agnostic-surfaces
- artifact-specs-extraction
- conformance-fixtures
