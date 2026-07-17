---
schema_version: 1
id: RAC-KW7VKPCEKR98
type: requirement
---
# RAC Lifecycle — Status and Gate Vocabulary

## Status

Proposed

## Problem

Artifact Status is already a validated enum per type (for example a requirement
is `Proposed | Accepted | Superseded | Deprecated`), but two lifecycle states the
corpus uses in practice are missing, and gate state is unstructured. Work that is
parked reads `Proposed` with no way to say `Deferred`; work blocked behind a gate
records it as a free-text line (`Blocked: GATE-2 (CLA not yet in place)`) that
nothing can enumerate. So "everything blocked behind GATE-1" is not a query.

This is gap 4 of the traceability audit (narrowed: the status enum exists and is
validated; the residue is the missing states and gate-status-as-data).

## Evidence

- `rac-growth-contribution-policy` is blocked behind GATE-2 in prose.
- `rac-growth-positioning` and several growth requirements are gated behind GATE-1
  in free-text assumptions, not enumerable.
- Parked work reads `Proposed` with no `Deferred` state to distinguish it.

## Requirements

- [REQ-001] The validated status vocabulary gains a `Deferred` state (intentionally parked) distinct from `Proposed`, applied consistently across the artifact types that carry a status enum.

- [REQ-002] A blocked state is expressible with a structured reason (for example a `Blocked` status plus a single gate-reason field), so blocked artifacts can be enumerated by gate.

- [REQ-003] The additions are additive (ADR-007, ADR-051): existing status values keep their meaning and `retired_status` semantics; new values are appended, never repurposing existing ones.

- [REQ-004] The new states are validated like the existing enum (a value off the allowed set is an error), and do not change which statuses count as retired unless explicitly specified.

## Success Metrics

- A query can list every artifact `Blocked` behind a named gate.
- `Deferred` distinguishes parked work from `Proposed` in the corpus.
- Existing status values validate byte-identically before and after.

## Risks

- Status creep blurs the knowledge-vs-work line (ADR-017); mitigated by keeping
  the vocabulary small and lifecycle-oriented, not a task tracker.

## Assumptions

- A small fixed set of additional states suffices; arbitrary workflow states are
  out of scope.

## Related Decisions

- adr-051
- adr-017
- adr-007

## Related Roadmaps

- relationship-vocabulary
