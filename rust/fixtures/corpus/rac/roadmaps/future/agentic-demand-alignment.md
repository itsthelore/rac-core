---
schema_version: 1
id: RAC-KX8EAJGK1XF1
type: roadmap
---
# Agentic Demand Alignment (Future)

## Status

Planned

Unscheduled — captured as future intent, not yet on a release. This item
organises the gap analysis against the July 2026 agentic-tooling demand
research; each initiative points at the artifact that owns the work.

## Context

Community demand research over the last-30-days window 2026-06-10 to
2026-07-10 (`research/2026-07-agentic-tooling-demand.md`) ranked the tool
categories indie, agent-equipped developers are actually asking for. Three
of the top ten — context-supply over MCP, spec-driven development, and
cross-session artifact memory — are one coherent gap that RAC's
architecture already targets, and the research concludes RAC should be the
substrate those workflows consume rather than compete with orchestrators,
verification gates, or review agents. A repo-grounded gap analysis found
the distance between that positioning and what is shipped. This roadmap
records the gaps in one place; performance and scalability gaps are
excluded because the native-core rewrite addresses them separately.

## Outcomes

- An agent connected to `lore` recovers from a paraphrased query instead
  of missing silently, and a corpus author can see why a query missed.
- An agent can draft a corpus artifact mid-session through the channel it
  grounds on, with both gates of the capture model intact.
- A roadmap item can be executed as fresh agent sessions without
  hand-assembled context: decomposition and context packets come from the
  corpus.
- Corpus staleness is a gate, not an advisory: drifted knowledge cannot
  silently remain trusted grounding.
- A newcomer reaches a well-structured, MCP-connected corpus without
  discovering conventions by trial and error.

## Initiatives

- **Answer the paraphrase gap.** Miss payloads with corpus vocabulary,
  explain-miss diagnostics, and the semantic sidecar for teams that want
  it. Owned by the `paraphrase-recall-response` design, with
  `retrieval-diagnostics` and `lore-supermemory-grounding`.
- **Agent-originated capture.** A draft-only write path on a sibling
  surface separate from Guide (ADR-113), preserving ADR-077's two gates
  and ADR-065's trust boundary, and reusable by a future desktop or web
  application face. Owned by the `guide-capture-path` design, alongside
  the host surfaces recorded in `lore-capture-followups`.
- **Own the spec-driven loop's boundary.** Issue decomposition and
  session context packets as deterministic exports, plus the
  `decisions-on-pr` surfacing lever whose dependencies already shipped.
  Owned by the `spec-driven-handoff` design.
- **Graduate freshness from advisory to gate.** The drift CI gate and
  freshness-biased retrieval fenced out of phase one of
  `freshness-and-drift-detection`, and the unbuilt code-scope drift
  consumer recorded in the `code-scope-consumption` seam.
- **Tool the cold start.** Opinionated corpus conventions, the mega-doc
  split recipe, and MCP registration guidance recorded in
  `corpus-setup-guidance`, treated as adoption work rather than docs
  polish.

## Success Measures

- Grounding eval gains a paraphrase family and its scores improve once
  miss payloads ship (ADR-066 keeps scoring deterministic).
- A capture draft created over MCP lands in the trusted corpus only ever
  via a human-reviewed PR — verified by test, not convention.
- A roadmap initiative round-trips to tracker issues and back through
  external-reference edges (ADR-087, ADR-096) with no hand-edited context
  files in the session transcripts.
- A corpus with drifted governed code fails the pre-merge tier (ADR-075)
  instead of passing with a doctor warning.

## Assumptions

- The demand signal holds: agent harnesses remain the primary consumer of
  team knowledge, and the community keeps preferring reviewable Markdown
  over opaque agent memory.
- The native-core rewrite lands the performance and scale floor, so none
  of these initiatives need to trade contract clarity for speed.
- Settled boundaries stay settled: no embeddings in core (ADR-066), no
  work tracking in RAC (ADR-017), read-only trusted grounding (ADR-065).

## Risks

- The capture surface's own contract and budget (ADR-113 requires both)
  are under-specified before implementation and drift the way the Guide
  surface's discipline was designed to prevent.
- Miss payloads bloat the response budget and degrade the hit path they
  were meant to protect.
- Decomposition export quietly becomes a tracker: scope discipline against
  ADR-017 must be tested, not assumed.
- Five initiatives invite scope creep into a single release; each is
  independently shippable and should be scheduled that way.

## Related Decisions

- adr-017
- adr-030
- adr-033
- adr-034
- adr-065
- adr-066
- adr-075
- adr-077
- adr-087
- adr-093
- adr-096
- adr-113

## Related Designs

- guide-capture-path
- paraphrase-recall-response
- spec-driven-handoff
- code-scope-consumption

## Related Roadmaps

- retrieval-diagnostics
- lore-supermemory-grounding
- lore-capture-followups
- freshness-and-drift-detection
- corpus-setup-guidance
- decisions-on-pr
