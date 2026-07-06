---
schema_version: 1
id: RAC-KWV0ZNKY74MB
type: roadmap
---
# Durability Benchmark

## Status

Planned

Unscheduled — captured as future intent and being executed in the benchmarks
repository. Records the intent to measure the governance claim the
granularity benchmark isolated: splitting knowledge into typed per-file
artifacts does not improve lexical retrieval, but it makes the structure
that retrieval safety depends on enforceable. This benchmark measures that
enforceability under realistic editing, which is the evidence an adopter
weighing artifacts against canon documents actually needs.

## Context

The granularity benchmark's validity round produced a null and a
sharpening: with an identical ranker, per-file splitting changes retrieval
not at all, and a status-aware parser over a well-formed canon recovers the
superseded-decision defense completely. What separates the models is what
happens after the corpus is edited by people: the artifact model's status
and reference structure is a validated contract, while the canon's status
lines are an unenforced convention that a single sloppy edit can silently
break — and a broken block boundary can corrupt the parser's reading of
neighboring decisions. None of that is measured anywhere today.

## Outcomes

- A safety-decay curve: superseded-decision leaks as a function of applied
  edits at recorded sloppy-edit rates, canon versus artifacts, with the
  artifact side reported both gated (validation flags breakage at edit
  time) and ungated (files rot too when nobody runs the gate — the gate is
  the value, and the honest comparison says so).
- A detectability matrix: for each injected break class — malformed status,
  heading-level slip, broken block boundary, duplicate identity, dangling
  supersedes target — whether the artifact gates catch it, and whether a
  best-effort deterministic canon linter can, showing where free contract
  checks end and bespoke tooling begins.
- A merge-conflict rate for concurrent edit pairs under deterministic
  three-way merge: same-file collisions in the canon versus per-artifact
  isolation.
- Blast radius per break: how many decisions a single structural slip
  corrupts in each rendering.

## Initiatives

- A deterministic seeded edit engine over the granularity member's dual
  renderings: a taxonomy of logical edits (reword, append, supersede,
  cross-reference) with a parameterised sloppy fraction that emits the
  break classes above, applied identically to both renderings.
- Round-based measurement: after each edit round, re-run the status-aware
  canon retrieval and the typed retrieval, count leaks, and record
  detection events from the artifact gates and the canon linter.
- A concurrent-edit simulation using deterministic three-way file merges
  over sampled edit pairs, reporting conflict rates per rendering.
- Reporting in the family scorecard shape, evidence-only, with every curve
  reported at each sloppy rate and seed and no delta claimed unless its
  sign is seed-stable.

## Success Measures

- Two runs on unchanged inputs produce byte-identical scorecards.
- Every claim in the adoption story traces to a table cell: decay slope,
  detection rate per break class, conflict rate, blast radius.
- The artifact-ungated arm is reported with the same prominence as the
  gated arm; if ungated artifacts rot at canon rates, the report says the
  gate, not the split, carries the value.

## Assumptions

- The edit taxonomy and sloppy rates are recorded assumptions, varied
  across at least three rates, not tuned to flatter either model.
- Scoring stays deterministic and offline (ADR-066); merges use
  deterministic three-way file merge, not clock-dependent repository
  state.

## Risks

- An edit model too synthetic to persuade: mitigated by deriving edit
  operations from the break classes real reviews produce and recording
  the taxonomy in the member for critique.
- Strawmanning the canon again: the canon linter must be the strongest
  cheap treatment — the matrix exists to show its honest ceiling, not to
  lose on purpose.

## Related Decisions

- RAC-KTQ63DQ2AEJZ
- RAC-KV6KFBDZ4D23
- RAC-KV6KFCC8MHTM
- RAC-KWFVA38YT2C0

## Related Roadmaps

- granularity-benchmark
