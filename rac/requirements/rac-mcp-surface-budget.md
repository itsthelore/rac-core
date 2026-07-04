---
schema_version: 1
id: RAC-KWK8HJTQ9DP1
type: requirement
---
# Requirement: Measured MCP Surface Budget

## Status

Accepted

Classification: `[internal]` — a measured, regression-checked property of the
agent-facing surface. Initiative 1 of the `lean-context-delivery` roadmap.

## Problem

A knowledge server justifies itself only if it stays lean; otherwise it
becomes the context tax it was meant to cure. The MCP "context tax" is a live
critique — tool descriptions and schemas consume real estate before any
answer is returned — and context rot is empirically established, so an
oversized surface actively worsens agent output. Lore records the right
instinct as a response budget (ADR-033), but nothing yet *measures* the
agent-facing footprint, so drift is invisible: a description edit or a new
field can inflate the surface with no signal.

## Requirements

- [REQ-001] The agent-facing footprint MUST be measured by a documented deterministic method: the token cost of the MCP tool descriptions, their JSON schemas, and a typical `search_artifacts`/`get_artifact` response over a fixed fixture corpus.
- [REQ-002] The measurement MUST be computed offline with no model call and no network (ADR-066): a fixed, reproducible number for a fixed input, per the method recorded in the `lean-context-delivery-measurement` design.
- [REQ-003] The measured footprint MUST be held to a stated budget and checked as a regression, so an increase is a visible, reviewable failure rather than silent drift — the leanness ADR-033 asserts, made measurable.
- [REQ-004] The measurement MUST NOT change the served surface: it counts the existing five-tool surface and its responses; it adds no tool, removes none, and shrinks payloads by no semantic compression or summarisation (ADR-066).
- [REQ-005] The budget check MUST respect the existing response budget (ADR-033): the two are consistent, with the response-budget truncation behaviour unchanged.

## Acceptance Criteria

- Running the measurement on the fixed fixture yields the same token number
  across repeated runs on the same input, with no network or model call.
- An edit that inflates a tool description or schema past the stated budget
  fails the regression check; a change within budget passes.
- The five-tool surface is unchanged by the measurement — no tool added or
  removed, no payload compressed.

## Success Metrics

- The agent-facing token footprint is measured and stays within its budget
  across releases, so Lore does not become the context tax it warns against.

## Risks

- A budget set too tight could pressure the surface into under-serving an
  agent. Mitigation: the budget is stated and reviewable, and selective
  on-demand retrieval (`rac-selective-retrieval-default`) lets an agent pull
  more when it asks rather than front-loading everything.
- The "typical response" fixture drifts from real usage and the number stops
  meaning anything. Mitigation: the fixture and method are pinned in the
  `lean-context-delivery-measurement` design and versioned with the check.

## Assumptions

- The context tax and context rot are durable design constraints, not a
  passing concern, so a measured budget earns its keep.
- A deterministic token count over a fixed fixture is a faithful-enough proxy
  for the agent-facing footprint; no semantic modelling is needed.

## Related Decisions

- adr-005
- adr-033
- adr-066

## Related Roadmaps

- lean-context-delivery

## Related Designs

- lean-context-delivery-measurement

## Related Requirements

- rac-selective-retrieval-default
- rac-cli-first-delivery
