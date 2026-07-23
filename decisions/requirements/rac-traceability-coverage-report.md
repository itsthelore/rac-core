---
schema_version: 1
id: RAC-KVJ6XB5MTVV4
type: requirement
tags: [user-facing, traceability, coverage, relationships, determinism]
---
# Requirement: Traceability Coverage Report

## Status

Accepted

Classification: `[user-facing]` — see where the knowledge graph is incomplete. Scoped to the v0.24.0 visibility release (WS-F). A deterministic report of typed traceability gaps over the existing relationship graph; no new schema, no AI, additive output (ADR-007).

## Problem

RAC detects relationship *integrity* problems — broken, cyclic, and orphaned references (`rac doctor`, `rac relationships`) — and counts artifacts by type (`rac stats`, `rac portfolio`). What no command reports is typed *coverage*: where the knowledge graph is incomplete by the team's own model. A requirement that no roadmap schedules is unimplemented intent; a decision that no requirement or roadmap applies is an unenforced choice; a roadmap that references no requirements is unscoped. These are valid, well-formed artifacts — they may carry other edges, so they are not orphans — yet each has a hole in the traceability chain (decision ← requirement ← roadmap). A maintainer who wants to ask "what have we decided but never built on?" or "what requirements are not on any roadmap?" has no answer short of reading the whole corpus by hand.

## Requirements

- [REQ-001] RAC MUST produce a deterministic coverage report identifying typed traceability gaps over the corpus relationship graph, covering at least: requirements referenced by no roadmap (unscheduled), decisions referenced by no requirement or roadmap (unapplied), and roadmaps that reference no requirements (unscoped). Gap classes MUST be derived from the existing relationship graph (incoming/outgoing references) and artifact types, not from a new schema field.
- [REQ-002] Coverage MUST be distinct from orphan detection and MUST NOT duplicate `rac doctor`'s `orphaned-artifact` finding: an artifact with inbound or outbound edges of other kinds can still be a coverage gap if it lacks the specific expected traceability edge. The report reports typed completeness, not generic reachability.
- [REQ-003] The report MUST be deterministic and offline: identical corpus bytes produce an identical, ordered gap list across repeated runs, with no AI/LLM/embeddings and no network (ADR-002).
- [REQ-004] The report MUST be exposed as a CLI surface (a `rac` subcommand or an additive section of an existing report) with human and JSON output (ADR-007); each gap MUST name the artifact path, its type, and the missing coverage relationship, and the JSON MUST be a stable, additive contract.
- [REQ-005] Coverage gaps MUST be advisory, never blocking: they are completeness signals for human judgement, not validation errors, so the report MUST NOT fail a build on a coverage gap alone (a roadmap may legitimately precede its requirements, a decision may be recorded before anything applies it). Coverage is informational and stays out of the `rac gate` enforcement path (ADR-049).
- [REQ-006] The typed coverage rules SHOULD derive their expected-edge expectations from the artifact specs and the relationship-type registry (ADR-055) rather than a hand-maintained per-type table, so adding an artifact type or relationship kind does not silently leave a coverage rule stale.

## Acceptance Criteria

- A fixture corpus with a requirement that no roadmap references reports exactly that requirement as an unscheduled-requirement gap; adding a roadmap reference to it clears the gap.
- A decision referenced only by another decision (not by any requirement or roadmap) is reported as an unapplied-decision gap — proving coverage is not orphan detection, since the decision has an inbound edge.
- The report exits `0` even when gaps are present (advisory).
- Output is byte-identical across repeated runs on an unchanged corpus; no network access occurs.

## Success Metrics

- A maintainer can list every unscheduled requirement, unapplied decision, and unscoped roadmap in one command, deterministically, without reading the corpus by hand.

## Risks

- The coverage rules become a brittle per-type table that drifts from the schema. Mitigation: REQ-006 derives expectations from the specs and the relationship registry.
- Coverage gaps are mistaken for errors and pressure teams into busywork. Mitigation: REQ-005 keeps them advisory and out of the enforcement gate.
- Intentionally standalone artifacts produce noisy "gaps". Mitigation: advisory framing now; an explicit opt-out marker is a possible later refinement, out of scope here.

## Assumptions

- The relationship graph (incoming/outgoing references) and artifact types are sufficient to compute typed coverage without a new schema field.
- Coverage is advisory: teams decide which gaps matter; RAC surfaces them, it does not enforce them.

## Related Decisions

- adr-055
- adr-016
- adr-020
- adr-002
- adr-007

## Related Requirements

- rac-traceability-self-relationships

## Related Roadmaps

- v0.24.0-visibility
