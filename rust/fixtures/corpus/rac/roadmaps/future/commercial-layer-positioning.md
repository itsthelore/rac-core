---
schema_version: 1
id: RAC-KVW1DQDE04B6
type: roadmap
---
# RAC — Commercial Layer Positioning (Future)

## Status

Planned

Unscheduled — captured as future intent for the first commercial offering built
on top of an open Lore corpus. Nothing here is committed scope; it graduates out
of `future/` into a versioned series when a commercial offering is actively
pursued (the review trigger ADR-012 already names). This item records the
*positioning thesis and competitive shape* of that layer, not its build plan —
the enabling technology is recorded separately (`lore-at-team-scale`,
`freshness-and-drift-detection`, `corpus-export-to-rag-backends`).

## Context

A growing class of products — runtime "AI memory" / context-assembly layers that
sit between a team and the frontier models — pitch the thesis Lore already holds:
*the model is not the moat, context is* (ADR-081, ADR-036). They compete on the
**assembler** — the runtime that is smart at the moment of query, backed by
implicit memory that "learns from every interaction." That layer is the
commoditising one: everyone builds it, over the same models, and its accumulated
memory is unaudited and unreproducible.

ADR-012 (Open Core) already drew the line for where Lore's commercial value sits,
and it is deliberately *not* the assembler. The corpus format, CLI, validation,
local MCP, and import/export stay open; commercial value is reserved for
**repository-scale and organisational intelligence** — hosted corpora, multi-repo
aggregation, the knowledge graph, governance/audit, enterprise reporting, and
MCP-compatible knowledge services. The named mental model is git → GitHub,
Terraform → Terraform Cloud: the spec and local tooling stay open, hosted and
org-scale capabilities carry the commercial value.

The strategic consequence is that a Lore commercial layer should not try to
**out-assemble** the runtime products. It should be the **governed, always-fresh,
multi-tenant source of truth those assemblers — including a runtime memory
product — read from.** Not a better Copilot; the GitHub that sits under the
Copilots. This item records that positioning so the README, growth artifacts, a
pitch, and the eventual offering derive from one stance, consistent with
ADR-081's rule that every claim be verifiable and stated as complementary, never
"better than."

## Outcomes

- There is a recorded answer to "how would a commercial layer on top of Lore
  compete, and against what," that the team, the README, and any pitch derive
  from — distinct from `growth-programme` (adoption of the open product) and
  `lore-at-team-scale` (the enabling server/cache technology).
- The layer competes on a **different axis** from runtime memory/assembler
  products: trusted, fresh, governed *substrate* rather than runtime assembly —
  so it is positioned as the layer beneath that category, not a rival inside it.
- The two differentiators competitors structurally cannot show — deterministic
  freshness/drift detection, and a published grounding benchmark — are named as
  the load-bearing commercial investments, consistent with ADR-081's honesty that
  both are currently unproven or unbuilt.
- The open-core trust story (ADR-012) and the no-inference-in-the-engine identity
  (ADR-035, ADR-069) survive the commercial layer intact: the layer adds hosted
  intelligence over the corpus without taking custody of it or putting a model in
  the engine.

## Initiatives

### Initiative 1 — Record the competitive stance ("substrate, not assembler")

A positioning artifact (extending `rac-growth-positioning` and ADR-081) that
states the axis: runtime memory/assembler products sell a smarter runtime plus
accumulated implicit memory; the Lore commercial layer sells the trusted, fresh,
multi-tenant source of truth that any such runtime reads from. The posture is
complementary — "plug your assembler into a governed corpus and it stops citing
stale decisions" — never "better than." The corpus lives in the customer's own
git (ADR-080), which is simultaneously the architecture and the anti-lock-in
differentiator against both runtime-memory black boxes and enterprise RM lock-in.

### Initiative 2 — Name the commercializable surface against ADR-012

Enumerate the offering as the repository-/org-scale intelligence ADR-012 already
reserves, each tied to a recorded enabling item: the always-current hosted
endpoint (`lore-at-team-scale`); deterministic freshness/drift detection
(`freshness-and-drift-detection`); multi-repo decision graph and governance/audit
over typed edges (ADR-074); provenance and compliance reporting off git history;
and an MCP-compatible knowledge service downstream consumers — including a runtime
memory product — read from (`corpus-export-to-rag-backends`, ADR-073). Each entry
states what it competes on, not just what it is.

### Initiative 3 — Fix the packaging axis: per-org, not per-seat

