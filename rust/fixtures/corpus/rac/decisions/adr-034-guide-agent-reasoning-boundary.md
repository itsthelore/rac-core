---
schema_version: 1
id: RAC-KTW0M81MVJ7D
type: decision
---
# ADR-034: Guide Agent Reasoning Boundary

## Status

Accepted

## Category

Product

## Context

The most tempting Guide tool is the one that answers the product's central
question directly: "does this change violate a recorded decision?" A
`check_conflict` tool would seem to deliver the grounding promise as a single
call.

It cannot be built honestly inside RAC. Deciding whether a proposed
implementation conflicts with a recorded decision is semantic inference —
it requires understanding what the code change means and what the decision
implies. RAC Core is deterministic by principle: structural validation, not
semantic scoring. A conflict verdict would either be a shallow keyword
heuristic dressed as judgment, or an LLM call embedded in Core — both
corrupt the one property that makes RAC's output trustworthy.

The division of labour is already in front of us: a capable reasoning engine
is the caller. The agent connected to Guide is precisely the component built
for semantic inference. What it lacks is not judgment but facts — the
artifacts, relationships, and repository state it never had in context.

The grounding demo is the proof: given the decision text at the right
moment, the agent itself recognizes the conflict and cites the decision. No
verdict tool is involved.

## Decision

Guide ships no conflict-detection, judgment, or synthesis tool.

- The server serves deterministic facts: artifacts, search results,
  relationships, validation and portfolio summaries.
- The consuming agent performs all reasoning over those facts — conflict
  recognition, implication, synthesis.
- RAC Core stays deterministic; no tool response contains a semantic verdict
  about user code or proposed changes.
- This boundary is permanent for Core. Any future judgment-shaped capability
  lives outside Core and arrives only through an explicit superseding
  decision.

## Consequences

### Positive

- Every Guide response is reproducible, testable, and explainable.
- The product claim stays honest: RAC supplies the facts, the agent supplies
  the judgment, and the demo shows the pair working.
- Guide improves as agents improve, with no RAC release required.
- Core's determinism — the property all consumers rely on — is preserved.

### Negative

- Guide cannot guarantee grounding: an agent may retrieve a decision and
  still violate it.
- "Why doesn't it just tell me if I'm violating something?" requires
  explanation in positioning and documentation.

### Risks

- The grounding behaviour is stochastic, so the value claim rests on
  citation rates rather than guarantees. Mitigation: the demo protocol
  measures it (8 of 10 scripted runs) and tool descriptions are engineered
  to put facts in front of the agent at the right moment.
- Competitive pressure to ship a verdict feature erodes the boundary.
  Mitigation: this decision names the line explicitly; crossing it requires
  superseding an accepted ADR, not drifting.

## Alternatives Considered

### A `check_conflict(id, proposal)` tool

Accept a proposed change and return a conflict verdict.

#### Advantages

- Directly answers the headline question in one call.

#### Disadvantages

- Honest implementation requires semantic inference Core must not contain.
- A heuristic version returns confident false verdicts — worse than no
  answer, because agents trust tool output.

### LLM inside the server

Embed a model call in Guide to render verdicts.

#### Advantages

- Real semantic judgment without faking it deterministically.

#### Disadvantages

- Violates AI-optional Core (ADR-002): RAC would require model access,
  keys, and network to serve its purpose.
- Nondeterministic output inside the deterministic contract surface.
- Duplicates the caller: there is already an agent in the loop.

### Keyword heuristics as "signals"

Ship deterministic lexical checks labelled as conflict signals.

#### Advantages

- Deterministic and testable.

#### Disadvantages

- Lexical overlap is not conflict; the signal would be wrong in both
  directions and consumed as a verdict regardless of labelling.

Serving facts and leaving reasoning to the agent is selected.

## Relationship to Other Decisions

- ADR-002 (AI optional): the reasoning engine stays outside RAC; Guide is
  how RAC serves it, not how RAC becomes it.
- ADR-008 (agent-ready architecture): anticipated agents as consumers of
  deterministic services — this decision keeps the consumed surface
  deterministic.
- ADR-017 (knowledge, not work management): the same instinct applied to
  inference — RAC manages recorded knowledge and declines the adjacent
  judgment business.
- ADR-030: bounds the four tools' semantics; this decision is why none of
  them is a verdict.

## Success Measures

- The grounded demo agent identifies the conflict and cites the decision ID
  in at least 8 of 10 scripted runs — with no verdict tool in the loop.
- Every Guide tool response remains byte-reproducible from repository state.
- Feature requests for conflict detection are answered by this ADR rather
  than by scope drift.

## Review Date

Review only alongside a decision that would place semantic capabilities
outside Core; the boundary for Core itself is not time-boxed.

## Related Requirements

- rac-agent-context-guide

## Related Designs

- guide-grounding-demo

## Related Roadmaps

- v0.10.0-guide-foundation
- v0.10.2-guide-grounding-demo
