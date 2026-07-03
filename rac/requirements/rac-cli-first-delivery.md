---
schema_version: 1
id: RAC-KWK8HNKZ4WQM
type: requirement
---
# Requirement: CLI-First Delivery as a First-Class Option

## Status

Proposed

Classification: `[external]` — a user-facing, documented delivery path.
Initiative 3 of the `lean-context-delivery` roadmap.

## Problem

The MCP context tax has driven practitioners toward CLI utilities as a
lower-tax path to ground an agent — the tool-description real estate an MCP
server spends is real, and a CLI spends none of it until invoked. Lore already
has a CLI-first posture (ADR-005) and the surfaces to deliver it (`find`,
`resolve`, `relationships`), but the CLI-as-delivery path is under-documented
relative to MCP, so the lowest-context-tax option reads as an afterthought
rather than a supported choice.

## Requirements

- [REQ-001] The CLI delivery path (`find` / `resolve` / `relationships`) MUST be documented as a supported, first-class way to ground an agent, not an afterthought to the MCP server.
- [REQ-002] The documentation MUST give explicit when-to-use-which guidance between the CLI path and the MCP server, framed around context cost (ADR-005).
- [REQ-003] Both surfaces MUST remain supported: the MCP server is neither removed nor deprecated by promoting the CLI path — the trade-off is made explicit, not resolved by dropping a surface.
- [REQ-004] The CLI delivery guidance MUST rely only on existing commands and their stable contracts; it introduces no new command or engine behaviour (documentation and, where needed, sharpened existing help).

## Acceptance Criteria

- The docs describe grounding an agent through `find`/`resolve`/`relationships`
  as a supported path, with a worked example.
- The docs state when to prefer the CLI path over the MCP server and vice
  versa, in context-cost terms.
- The MCP server remains documented and supported; nothing marks it deprecated.
- No new CLI command is required for the guidance to hold.

## Success Metrics

- A team can ground an agent through the CLI path with materially lower context
  cost than a heavyweight tool surface, guided by documentation on when to use
  which.

## Risks

- Promoting the CLI path reads as steering users away from MCP. Mitigation:
  REQ-003 keeps both surfaces first-class and frames the choice as a
  context-cost trade-off, not a deprecation.
- The guidance drifts from the actual commands as they evolve. Mitigation:
  REQ-004 ties the guidance to existing stable contracts and their help output.

## Assumptions

- The `find`/`resolve`/`relationships` commands already deliver the grounding
  an agent needs, so this documents and sharpens rather than builds.
- A documented CLI path plus the measured MCP budget is enough; no semantic
  compression is needed for a small, structured corpus.

## Related Decisions

- adr-005
- adr-033
- adr-066

## Related Roadmaps

- lean-context-delivery

## Related Requirements

- rac-mcp-surface-budget
- rac-selective-retrieval-default
