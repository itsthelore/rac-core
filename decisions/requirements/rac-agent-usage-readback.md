---
schema_version: 1
id: RAC-KVH2PNQBMEWM
type: requirement
tags: [user-facing, telemetry, read-back, local-first, privacy]
---
# Requirement: Agent Usage Read-Back

## Status

Accepted

Classification: `[user-facing]` — the team can see how agents consult Lore. Scoped to the
v0.24.0 visibility release (WS-E). Promotes the future placeholder
`rac/roadmaps/future/agent-usage-readback.md` (now Superseded). Builds on the existing
local, content-free telemetry (ADR-040, ADR-041); its CLI-usage leg depends on ADR-046
(currently Proposed).

## Problem

RAC already records local, content-free Guide telemetry (ADR-040) and exposes it through
`rac mcp-stats`, but the signal is a diagnostic dump scoped to the four Guide MCP tools
during `rac mcp --telemetry` sessions. A maintainer who wants to *see grounding
happening* — which decisions agents read, how often, with what errors and truncations,
and whether usage is trending — has no read-back surface, and CLI usage (validate,
review, find, gate) is not recorded at all. The gap is a usable read-back over the
signals RAC may legitimately keep, without adding hosted infrastructure or recording any
content.

## Requirements

- [REQ-001] RAC MUST provide a read-back surface that summarises recorded agent Lore usage — per-tool/per-command counts, error and truncation counts, session count, and a recent-activity trend over the last N days — reading the existing local telemetry log and working within ADR-040's pinned, content-free event schema.
- [REQ-002] The read-back MUST remain content-free: it MUST NOT record or display argv, file paths, artifact IDs, query strings, or flag values — only the pinned, non-identifying fields (command/tool name, outcome, duration) (ADR-040, ADR-041).
- [REQ-003] Widening the recorded source to all `rac` CLI commands MUST be gated by the single existing consent record (no new consent mechanism), MUST record one content-free event per completed command to a separate local log, and MUST land only once ADR-046 (CLI Usage Telemetry) is Accepted; until then the read-back covers the Guide log only.
- [REQ-004] Telemetry MUST stay opt-in and default-off; with consent absent or declined, nothing is recorded and the read-back reports an empty result without error (ADR-040).
- [REQ-005] Sharing MUST reuse the existing local-first, user-submitted flow: a `--share` option builds a prefilled GitHub issue URL/string that the user reviews and submits in their own browser; RAC MUST NOT transmit telemetry itself beyond the existing opt-in anonymous ping (ADR-041, ADR-035).

## Acceptance Criteria

- The read-back command summarises the Guide log (counts, errors, truncations, sessions,
  N-day trend) deterministically and content-free.
- With consent off, the command records nothing and reports an empty read-back without
  error.
- `--share` produces a prefilled issue the user submits; no telemetry is sent by RAC.
- The CLI-usage leg is present only behind an Accepted ADR-046; absent that, only Guide
  usage is read back.

## Success Metrics

- A maintainer can answer "are agents actually consulting our decisions, and which
  ones?" from one local command, with no hosted infrastructure and no content captured.

## Risks

- Scope creep into content capture or a hosted dashboard. Mitigation: REQ-002 / REQ-005
  and the roadmap Non-Goals.
- Shipping CLI-usage recording ahead of its decision. Mitigation: REQ-003 gates it on
  ADR-046 acceptance.

## Assumptions

- ADR-040's pinned schema is sufficient for a useful Guide read-back without a schema
  change.
- ADR-046 will be accepted before the CLI-usage leg ships.

## Related Decisions

- adr-040
- adr-041
- adr-046
- adr-035

## Related Requirements

- rac-trust-transparency

## Related Roadmaps

- v0.24.0-visibility
