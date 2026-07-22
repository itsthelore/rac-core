---
schema_version: 1
id: RAC-KW7VKEX21GW6
type: requirement
---
# RAC Traceability — Roadmap Supersession Edge

## Status

Proposed

## Problem

A roadmap can be replaced by a successor — a series folded into another, a plan
supplanted by a later one — but the relationship vocabulary cannot express it.
`## Supersedes` exists for decisions only; roadmaps carry a `Superseded` lifecycle
*status* (ADR-061) but no edge to the artifact that replaced them. So "what
superseded this roadmap?" is unanswerable as a graph query, and the replacement
link lives in prose that dangles when files move.

This is gap 5 of the traceability audit.

## Evidence

- The single-item series flattened during the v0.28–v0.30 → codename renames,
  whose predecessors are superseded with no edge.
- `repo-extraction-programme` superseded by the `repo-topology` series in prose only.
- `growth-programme` absorbed earlier `future/` items whose supersession is implicit.

## Requirements

- [REQ-001] The roadmap schema accepts a `## Supersedes` section, so a roadmap can reference the roadmap(s) it replaces as a resolved, validated edge.

- [REQ-002] A roadmap `## Supersedes` target is existence-checked by `rac relationships --validate`, including targets under `archive/`, so a replaced roadmap stays reachable.

- [REQ-003] The change is additive (ADR-007) and preserves the existing `supersedes` semantics: it extends the section to the roadmap type without altering its decision-only behaviour or JSON shape.

## Success Metrics

- A roadmap declaring `## Supersedes` resolves to an edge; a missing target is reported.
- The evidence instances become declared edges, raising the resolved-edge count.
- `supersedes` on decisions is byte-identical before and after.

## Risks

- Supersession chains could form cycles; mitigated by validating targets and
  treating supersession as a directed-but-acyclic check, as for decisions.

## Assumptions

- `supersedes` remains the right home for replacement semantics (per the self-type
  audit entry); this only extends which types may use it.

## Related Decisions

- adr-016
- adr-061
- adr-007

## Related Roadmaps

- relationship-vocabulary
