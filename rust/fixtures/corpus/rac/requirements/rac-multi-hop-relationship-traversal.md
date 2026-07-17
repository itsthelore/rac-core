---
schema_version: 1
id: RAC-KVH2PMJYV9FY
type: requirement
tags: [internal, relationships, traversal, mcp, determinism]
---
# Requirement: Bounded Multi-Hop Relationship Traversal

## Status

Accepted

Classification: `[internal]` — richer relationship answers. Scoped to the v0.24.0
visibility release (WS-D, Tier 2, cut-first). Extends the existing 1-hop
`get_related` to a bounded N-hop neighbourhood; no new MCP tool, additive output
(ADR-007).

## Problem

`get_related` (and `rac relationships`) returns one hop: an artifact's immediate
neighbours. Real questions an agent asks — "what decisions ultimately constrain this
requirement, including the ones reached through a design or a parent requirement?" —
span more than one edge. v0.23.0 deliberately kept traversal 1-hop (a Non-Goal), and
`rac-parser-traversal-robustness` REQ-010 pre-committed that any future multi-hop
traversal MUST add explicit depth, frontier, visited-set, and work-budget caps before
shipping. The gap is a *bounded* N-hop traversal that honours those caps and the ADR-033
response budget.

## Requirements

- [REQ-001] `get_related` MUST accept a bounded depth parameter (default `1`, preserving today's behaviour) that returns artifacts reachable within N hops, with N capped at a small documented maximum.
- [REQ-002] Traversal MUST enforce all four caps from `rac-parser-traversal-robustness` REQ-010 — maximum depth, maximum frontier size per level, a visited-set that prevents revisiting a node (cycle-safe), and a total work budget — and MUST terminate deterministically when any cap is reached, emitting a stable truncation marker consistent with ADR-033.
- [REQ-003] The full multi-hop response MUST stay within the ADR-033 response budget, truncating whole items (never mid-JSON) in a deterministic order; output MUST be byte-identical across repeated calls on an unchanged corpus.
- [REQ-004] Each returned artifact MUST carry its hop distance from the origin, and results MUST be ordered deterministically (by depth, then the existing relationship-type and ascending-id tie-break) so truncation is stable.
- [REQ-005] Traversal MUST remain stateless per call — re-read from disk, no session cursor or persisted graph (ADR-032) — and offline/deterministic, with no AI and no relevance ranking (ADR-002).

## Acceptance Criteria

- `get_related(id, depth=1)` is byte-identical to today's output.
- `get_related(id, depth=2)` on a fixture returns the 2-hop neighbourhood with per-item
  hop distances, deterministically ordered.
- A dense/cyclic fixture cannot exceed the depth, frontier, visited, or work caps, and
  produces a stable truncation marker.
- Repeated calls on an unchanged corpus are byte-identical; no network access occurs.

## Success Metrics

- An agent can retrieve a bounded transitive decision neighbourhood in one call, within
  budget, with no traversal blow-up on a hostile graph.

## Risks

- Combinatorial blow-up on dense graphs. Mitigation: the four REQ-010 caps as a hard
  precondition, fuzzed before ship.
- Budget truncation hides the nearest relevant hop. Mitigation: depth-ordered results
  surface nearer hops first; ordering stays deterministic, not relevance-scored.

## Assumptions

- The v0.23.0 relationship graph and response budget are sound foundations.
- A small depth cap (e.g. 2–3) covers the real questions without needing unbounded
  traversal.

## Related Decisions

- adr-033
- adr-055
- adr-032

## Related Requirements

- rac-parser-traversal-robustness

## Related Roadmaps

- v0.24.0-visibility
