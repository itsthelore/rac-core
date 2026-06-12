---
schema_version: 1
id: RAC-KTYB8944G7TN
type: requirement
---
# Growth Positioning: Relating Lore/RAC to Spec-Driven Development Tools

## Status

Proposed

## Problem

Readers who arrive at the repository already knowing spec-driven
development (SDD) tools — GitHub Spec Kit, OpenSpec, Kiro — have no
recorded answer to the obvious question: is this another one of those?
The README leads with Lore's product identity (ADR-036) but never
relates it to the SDD category, so evaluators either misfile Lore as a
competing SDD workflow tool or bounce without placing it at all.

The distinction matters and is currently unstated in any public
surface: SDD tools manage the *change* — proposal, design, tasks — and
treat requirements as ephemeral inputs that are consumed and archived.
RAC manages the *requirements* as a durable, versioned, governed corpus
that persists across changes. RAC is the layer above SDD tools, not a
competitor to them.

## Requirements

- [REQ-001] The README shall contain a single `##` section, placed below the fold (after the "Who it's for" section and never above the Lore lead), that relates Lore/RAC to spec-driven development tools and states the layer-above thesis: SDD tools manage the change and treat requirements as ephemeral inputs; RAC manages requirements as a durable, versioned corpus that persists across changes, a layer above SDD tools rather than a competitor to them.
- [REQ-002] The section shall name GitHub Spec Kit and OpenSpec explicitly.
- [REQ-003] The section shall contain a comparison table whose rows are capability dimensions (requirement persistence, change management, traceability, tool coupling, install footprint), restricted to rows for which every column's claim has been verified.
- [REQ-004] Every claim in the comparison table shall be verifiable from the named tool's own repository or documentation, with the source URLs recorded in an HTML comment adjacent to the table.
- [REQ-005] The section shall frame the relationship as complementary — Lore/RAC owns a different layer — and shall contain no claim that Lore or RAC is better than any named tool, and no claim that cannot be verified.

## Success Metrics

- The README section exists below the fold, satisfies REQ-001 to
  REQ-005 on manual review, and the first screen of the README is
  byte-identical to its state before the section was added.
- Every table cell can be traced to a source URL in the adjacent HTML
  comment, and each URL substantiates the cell it is cited for.
- `rac validate rac/` and `rac relationships rac/ --validate` exit 0
  with this artifact present.

## Risks

- Competitor documentation changes after publication, leaving a table
  cell stale; the recorded source URLs make staleness checkable but not
  self-healing.
- Comparison content, however neutral, can read as competitive
  positioning; the complements-not-competitor framing must hold in
  every revision.
- Kiro's documentation site could not be fetched for verification at
  the time of writing, so Kiro is named in prose as part of the SDD
  category but excluded from the table; this asymmetry may read as an
  omission.

## Assumptions

- ADR-036's positioning (Lore leads; the README first screen is
  settled) remains in force; this section is secondary positioning
  only.
- GitHub Spec Kit and OpenSpec remain the most recognisable named SDD
  tools for the README's audience; if the category's reference points
  shift, the section should be revisited rather than extended.
- A README section, rather than a `docs/` page, is the right depth for
  this comparison; anything longer belongs in the documentation layer.

## Related Decisions

- adr-036
