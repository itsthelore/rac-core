---
schema_version: 1
id: RAC-KVWHTV28J65S
type: requirement
---
# Growth Positioning: Relating Lore/RAC to the Agent-Memory Category

## Status

Proposed

## Problem

"Agent memory" is the loudest adjacent category to Lore, and readers
arriving from it have no recorded answer to the obvious question: is Lore
another agent-memory store? The README leads with Lore's product identity
(ADR-036) and relates Lore to spec-driven-development tools and OKF
(rac-growth-positioning), but says nothing about the memory category, so
evaluators either misfile Lore as one more LLM-distilled memory store or
bounce without placing it.

The category splits on an axis Lore sits squarely on one side of, and the
distinction is currently unstated on any public surface:

- **LLM-distilled mutable stores** — Mem0, Zep/Graphiti, Cognee, Letta,
  OpenBrain/OB1, and the research framework Collaborative Memory — use an
  LLM to extract facts/entities at ingest into a mutable database, vector
  index, or temporal knowledge graph, and are overwhelmingly per-agent or
  per-user episodic memory rather than a human-reviewed shared source of
  truth. Zep/Graphiti is the most sophisticated: a bi-temporal knowledge
  graph that invalidates (without deleting) superseded facts. None routes
  knowledge through human review.
- **Git-native human-reviewed knowledge** — where Lore lives, and where
  its only genuine positioning competitors now sit. Two have appeared:
  **Mainline** (git refs/notes, no DB, no LLM distillation, decisions
  bound to commits) and **Kage** (files in git, reviewed in the same pull
  request as the code, citations validated against the repo, stale memory
  withheld). Both overlap Lore's git-native and provenance story; neither
  is a typed requirements/decisions corpus with human-ratified
  supersession (ADR-049, ADR-061).

A second, sharper problem: the convenient line "the only git-native
team-knowledge engine" is no longer true now that Mainline and Kage
exist, and must not appear on any surface. The defensible, still-true
distinction is narrower — Lore is the git-native team-knowledge engine
whose judgment is **human-ratified and typed**, not LLM-distilled
(ADR-049, ADR-065, ADR-080) — and that is what the README must state.

## Requirements

- [REQ-001] The README shall contain a single `##` section, placed below the fold (after the existing positioning sections and never above the Lore lead, per ADR-036), that relates Lore/RAC to the agent-memory category and states the axis thesis: most agent-memory products are LLM-distilled, mutable, and per-agent; Lore is a git-native, human-ratified, typed knowledge corpus — a different category, not a competing memory store.
- [REQ-002] The section shall name at least one representative LLM-distilled mutable store (Mem0 and/or Zep/Graphiti) and both git-native human-reviewed players (Mainline and Kage) explicitly, and shall not imply the list is exhaustive in a fast-moving space.
- [REQ-003] The section shall state Lore's two surviving differentiators in plain terms: (1) no LLM distillation of judgment — knowledge is authored and ratified by humans, not extracted by a model at ingest; (2) a human-ratification gate over a typed requirements/decisions corpus with explicit supersession and retained history, versioned in git.
- [REQ-004] The section shall NOT claim Lore is the only git-native team-knowledge system, and shall NOT claim Lore is better than any named product; it shall frame the relationship as a different category with a different trust model. Mainline and Kage shall be acknowledged as the closest git-native neighbours rather than diminished.
- [REQ-005] Every comparative claim in the section shall be verifiable from the named product's own repository or documentation, with the source URLs recorded in an HTML comment adjacent to the claim, and any claim that could not be verified shall be omitted rather than softened.
- [REQ-006] The section shall not assert capabilities for Lore that contradict recorded decisions — in particular it shall remain consistent with the no-semantic-verdict boundary (ADR-034), the deterministic no-embedding eval (ADR-066), and the git-not-a-database source of truth (ADR-080).

## Success Metrics

- The README section exists below the fold, satisfies REQ-001 to REQ-006
  on manual review, and the first screen of the README is byte-identical
  to its state before the section was added.
- Every comparative cell or sentence can be traced to a source URL in the
  adjacent HTML comment, and each URL substantiates the claim it is cited
  for.
- No surface (README, docs, outreach) contains the phrase "only
  git-native" or an equivalent exclusivity claim contradicted by Mainline
  or Kage.
- `rac validate rac/` and `rac relationships rac/ --validate` exit 0 with
  this artifact present.

## Risks

- The agent-memory space moves fast (most sources are dated 2025-2026);
  Mainline, Kage, Mem0 V3, Letta Context Repositories, and OB1 are all
  recent, so any comparison risks going stale and the recorded source
  URLs make staleness checkable but not self-healing.
- Comparative content, however neutral, can read as competitive
  positioning; the different-category, complements-not-attacks framing
  must hold in every revision.
- Competitor capability claims rest substantially on vendor
  self-description (mainline.sh, kage-core.com); they are appropriate for
  stating what a product claims, but not independently audited, and the
  section must attribute rather than assert them as fact.
- Naming specific competitors invites them to respond or to close the gap;
  the section should lead with Lore's durable distinction (human
  ratification of a typed corpus) rather than a transient feature delta.

## Assumptions

- ADR-036's positioning (Lore leads; the README first screen is settled)
  remains in force; this section is secondary positioning only.
- Mem0/Zep represent the LLM-distilled camp and Mainline/Kage represent
  the git-native human-reviewed camp well enough to stand in for the
  category; if the reference points shift, the section is revisited rather
  than extended.
- A README section, rather than a `docs/` page, is the right depth; a
  fuller competitive landscape belongs in the documentation layer or a
  design artifact, not the README.
- The distinction that matters to evaluators is the trust model
  (human-ratified vs model-distilled), not raw feature count; the section
  is written to that thesis.

## Related Decisions

- adr-036
- adr-049
- adr-065
- adr-080