Record the pricing/packaging shape that the git → GitHub pattern (ADR-012)
implies and that ADR-081 makes a positioning pillar: the whole team reads, and
the charge is for org-scale intelligence and governance — *zero per-seat
collaboration tax*. Per-seat pricing is the enterprise-RM failure mode ADR-081
calls out; refusing it is a competitive weapon, not just a price point.

### Initiative 4 — Record the discipline boundary

State explicitly that the commercial layer must not drift into runtime inference,
assembly, or codegen — the moment it does, it becomes the assembler it is
positioned beneath and forfeits the determinism and open-core trust that
differentiate it. Inference-adjacent capability is a sibling product, per the
Wayfinder precedent (ADR-069, ADR-035, ADR-049). The commercial layer is
repository-scale *knowledge* intelligence — deterministic, hosted, governed.

## Constraints

- Every positioning claim is verifiable and stated as complementary, never
  "better than" (ADR-081, `rac-growth-positioning`).
- The corpus stays files-in-git as the single source of truth; the commercial
  layer is hosted intelligence over it, never custody of it or a competing store
  (ADR-080, ADR-024).
- No model or inference enters the engine; runtime-inference concerns are sibling
  products, not commercial features of Lore (ADR-035, ADR-069, ADR-002).
- The open core stays open: this layer adds org-scale capability above the
  specification, it does not restrict core artifact functionality (ADR-012).

## Non-Goals

- Building or out-competing a runtime assembler / "AI memory" product. The layer
  is the substrate such products read from, not a rival to them.
- Any claim of proven agent-task uplift before the grounding benchmark (ADR-066)
  publishes it, or any claim that drift detection ships before it does.
- A database or central system of record other than git (ADR-080); a per-seat
  pricing model; or repositioning the open product's README-first identity
  (ADR-036).
- Pre-committing build scope — the enabling technology is owned by
  `lore-at-team-scale`, `freshness-and-drift-detection`, and
  `corpus-export-to-rag-backends`; this item owns only the positioning.

## Success Measures

- A single recorded stance answers "how does a commercial layer on top of Lore
  compete, and against what," and the README, growth work, and any pitch cite it
  rather than improvising.
- Every commercial-surface claim traces to an ADR-012-reserved capability and a
  recorded enabling item, and every competitive claim carries a verifiable,
  complementary framing (no "better than" survives review).
- The positioning names per-org (not per-seat) packaging and the no-inference
  discipline boundary explicitly, so neither is re-litigated ad hoc.
- `rac validate rac/`, `rac relationships rac/ --validate`, and `rac review rac/`
  stay clean over this item.

## Assumptions

- ADR-012's open-core boundary remains the governing split; commercial value sits
  in repository-/org-scale intelligence, not in restricting core functionality or
  in the assembler layer.
- Teams that want a hosted, always-current, governed source of truth their agents
  and assemblers read from are a real commercial segment, distinct from the
  local-clone open-product audience.
- The freshness/drift differentiator and the grounding benchmark are achievable
  and are where commercial investment concentrates, consistent with ADR-081
  recording both as currently unproven or unbuilt.

## Risks

- The layer drifts into runtime assembly/inference to chase the hot category,
  forfeiting the determinism and open-core trust that differentiate it.
  Mitigation: the discipline boundary (Initiative 4) and the Wayfinder precedent
  (ADR-069) keep inference in a sibling product.
- Positioning outruns reality: the two strongest pillars (drift detection, the
  benchmark) are unbuilt/unproven today (ADR-081). Mitigation: claims stay framed
  as future intent and the Non-Goals forbid asserting them as shipped.
- The offering reads as "another store beside Confluence/Slack" rather than the
  source of truth in the team's own repo (ADR-081's named failure mode).
  Mitigation: the corpus-in-customer-git framing (ADR-080) is stated on every
  surface.
- Three-name positioning (RAC engine, Lore product, the commercial layer) adds
  brand-explanation load. Mitigation: the commercial layer is described as a
  Lore-branded hosted tier, not a fourth name, consistent with ADR-068's
  install-vs-engine naming principle.

## Related Decisions

- adr-012
- adr-081
- adr-080
- adr-074
- adr-073
- adr-069
- adr-066
- adr-049
- adr-036
- adr-035

## Related Roadmaps

- lore-at-team-scale
- freshness-and-drift-detection
- corpus-export-to-rag-backends
- growth-programme

## Related Requirements

- rac-growth-positioning
