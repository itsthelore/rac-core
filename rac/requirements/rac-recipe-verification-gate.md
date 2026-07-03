---
schema_version: 1
id: RAC-KWK8HHCAHDJ5
type: requirement
---
# Requirement: Recipe Verification Gate

## Status

Proposed

Classification: `[internal]` — governs when a recipe becomes a listed,
verified integration. Initiative 3 of the `integration-recipe-factory`
roadmap.

## Problem

A recipe that is written is not yet a recipe that is proven. If unverified
recipes were listed as supported integrations, `docs/ecosystem.md` would
drift into a vague "works with any MCP client" claim — exactly what that
file's real-and-verified rule exists to prevent. The corpus needs a hard,
explicit line between "documented" and "verified against a released engine",
so a reader can trust every listed harness.

## Requirements

- [REQ-001] A harness recipe MUST be smoke-tested against a released `rac-core` engine version before its row is added to `docs/ecosystem.md`.
- [REQ-002] Until it is verified, a recipe MUST ship carrying the `verify against <client> <version>` marker (the convention already used in `docs/mcp.md`) and MUST stay off the `docs/ecosystem.md` table.
- [REQ-003] The verification close for every recipe MUST be the grounding demo (`examples/guide/`), so each recipe is proven against the same engine behaviour.
- [REQ-004] Each `docs/ecosystem.md` row MUST be real and verified — named harness, verified recipe, dated against the engine version it was smoke-tested on — with no row added before smoke-test.
- [REQ-005] The verification gate MUST NOT require any engine change: it is a documentation and process discipline over the existing surfaces.

## Acceptance Criteria

- A newly authored recipe that has not been smoke-tested appears only in
  `docs/mcp.md` with the `verify against <client> <version>` marker and does
  not appear in the `docs/ecosystem.md` table.
- After a smoke-test against a released engine version, the recipe gains a
  `docs/ecosystem.md` row naming the harness and the verified version.
- Every listed recipe's verification path runs the `examples/guide/`
  grounding demo.
- No `docs/ecosystem.md` row exists without a corresponding verified recipe.

## Success Metrics

- `docs/ecosystem.md` names every harness with a verified recipe and no
  others, so the ecosystem table stays trustworthy and the documented-versus-
  verified boundary stays explicit.

## Risks

- Stale config dialects: a harness changes its config format and a listed
  recipe silently rots. Mitigation: the `verify against <client> <version>`
  marker and this listing gate keep claims dated and re-verified against a
  released engine.
- Verification is skipped under delivery pressure and an unverified recipe is
  listed. Mitigation: REQ-004 makes the real-and-verified rule a precondition
  of the row, not a courtesy.

## Assumptions

- The grounding demo (`examples/guide/`) remains the stable, engine-level
  verification close that every recipe can run.
- Adoption signal, not completeness, decides which harnesses are worth
  verifying and listing.

## Related Decisions

- adr-007
- adr-008
- adr-030
- adr-031
- adr-063
- adr-067

## Related Roadmaps

- integration-recipe-factory

## Related Requirements

- rac-recipe-authoring-contract
