---
schema_version: 1
id: RAC-KV6KFH925GH8
type: requirement
tags: [user-facing, doctor, validation, diagnostics]
---
# Requirement: Repository Health Diagnostic (doctor)

## Status

Accepted

Classification: `[user-facing]` — the user runs it on their repo. Scoped to the
v0.23.0 hardening release (WS3).

## Problem

RAC already *detects* most corpus defects, but the detection is spread across
three commands a new adopter does not yet know to chain. `rac validate` answers
pass/fail per file; `rac relationships --validate` reports broken, ambiguous,
self-referencing, type-mismatched, retired-target, duplicate-identifier, and
cyclic references; `rac review`/`rac portfolio` aggregate validation, broken
relationships, and orphans into a prioritized list. A person pointing Lore at a
real, years-old corpus must run several commands, reconcile their output, and
already know which one finds what. There is also no single command that answers
the WS11 trust question — "does any artifact contain text engineered to steer a
consuming agent?" — nor one that names the **high-fan-out hubs** WS4 must bound
at runtime. The gap is not detection; it is one front door that returns a single
health verdict with a paste-ready next step for each finding.

## Requirements

- [REQ-001] RAC MUST provide a `rac doctor <dir>` CLI subcommand that runs the existing validation and relationship-integrity checks over a corpus and returns one aggregated health report, reusing `rac.services` (validate, relationships, portfolio/review) rather than re-deriving any defect class it already detects (ADR-049, ADR-055, ADR-060).
- [REQ-002] `rac doctor` MUST add the two diagnostics no existing command provides: high-fan-out relationship hubs (a node whose inbound-plus-outbound resolved-edge degree exceeds a configurable threshold), and a heuristic injection-style content flag (REQ-005); it MUST NOT reimplement cycle, duplicate-ID, orphan, broken-reference, or schema-drift detection, which remain owned by `validate` and `relationships --validate`.
- [REQ-003] For every finding, `rac doctor` MUST print the source path, a stable finding code, the problem, and a deterministic paste-ready fix — a runnable `rac` command (e.g. `rac relationships <dir> --validate`, `rac validate <path>`) or a literal edit instruction — never an auto-applied change (REQ-007, ADR-065).
- [REQ-004] `rac doctor` MUST flag relationship cycles and high-fan-out hubs in its report so authors can fix the data WS4 bounds at runtime; the cycle data is read from `relationships --validate`, and only the hub computation is doctor's own.
- [REQ-005] `rac doctor` MUST flag instruction-like / injection-style content — for example imperative overrides, impersonation of system/agent/tool instructions, or text steering an agent away from recorded decisions — as a deterministic, offline heuristic WARNING for human review (supports WS11); it MUST NOT auto-edit content, hard-fail a run on its own, or claim the content is unsafe — only that a human should look (ADR-065).
- [REQ-006] `rac doctor` MUST run fully deterministically and offline, with no AI, LLM, embeddings, or network access in any check (ADR-002, ADR-034, ADR-066); repeated runs on an unchanged corpus MUST produce byte-identical output.
- [REQ-007] `rac doctor` MUST exit non-zero only when a validation or relationship-integrity *error* is present, exit zero when the report holds only warnings (including every injection and hub finding), provide a `--json` mode emitting a `schema_version`-gated, additive contract (ADR-007), and be wired into CI alongside the existing validation gate.

## Acceptance Criteria

- `rac doctor` runs validate + relationships + the two new checks in one pass and
  prints, per finding, path, code, problem, and a paste-ready fix.
- A fixture exercising each defect class (malformed front matter, broken/cyclic
  relationship, duplicate ID, orphan, high-fan-out hub, injection-style content)
  produces the expected finding and fix.
- A planted injection-style fixture is flagged as a WARNING; the run still exits
  zero when no error-severity finding is present (a test asserts both the flag
  fires and the warning alone does not fail the run).
- Output is byte-identical across repeated runs on an unchanged corpus.
- A malformed artifact yields a clear `doctor` error rather than crashing
  `get_artifact` / `search_artifacts` (with WS4).

## Success Metrics

- A user can take a real repository from "unknown health" to "clean" by running
  one command and following its output, without reading RAC's source or knowing
  which of validate/relationships/review finds what.

## Risks

- The injection-content heuristic can false-positive. Mitigation: it is a
  reviewable WARNING for a human, never an auto-edit and never a standalone hard
  failure (REQ-005, ADR-065).
- Aggregating existing services could drift from their own output. Mitigation:
  doctor calls those services rather than copying their logic, so a finding it
  surfaces is the same finding `validate` / `relationships --validate` report.

## Assumptions

- The validator and relationship engine already detect every defect class except
  high-fan-out hubs and injection-style content; doctor aggregates and explains
  them with fixes, and adds only those two checks.
- The single-file `--corpus` resolution seam and the existing identifier index
  give doctor everything it needs to compute hub degree without a second model.

## Out of Scope

- Re-implementing any check `validate` or `relationships --validate` already owns
  (cycles, duplicates, orphans, broken/ambiguous/type-mismatch references, schema
  drift). Doctor composes them.
- Auto-editing, rewriting, or quarantining artifact content; doctor only reports
  and suggests (ADR-065).
- Treating the injection flag as a security guarantee or a CI hard-fail; the
  trust boundary stays human PR review (WS11, ADR-065).
- Any AI/LLM/embedding-based classification of "malicious" content.
- Multi-hop graph analysis beyond the one-hop degree count; traversal bounding is
  WS4's runtime concern (REQ-004).

## Related Decisions

- adr-055
- adr-051
- adr-049
- adr-065

## Related Requirements

- rac-parser-traversal-robustness
- rac-artifact-trust-model

## Related Roadmaps

- v0.23.0-hardening
