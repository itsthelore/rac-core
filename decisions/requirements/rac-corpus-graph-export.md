---
schema_version: 1
id: RAC-KVK19MJNE7KX
type: requirement
tags: [internal, export, graph, relationships, determinism]
---
# Requirement: Corpus Graph Export

## Status

Accepted

Classification: `[internal]` — give graph backends RAC's real decision graph.
Delivered in v0.25.0 (WS2): `rac export --graph`. A deterministic nodes+edges
projection that surfaces the typed relationship graph (ADR-074, now Accepted).

## Problem

GraphRAG-style backends (Neo4j, Graphiti, Cognee) build a knowledge graph from
documents — typically by having an LLM *infer* entities and edges from prose,
fuzzily and non-deterministically. RAC already owns a typed, validated
relationship graph (ADR-055): artifacts are nodes, and `supersedes` / `related_*`
are typed, directional-or-not edges that relationship validation already computes.
But the current export flattens every edge to an untyped `relates-to` and exposes
no node/edge projection, so a graph backend cannot consume the real graph and is
forced to re-infer it. RAC should hand the graph over directly — deterministic and
curated — so the backend reflects the team's actual decision topology.

## Requirements

- [REQ-001] RAC MUST provide an additive `rac export --graph` mode that emits a nodes+edges projection of the corpus, deterministically and offline, without altering the existing default export payload (ADR-007, ADR-002).
- [REQ-002] Nodes MUST carry the canonical `id`, `type`, `status`, and `title`; edges MUST carry `source` and `target` canonical ids, the edge `type` taken from the relationship-type registry (`supersedes`, `related_decisions`, …), and a `directed` flag derived from the registry — `supersedes` directed, `related_*` undirected (ADR-055).
- [REQ-003] Surfacing typed edge types rather than the viewer's flattened `relates-to` MUST follow ADR-074; the viewer JSON's `relates-to` contract MUST remain unchanged, the graph projection being separate and additive.
- [REQ-004] Resolved references MUST become canonical-id edges; unresolved references MUST be preserved with the literal target and flagged unresolved, never silently dropped and never inventing a phantom node (matching how the existing export preserves unresolved targets).
- [REQ-005] Output MUST be deterministic: identical corpus bytes produce a byte-identical graph across runs (sorted nodes and edges, no timestamps), with no AI/LLM/embeddings and no network (ADR-002, ADR-066).

## Acceptance Criteria

- `rac export --graph` over a fixture corpus with a supersession chain and several
  `related_*` edges emits nodes for every classified artifact and edges whose types
  and direction match `rac relationships`' resolved typed graph.
- A `supersedes` edge is `directed: true`; a `related_decisions` edge is
  `directed: false`.
- An unresolved reference appears as an edge flagged unresolved with its literal
  target, and creates no node.
- The default `rac export` output is unchanged; two runs produce byte-identical
  graph output.

## Success Metrics

- A graph backend ingests `rac export --graph` and reflects RAC's real
  `supersedes`/`related_*` topology, with no LLM inference step.

## Risks

- The typed-edge surfacing leaks into or changes the viewer's `relates-to`
  contract. Mitigation: REQ-003 and ADR-074 keep `--graph` a separate, additive
  projection.
- Edge typing drifts from the registry. Mitigation: REQ-002 derives types and
  direction from the relationship-type registry, not a hand-maintained table.

## Assumptions

- The relationship-type registry and the resolution that validation performs are
  sufficient to emit typed, directed edges without a new schema (ADR-055).
- ADR-074 is accepted before this workstream ships (it is Proposed until then).

## Related Decisions

- adr-002
- adr-007
- adr-055
- adr-063
- adr-066
- adr-074

## Related Designs

- corpus-export-shape-contract

## Related Roadmaps

- v0.25.0-connect
