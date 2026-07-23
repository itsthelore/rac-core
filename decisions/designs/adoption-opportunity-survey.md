---
schema_version: 1
id: RAC-KWQAJG8WDSN1
type: design
---
# Adoption Opportunity Survey

## Status

Proposed

Exploratory — this records the output of a grounded adoption-opportunity
discovery pass so the reasoning lives in the corpus, not a session's scratch
space (ADR-047). It is not an accepted build. It surveys net-new adoption
levers, states each one's honest overlap with already-recorded work, and
leaves a recommended priority order rather than a closed decision. It states
positioning already recorded in ADR-036 and ADR-081; it does not alter it.

## Context

The prompt behind this survey was "review the codebase and identify 10x
products and features that would increase adoption." Run naively, that prompt
re-discovers work already planned or already shipping — because it has no step
that grounds each idea against the record first. So this survey did the
grounding first, and the honest headline is: **most of the obvious adoption
space is already recorded.** The roadmap and ADRs already own activation (the
`<5min` / `<30s` cold-start contract, `rac quickstart`, zero-config
`pipx`/`uv` install, the demo GIF — `rac-growth-adoption`, ADR-044),
positioning (`rac-growth-positioning`, the `decision-grounding-paper`),
capture surfaces (`lore-slack-bot`, `lore-overlay`, the agent-interview skill
and `/intake` action in `lore-frontend-optionality` Thread E), distribution
and CI reach (SARIF, `ci-report-formats`, `agnostic-surfaces`, `rac-editors`,
`oci-image`, `integration-recipe-factory`), RAG and enterprise
(`corpus-export-to-rag-backends`, `corpus-sync`, `lore-at-team-scale`,
`lore-supermemory-grounding`), and ecosystem (`rac-growth-extensibility`,
`rac-growth-ecosystem-list`, `artifact-family-factory`).

The single most important finding is a meta-one: `lore-frontend-optionality`
already concluded that the highest-leverage move is **distribution of the MCP
surface Lore already ships** (Thread D), and it sits there as an unbuilt Open
Question. The biggest lever is not undiscovered; it is un-scheduled.

What remains after grounding is a short, honest set of net-new levers,
recorded here so a future session inherits both the map and the ideas.

## User Need

- The **maintainer** deciding where the next unit of adoption effort buys the
  most, given how much is already recorded.
- **Future sessions**, which need the "already decided / already shipping" map
  as much as the ideas — the grounding step is what stops the next discovery
  pass from re-proposing (or re-building) settled work, the exact failure that
  produced a duplicated `freshness-and-drift-detection` build in the session
  that authored this survey.
- **Contributors** looking for a well-scoped, net-new place to help.

## Design

Grounding left a short, honest set of net-new levers. Each is recorded as its
own design for independent consideration; this survey is the **index** — it
holds the grounding, the already-decided map, and the priority order that are
*about the set*, not any single opportunity. Ordered by
(impact × confidence) ÷ effort:

1. **Decisions-on-PR surfacing** (`pr-decision-surfacing`) — *the
   recommendation*. A PR that edits governed code gets one comment naming the
   decisions that govern it, at the moment a reviewer or agent would otherwise
   ignore them. Distribution + retention; rides the just-shipped `rac decisions`
   / `## Applies To` lookup (`decision-to-code-proximity`). Cheap, net-new, and
   the most on-thesis idea in the set.
2. **Corpus status badge** (`corpus-status-badge`) — *the cheapest win*. A
   shields-style `Lore · N decisions · validated` badge an adopting repo renders
   from its corpus; a distribution loop over counts `rac` already emits. Distinct
   from RAC's own CI/coverage badges (`rac-trust-transparency` FR-6/FR-7).
3. **MCP registration helper** (`mcp-registration-helper`) — *scheduling the
   record's own #1*. `lore-frontend-optionality` Thread D already ranked MCP
   distribution first and left the mechanism (`rac mcp init` + registry listings)
   as an open question; that design answers it. Not a re-discovery — the
   scheduling of an already-recorded conclusion.
4. **Evaluator playground** (`evaluator-playground`) — *the highest ceiling, a
   real build*. A zero-install, paste-a-decision-see-it-validated surface that
   removes the install barrier `rac-growth-adoption` only shortens; gated on a
   hosting decision (hosted `rac` endpoint vs. Pyodide/WASM).

**Opportunity 5 — shareable public decision pages is deliberately not a separate
design.** Its own analysis concludes "fold in": a rendered, shareable decision
page rides the PR comment (design 1 links one) and the playground permalink
(design 4), rather than standing alone. Recorded here so the idea is not lost,
not as its own artifact.

