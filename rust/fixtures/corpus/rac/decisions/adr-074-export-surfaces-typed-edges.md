---
schema_version: 1
id: RAC-KVK19NPWFYC9
type: decision
---
# ADR-074: The Graph Export Surfaces Typed Relationship Edges

## Context

`rac export` (`src/rac/services/export.py`) deliberately flattens every
relationship to a single untyped `relates-to` edge. The code says so explicitly:
"richer typing (supersedes/refines/implements) is reserved for a future decision,
not an export invention." That flattening is correct for the Portal viewer, whose
v1 contract (`CorpusExport.to_dict`) is reconciled with the vendored viewer and
must stay stable (ADR-007).

The typed graph nonetheless already exists inside the engine:
`extract_relationships_full` plus the relationship-type registry (ADR-055) give
`supersedes`, `related_decisions`, `related_requirements`, … each with declared
direction and acyclicity, and that is what relationship validation runs on.

The v0.25.0 graph export (`rac export --graph`, requirement
`rac-corpus-graph-export`, design `corpus-export-shape-contract`) exists precisely
to hand graph backends RAC's real decision topology rather than one inferred from
prose. That requires surfacing the typed edges — the "future decision" the export
code reserved. This ADR records that decision.

## Decision

The `rac export --graph` projection **surfaces typed relationship edges** taken
from the relationship-type registry (ADR-055):

- Each edge carries its registry `type` (`supersedes`, `related_decisions`,
  `related_requirements`, `related_roadmaps`, `related_designs`,
  `related_prompts`) and a `directed` flag derived from the registry
  (`supersedes` is directed; the `related_*` edges are undirected).
- This applies **only** to the new `--graph` projection. The default viewer JSON
  (`CorpusExport.to_dict`) keeps its flattened, untyped `relates-to` edges
  unchanged — the graph projection is separate and additive (ADR-007), so the
  viewer contract is not touched.
- Edge typing is derived from the registry and the same resolution validation
  uses, never a hand-maintained table, so adding a relationship kind does not
  leave the export stale.

This lifts the export's self-imposed "untyped only" restriction for the graph
projection alone, and leaves it in place for the viewer payload.

## Consequences

### Positive

- Graph backends (Neo4j, Graphiti, Cognee) receive RAC's real, validated typed
  graph instead of an LLM-inferred one — the differentiator behind the export-to-
  graph work.
- Typing comes from one declarative source (the registry), so it cannot drift from
  what validation enforces.
- The viewer's stable `relates-to` contract is untouched; the change is additive.

### Negative / trade-offs

- A second edge representation now exists (flattened `relates-to` for the viewer,
  typed for `--graph`). Accepted: they serve different consumers, and both derive
  from the same resolved graph, so they cannot disagree on *which* edges exist —
  only on how much type detail is exposed.

### Risks

- The typed projection is mistaken for a change to the viewer contract.
  Mitigation: the decision scopes typing to `--graph` only and states the viewer
  payload is unchanged; a test asserts the viewer JSON is byte-stable.

## Status

Accepted

Accepted with the v0.25.0 WS2 graph-export delivery (`rac export --graph`); the
documents projection (WS1) does not depend on it.

## Category

Technical

## Alternatives Considered

### Keep all export edges untyped (`relates-to`)

Rejected for the graph projection: it defeats the purpose of exporting to a graph
backend, which is to convey the real typed topology rather than a flat
adjacency the backend would then try to re-infer.

### Add typing to the viewer JSON as well

Rejected: the viewer's v1 contract is stable and reconciled with the vendored
viewer (ADR-007); changing it is out of scope and unnecessary. Typing is added
only where it is consumed — the `--graph` projection.

## Related Decisions

- adr-007
- adr-055
- adr-063

## Related Designs

- corpus-export-shape-contract

## Related Roadmaps

- v0.25.0-connect
