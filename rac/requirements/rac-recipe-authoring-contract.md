---
schema_version: 1
id: RAC-KWK8HFX5RWPP
type: requirement
---
# Requirement: Recipe Authoring Contract

## Status

Proposed

Classification: `[internal]` — a contributor-facing authoring contract, not
a CLI behaviour. Initiative 1 of the `integration-recipe-factory` roadmap.

## Problem

Each new harness integration is added ad hoc, yet the shapes recur: the same
`command: rac, args: [mcp, --root, .]` server invocation in three config
dialects, the same push/pull/enforcement README structure, and the same
"verify with the grounding demo" close. Without a named template a contributor
must reverse-engineer the pattern from an existing `examples/<client>/`
directory, and each fresh recipe risks drifting in structure — most
dangerously into describing a pre-edit hook as enforcement, which would
contradict the recorded boundary (ADR-067).

## Requirements

- [REQ-001] A documented recipe template MUST capture the recurring shape: a push/pull/enforcement README skeleton, the same `lore` server invocation expressed in the three config dialects (JSON, TOML, YAML), and the standard verification close pointing at `examples/guide/`.
- [REQ-002] The template MUST be authored the same way an artifact is created from its template (ADR-021): a contributor produces a new `examples/<client>/` recipe by filling the template, without reading another recipe.
- [REQ-003] Every recipe's enforcement section MUST describe context-supply plus post-edit CI only (ADR-067 / ADR-065), never a pre-edit interception hook, restated identically across recipes so the boundary never drifts.
- [REQ-004] Recipes MUST consume only the two stable integration surfaces — the generated agent-instructions file (`rac export --agent-rules`) and the `lore` MCP server (ADR-008, ADR-030, ADR-031) — as additive, stable contracts (ADR-007, ADR-063); no recipe introduces engine code or a new served surface (ADR-024).
- [REQ-005] The template MUST NOT require any `rac-core` engine change to add a harness: authoring a recipe is documentation work with a zero engine diff.

## Acceptance Criteria

- A contributor produces a structurally consistent `examples/<client>/`
  recipe (README plus the three-dialect config) from the template and its
  checklist alone, without opening an existing recipe.
- Every recipe's enforcement section reads identically in boundary terms —
  context-supply and post-edit CI — with no pre-edit hook described.
- The verification close of each recipe references `examples/guide/`.
- Adding the recipe leaves the `rac-core` engine unchanged (no source diff).

## Success Metrics

- New harness recipes land with a consistent structure and zero engine diff,
  so footprint grows by repeating a cheap, on-thesis recipe rather than by
  per-harness code.

## Risks

- The template ossifies against one config style and rots when a harness
  changes format. Mitigation: the dialects are examples of the same
  invocation, and the verification gate (`rac-recipe-verification-gate`)
  keeps every claim dated and re-verified.
- A harness offering a pre-edit hook tempts a recipe to use it as
  enforcement. Mitigation: REQ-003 fixes the enforcement section to ADR-067.

## Assumptions

- The "MCP server plus agent-instructions file" pattern remains the de-facto
  way harnesses consume external context, so one recipe shape serves most
  targets.
- The export and the `lore` server stay stable additive contracts (ADR-007,
  ADR-063), so the invocation block is durable.

## Related Decisions

- adr-007
- adr-008
- adr-021
- adr-024
- adr-030
- adr-031
- adr-063
- adr-065
- adr-067

## Related Roadmaps

- integration-recipe-factory

## Related Requirements

- rac-recipe-verification-gate