The order above is the recommendation: do the two cheap distribution wins (1, 2)
first, schedule the record's top lever (3), and sequence the higher-ceiling build
(4) after its hosting question is settled.

## Constraints

- **Thin clients over the contract (ADR-063).** Every surface here consumes the
  published CLI/JSON/MCP output; none reimplements the engine. The badge, the
  PR comment, and the playground all read `rac`'s existing output.
- **RAC is not a content store (ADR-024).** The playground's pasted text and
  the badge's counts are ephemeral projections; artifacts stay on disk.
- **Facts, not verdicts (ADR-034); post-edit, not interception (ADR-067).** The
  PR comment names governing decisions and recommends review; it never blocks
  an edit or renders a judgement, and it augments the human PR trust boundary
  (ADR-065) rather than replacing it.
- **Additive contracts only (ADR-007).** Any new JSON (a shields shape, a
  playground response) is additive; `schema_version` is unchanged.
- **Brand and topology (ADR-068).** Installed surfaces (a hosted playground, a
  badge service) are `lore-*` products; engine affordances (`rac mcp init`, a
  `rac decisions --changed` mode) are `rac-*`.
- **Positioning is stated, not altered (ADR-036, ADR-081).** None of these
  repositions Lore or proposes the spec-as-source / codegen direction ADR-081
  refuses.

## Rationale

Two lines of reasoning shaped the ranking. First, **grounding before ideation
is the whole method** — it is what let this survey report five net-new items
honestly instead of ten padded ones, and it is exactly the step the original
prompt lacked. Second, **distribution of existing surfaces beats new builds**,
the same conclusion `lore-frontend-optionality` reached: the two cheapest wins
(the PR comment and the badge) turn output Lore already produces into reach,
and they compound capability that already shipped. A new build (the playground)
earns a lower rank precisely because its value is real but conditional on a
hosting decision.

## Alternatives

Deliberately excluded as re-discoveries — grounding is what kept them out:

- **MCP-as-frontend / grounding distribution** — recorded
  (`lore-frontend-optionality` Thread D); surfaced above only as "schedule it."
- **Any capture or non-technical authoring surface** — recorded (Thread E:
  agent-interview skill, `/intake` action, guided web-capture form).
- **A homegrown editor** — explicitly rejected (`lore-frontend-optionality`
  Thread B) on build/maintenance cost and the git-source-of-truth identity.
- **Semantic / RAG recall** — recorded (`corpus-export-to-rag-backends`,
  `lore-supermemory-grounding`).
- **Benchmarks and the paper** — recorded (`external-benchmark-evidence`,
  `decision-grounding-paper`, `artifact-completeness-benchmark`).
- **Enterprise / team scale** — shipped (`lore-at-team-scale`).
- **Editor / OCI / GitLab reach** — recorded (`rac-editors-buildout`,
  `oci-image`, `ci-report-formats`).

## Accessibility

Not a user interface. The bar is legibility of the analysis: each opportunity
traces its net-new claim to the record it was checked against (by roadmap
codename, design, or ADR id), so a reader can verify the grounding without
re-running the pass. Any surface that graduates from here inherits the
recorded accessibility constraints of its kind — keyboard-first parity for a
viewer (ADR-028), provenance legibility for a grounding surface.

## Style Guidance

Honest, non-promotional register — no "revolutionary" or "blazing." An
opportunity earns its rank with evidence and a falsifiable smallest-proof, and
overlaps with recorded work are stated plainly (Opportunity 3 and 5 lead with
their overlap). Cite recorded decisions by ADR id and related work by codename.

## Open Questions

- Should any of Opportunities 1–4 graduate to a `future/` roadmap item now, or
  stay recorded here until a build is scheduled?
- For the **playground (4)**: hosted `rac` endpoint or a Pyodide/WASM build,
  and where does it live under the `lore-*` brand (ADR-068)?
- For the **badge (2)**: is a static shields JSON shape enough, or is a small
  hosted endpoint warranted, and how is staleness communicated?
- **Coordination.** This repository has heavy parallel-agent activity; before
  any of these is built, re-run the claim check (open PRs, active branches) so
  a graduated item is not drafted twice — the discipline this survey exists to
  encode.

## Related Decisions

- adr-007
- adr-024
- adr-034
- adr-036
- adr-045
- adr-063
- adr-065
- adr-067
- adr-068
- adr-081

## Related Roadmaps

- growth-programme
- decision-to-code-proximity
- integration-recipe-factory

## Related Requirements

- rac-growth-adoption
- rac-growth-positioning
