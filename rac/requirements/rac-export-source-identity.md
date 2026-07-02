---
schema_version: 1
id: RAC-KWJ4VMKVSS65
type: requirement
---
# Requirement: Multi-Corpus Source Identity

## Status

Proposed

Classification: `[internal]` — merge N corpora with zero collisions.
Feature E of the `corpus-sync` programme: one configured, deterministic
source identity stamped across all projections, and a documented
consumer-side aggregation recipe. Explicitly not federation (ADR-089).

## Problem

The export projections stamp the corpus directory's basename as the corpus
identity, so in practice every RAC repository exports as the same source
value. An organisation aggregating two corpora into one backend collides
immediately on that key — even though artifact ids already carry a
per-repository key prefix that makes bare-id collisions impossible
(ADR-026). Consumption-side aggregation needs a stable, configured source
identity; it does not need federation semantics in the engine, which stay
deferred per ADR-089.

## Requirements

- [REQ-001] All three projections MUST stamp one consistently derived corpus identity: an explicit export-source key in the repository configuration when present, else a value derived from the repository key, else the current directory-basename fallback — one shared derivation used by the viewer, documents, and graph builders.
- [REQ-002] The value MUST land in the projections' existing source fields, and additively as a source field in the viewer payload's corpus block whose existing name field is byte-unchanged, so the viewer contract is untouched (ADR-007, ADR-063).
- [REQ-003] The derivation MUST be deterministic and spelling-independent: any argument spelling of the same initialised corpus and any checkout location produce the same source value (ADR-002).
- [REQ-004] Documentation MUST publish a consumer-side aggregation recipe: N corpora merge by concatenating documents streams and unioning graph nodes and edges, keyed globally on `(source, id)`; the recipe MUST state that distinct repository keys make bare-id collisions impossible (ADR-026) and that cross-corpus references remain unresolved edges, resolvable only consumer-side.
- [REQ-005] This capability MUST NOT introduce federation semantics: no inheritance, no cross-corpus resolution or validation in the engine, and no change to relationship validation — ADR-089 stays deferred and untouched.
- [REQ-006] The value-precedence change MUST ship with a documented migration note for consumers keyed on the old basename value, since the field shape is unchanged but the default stamped value changes for initialised repositories.

## Acceptance Criteria

- With an explicit export-source key configured, all three projections
  carry that value; with only a repository key, they carry the derived
  value; with no repository configuration at all, output is byte-identical
  to today's basename fallback and existing goldens are unchanged.
- A merge test over two fixture corpora with distinct repository keys
  asserts zero `(source, id)` collisions and zero bare-id collisions.
- Exporting the same corpus under different argument spellings of the same
  directory produces byte-identical output.
- The viewer payload gains the additive source field while the existing
  name field's bytes are unchanged, and the updated schemas validate all
  outputs.

## Success Metrics

- An organisation aggregates multiple corpora into one backend keyed on
  `(source, id)` with no collision handling code of its own.

## Risks

- Consumers keyed on the old basename value are surprised by the new
  default for initialised repositories. Mitigation: REQ-006's migration
  note, and the unconfigured fallback preserving today's value exactly.
- Source identity is mistaken for federation and scope creeps toward
  cross-corpus resolution. Mitigation: REQ-005 walls federation off
  explicitly; ADR-089's sequencing is unchanged.

## Assumptions

- Per-repository key prefixes on artifact ids remain the uniqueness
  guarantee aggregation relies on (ADR-026).
- Aggregation lives entirely in consumers and connectors; the engine emits
  one corpus per invocation (ADR-073).

## Related Decisions

- adr-002
- adr-007
- adr-026
- adr-063
- adr-073
- adr-080
- adr-085
- adr-089

## Related Designs

- corpus-export-shape-contract

## Related Roadmaps

- corpus-sync

## Related Requirements

- rac-export-contract-schemas
