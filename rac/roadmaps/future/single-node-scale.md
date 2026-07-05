---
schema_version: 1
id: RAC-KWRKEFNA0413
type: roadmap
---
# Single-Node Scale

## Status

Planned

Unscheduled — captured as future intent and being executed on a feature
branch. Records the intent to make the core read engine serve
enterprise-scale corpora — up to ten million artifacts — on a single node,
without sharding, distribution, or external services, while first banking a
simplicity and maintainability pass with behavior frozen.

## Context

Every CLI invocation and every default MCP tool call re-walks the corpus and
re-parses every artifact (ADR-032's re-read-per-call model). The derived-index
cache (ADR-099) removes re-parse and re-index work for warm MCP reads, but its
freshness key still re-reads and re-hashes every file on every call, so the
per-call floor remains proportional to corpus size even when warm. Measured on
the reference node, engine work costs roughly three milliseconds per artifact
per invocation: tolerable at hundreds of artifacts, and a wall — minutes per
query — at a million. Per-match `git log` subprocesses for recency (ADR-045)
compound the per-query cost.

The scale claim to earn is invariance, not one point: warm retrieval and
incremental validation budgets must stay flat as the corpus grows, because
they are bound by query and changeset size, not corpus size. Only a cold full
build may scale with corpus size, linearly and parallel across cores.

## Outcomes

- Warm retrieval (search, resolve, relationship reads) under 100 ms p99 and
  30 ms p50, flat across the corpus-size curve, on one node.
- Incremental re-validation of a roughly thousand-file changeset under five
  seconds, independent of total corpus size.
- Cold full build bounded at roughly two minutes per million artifacts,
  parallel across cores; resident working set within two-thirds of node RAM,
  with the index living on disk.
- A simpler, more maintainable engine: complexity, duplication, and size
  measurably reduced with the externally observable contract byte-frozen.
- Rerunnable scale evidence: a deterministic corpus generator and a latency
  harness versioned in the benchmarks repository, with the budgets above as
  a pass/fail gate.

## Initiatives

- Baseline and examiner hardening: capture before-evidence across the size
  curve, pin unpinned contract behavior with characterization tests, and add
  a live cross-repo contract test for the connector export surface.
- Movement A — simplify with behavior frozen: rebuild for clarity and
  maintainability against the existing examiner; no observable change.
- Movement B — scale with architecture open: supersede the decisions that pin
  per-call re-reading (ADR-099's whole-corpus rehash key and the freshness
  mechanism of ADR-032; revisit ADR-045's per-query git subprocesses) with a
  persistent, content-addressed, incrementally invalidated index — each change
  shipped with a new decision record, new pinning tests, and a measured win on
  the scale harness.
- Evidence: rerun every before-metric with the same harness and publish the
  latency-versus-corpus-size curve as the headline result.

## Success Measures

- The scale harness gate passes at the top measured corpus size with flat
  warm-retrieval and incremental-validate lines across the curve, and any
  unreached size is reported as an honest extrapolation, never fabricated.
- The full examiner is green twice from clean with the rebuilt engine, and
  the frozen surfaces (tests, packaging, CI configuration, the connector
  export contract) show no unapproved diff against the default branch.
- Complexity, duplication, and lines of code are measurably reduced against
  the recorded baseline without loss of typing or docstring coverage.

## Assumptions

- The corpus stays a git checkout of Markdown files; the index remains a
  disposable derived structure, never authoritative (ADR-024, ADR-099).
- The reference node is modest — four cores and fifteen gigabytes of memory —
  so the working set must not assume the corpus fits in RAM.
- Determinism holds: identical corpus bytes and identical input produce
  identical output; no embeddings and no semantic scoring in Core (ADR-038,
  ADR-066).

## Risks

- Superseding ADR-032's freshness mechanism could reintroduce the silent
  staleness it exists to prevent; any replacement must detect every byte
  change before serving, or the correctness contract is broken.
- The externally observable contract could drift under rebuild pressure; the
  examiner, golden outputs, and the cross-repo connector contract test are
  the tripwires, and a consumer-repo edit to accommodate the engine is the
  tell that the contract broke.
- Scale measurements on a shared four-core box are noisy; budgets are gated
  on medians and percentiles from repeated runs, with the method recorded.

## Related Decisions

- RAC-KTW0M81E7TRA
- RAC-KWMZ3MR9DZ09
- RAC-KV2E5B1122YN
- RAC-KTXTAF6ZKDK8
- RAC-KTXTAG63E89H
- RAC-KWFVA38YT2C0
