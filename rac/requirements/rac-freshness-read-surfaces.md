---
schema_version: 1
id: RAC-KWK4VBB4K0D3
type: requirement
---
# Requirement: Freshness on Read Surfaces

## Status

Proposed

Classification: `[internal]` — staleness visible where artifacts are
picked. Initiative 1 (phase 1) of the `freshness-and-drift-detection`
roadmap.

## Problem

Recency exists in the engine (ADR-045) and on the MCP `get_artifact`
response, but the surfaces where readers and agents actually *pick*
artifacts — find and search — show nothing about age, so decay is
invisible exactly where selection happens. A five-year-old superseded-in-
spirit artifact and one touched yesterday look identical in a result list.

## Requirements

- [REQ-001] Read surfaces MUST additively surface git-derived recency: at minimum, `rac find` search output and MCP `search_artifacts` results gain last-committed recency and a staleness indicator, joining the provenance `get_artifact` already embeds — additive per ADR-007, `schema_version` unchanged.
- [REQ-002] Every surfaced field MUST derive from the existing git-derived recency service (ADR-045); no frontmatter freshness field is read, written, or introduced.
- [REQ-003] Outside a git repository, for untracked files, or where history cannot answer, fields MUST degrade to null or absent gracefully — never an error, never a fabricated date (the ADR-045 posture).
- [REQ-004] The staleness indicator MUST be a documented deterministic function of last-committed age against an explicit threshold (configurable, with a stated default), reported as data beside its underlying date — never a score or verdict beyond it (ADR-034).
- [REQ-005] Recency fields MUST NOT change search matching or ordering in this phase: result sets and ranking are identical to pre-change behaviour for the same corpus — the ADR-078 ranking contract and its goldens are untouched; the retrieval-bias later phase rides its own scoped work.
- [REQ-006] Byte-pinned goldens MUST stay stable: fixtures either fully control git state or the byte-pinned goldens exclude the git-derived fields; the existing golden suite passes unchanged.
- [REQ-007] MCP additions MUST respect the response budget (ADR-033), with truncation behaviour unchanged.

## Acceptance Criteria

- A fixture repository with controlled commit dates yields the expected
  recency and indicator on find and search output, byte-identical across
  repeated runs.
- The same corpus outside git yields null or absent fields with shape and
  exit codes otherwise unchanged.
- Ranking and ordering goldens are unchanged: identical result ordering
  before and after on the ranking fixture suite.
- The budget test on an oversized corpus passes with the fields present.
- The full byte-pinned golden suite is green with no golden edits except in
  fixtures that pin git state.

## Success Metrics

- A reader or agent choosing between search results can see which artifact
  has decayed without opening it — the loud signal the trust-collapse
  evidence calls for.

## Risks

- The indicator reads as a correctness verdict. Mitigation: REQ-004 reports
  it as data beside its date, with "review recommended" framing owned by
  the roadmap.
- Golden churn from uncontrolled git state. Mitigation: REQ-006 is the
  council's golden-stability constraint made testable.

## Assumptions

- The existing recency service's per-call cost is acceptable on the widened
  surfaces; if scale says otherwise, the derived-index cache work
  (`rac-derived-index-cache`) is the recorded seam, not a new one.
- One age threshold with a stated default is enough for phase 1; per-type
  cadences remain `rac review`'s territory.

## Related Decisions

- adr-002
- adr-007
- adr-033
- adr-034
- adr-045
- adr-066
- adr-078

## Related Roadmaps

- freshness-and-drift-detection

## Related Requirements

- rac-drift-advisory-finding
