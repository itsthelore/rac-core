---
schema_version: 1
id: RAC-KW7VKGRAN30J
type: requirement
---
# RAC Traceability — Typed Relationship Edges

## Status

Proposed

## Problem

Authors want to say *how* one artifact relates to another — it implements a
decision, depends on a requirement, satisfies a roadmap — but the vocabulary has
only untyped `## Related <Type>` links. So authors invent edge-label sub-headings
(`### Implements`, `### Depends On`) that nothing validates and that no consumer
can query. The graph export already surfaces typed edges (ADR-074); the authoring
side has no matching, validated vocabulary.

This is gap 3 of the traceability audit.

## Evidence

- `adr-028-explorer-surface` uses `### Implements` inside a non-schema section.
- `rac-product-knowledge-navigator-explorer` invents `### Depends On`.
- Historic (now archived) `v0.10.3-search-quality` listed implemented decisions
  and standing-constraint decisions in one flat `## Related Decisions` list.

## Requirements

- [REQ-001] The relationship vocabulary can type an edge within a `## Related <Type>` section using a recognised, validated edge label (for example `### Implements`, `### Depends On`, `### Satisfies`), defaulting to an untyped relationship when no label is present.

- [REQ-002] Typed edges are surfaced consistently with the graph export's existing typed-edge representation (ADR-074), so authoring and export agree on the vocabulary.

- [REQ-003] The change is additive (ADR-007): an untyped `## Related <Type>` section keeps its current meaning and JSON shape; typing is opt-in and labelled.

- [REQ-004] Typed-edge labels do not change classification: adding labels to a section the schema already recognises must not shift how a document classifies (adjacent-type tests hold).

## Success Metrics

- The invented sub-headings in the evidence become validated typed edges.
- `rac relationships` and the graph export report the same edge types.
- Untyped relationships are byte-identical before and after.

## Risks

- Edge-label vocabulary can sprawl; mitigated by a small fixed, validated set
  decided in the design/ADR.
- Sub-headings inside sections complicate parsing; mitigated by reusing the
  shared Markdown parser and additive extraction.

## Assumptions

- A small fixed label set covers the real need; free-text edge types are out of scope.

## Related Decisions

- adr-016
- adr-074
- adr-007

## Related Roadmaps

- relationship-vocabulary
