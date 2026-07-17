---
schema_version: 1
id: RAC-KV2H5328Q706
type: requirement
---
# RAC Traceability — Self-Type Relationship Gap

## Status

Accepted

<!-- Delivered by the v0.13.5 roadmap: the roadmap and decision schemas now
carry `related roadmaps` / `related decisions`, so REQ-001, REQ-002, and
REQ-003 are satisfied. The record is retained as the audit entry. -->


## Problem

RAC models cross-artifact relationships as `## Related <Type>` sections, but
only the pairs a given artifact type's schema lists become graph edges
(`spec.optional` ∩ the relationship vocabulary). Two relationships the corpus
needs in practice are not in any schema, so they cannot be expressed:

- **roadmap → roadmap** — a release series is inherently sequential (each
  milestone follows the last and precedes the next), but the roadmap schema has
  no `related roadmaps` section.
- **decision → decision** — an ADR routinely builds on, contrasts with, or
  depends on other ADRs beyond the narrow `supersedes` case, but the decision
  schema has no `related decisions` section.

The failure is silent, which makes it worse than a missing feature. Authors
write `## Related Roadmaps` on roadmaps and `## Related Decisions` on
decisions; the sections pass validation (extra sections are allowed), render as
prose, and contribute **zero edges** — with no warning. The relationship graph,
`rac portfolio` coverage, the Explorer, and the Lore MCP server therefore
understate real traceability, and authors believe they have linked artifacts
that are in fact disconnected.

This record is the Growth Programme's "traceability gap audit" output for these
two types: a concrete, designable gap evidenced by existing corpus instances.
It documents the gap and the requirements a fix must satisfy; it does not
implement a schema change (that is a separately scoped, version-fenced piece of
work).

## Evidence

Concrete instances already in the corpus where a declared section produces no
edge:

- **roadmap → roadmap (11 instances):** every milestone of the v0.13.x series
  (`v0.13.0`–`v0.13.4`), the v0.12.x series (`v0.12.1`, `v0.12.2`,
  `v0.12.3` each naming its predecessor), `v0.10.5-bundled-agent-skill`,
  `v0.10.5-review-and-ingest-skills`, and `v0.7.0-relationship-metadata`.
- **decision → decision (8 instances):** `adr-017`, `adr-019`, `adr-036`
  (declares `Related Decisions: ADR-029`, dropped), `adr-037`, `adr-038`,
  `adr-039`, `adr-042`, and `adr-045` (declares `adr-013`, `adr-017`,
  `adr-025`, `adr-043`, all dropped).

## Requirements

- [REQ-001] The relationship vocabulary can express a roadmap's references to other roadmaps, so a release series' sequencing (predecessor/successor and sibling links) becomes graph edges resolved and validated like any other relationship.

- [REQ-002] The relationship vocabulary can express a decision's references to other decisions, distinct from the existing `supersedes` relationship, so an ADR can link the ADRs it builds on or relates to as graph edges.

- [REQ-003] Until self-type relationships are supported, a `## Related <SameType>` section that the schema does not consume does not fail silently: it is surfaced (for example as a `rac review`/`rac validate` advisory) so authors learn the link produced no edge, rather than believing it did.

- [REQ-004] This record stays the consolidated audit entry for self-type relationship gaps: each missing source→target pair is enumerated with at least three concrete corpus instances (see Evidence), specific enough to design a schema change from.

- [REQ-005] Any fix preserves the existing relationship contracts: `supersedes` keeps its current decision-only semantics and JSON shape (ADR-007), and adding a self-type section to a schema is additive, never repurposing an existing section.

## Success Metrics

- The graph edge count rises to include the previously-dropped self-type
  references once a fix ships (the Evidence instances resolve instead of being
  silently discarded).
- No `## Related <Type>` section that names the artifact's own type is silently
  ignored: it either resolves to edges or is reported.
- The audit entry enumerates every missing self-type pair with ≥3 instances,
  reviewed against the live corpus rather than asserted.

## Risks

- Allowing roadmap→roadmap and decision→decision edges could invite cycles
  (A relates to B relates to A). Mitigated by treating these as undirected
  "related" links, as the existing `related_*` sections already are, rather
  than as ordering or dependency semantics.
- Adding sections to schemas changes classification surface; a careless change
  could shift how borderline documents classify. Mitigated by additive-only
  section changes and the existing adjacent-type misclassification tests.

## Assumptions

- The relationship model stays "structural references in Markdown sections"
  (ADR-016); this gap is about the vocabulary, not the mechanism.
- `supersedes` remains the right home for decision-replacement semantics; this
  gap is about general decision-to-decision association, not replacement.

## Related Roadmaps

- growth-programme
- v0.13.5-self-type-relationships

## Related Decisions

- adr-016
