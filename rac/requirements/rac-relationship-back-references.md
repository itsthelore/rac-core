---
schema_version: 1
id: RAC-KW7VKJKDZV7B
type: requirement
---
# RAC Traceability — Relationship Back-References

## Status

Proposed

## Problem

Relationships are declared on one side. An artifact that is heavily referenced
cannot advertise who cites it, and nothing warns when an expected reverse edge is
absent — so an agent landing on a target cannot discover the citing artifact, and
asymmetric links go unnoticed. The `unlinked-reference` advisory (ADR-082)
surfaces prose mentions, not this. No schema change is needed: this is a
detection gap.

This is gap 6 of the traceability audit.

## Evidence

- ADR-036 ← `v0.10.2`: the roadmap references the decision; the decision carries
  no reverse link.
- Several early ADRs cited by `rac-agent-context-guide` carry no `## Related`
  sections themselves.
- Decisions referenced by many requirements rarely link back to any of them.

## Requirements

- [REQ-001] `rac relationships --validate` (and/or `rac doctor`) emits an advisory finding when a resolved relationship edge is not reciprocated, naming the source, the target, and the missing reverse section.

- [REQ-002] The finding is advisory: it exits zero and does not change the `rac validate` / `rac relationships --validate` contract, consistent with the existing advisory findings (ADR-075).

- [REQ-003] The check is deterministic and offline (ADR-002): identical corpus bytes yield identical findings, with stable ordering and no schema change.

## Success Metrics

- The evidence asymmetries are surfaced as advisory findings.
- Exit codes are unchanged with and without the new advisory present.
- Re-running on an unchanged corpus is byte-identical.

## Risks

- Not every edge should be reciprocal, so a naive check is noisy; mitigated by
  scoping the advisory to edge kinds where a back-reference is expected and
  keeping it advisory, never gating.

## Assumptions

- `related_*` edges are undirected, so reciprocity is about discoverability, not
  ordering semantics.

## Related Decisions

- adr-016
- adr-082
- adr-075
- adr-002

## Related Roadmaps

- relationship-vocabulary
