---
schema_version: 1
id: RAC-KVTRPAX62TWJ
type: roadmap
---
# RAC — Lean Context Delivery (Future)

## Status

Planned

Unscheduled — captured for future consideration from the team-scale (20+) market
research. It graduates out of `future/` into a versioned series when prioritised.

## Context

The research surfaced a real risk to how Lore *delivers* knowledge to agents. Two
independent findings converge: **"context rot"** is empirically established —
Chroma Research tested 18 frontier models and found every one degrades as input
length grows, well before the context window fills — so dumping a corpus actively
*worsens* output; and the **MCP "context tax"** is a live critique — Simon Willison
stopped using MCP for coding agents because tool descriptions "take up a lot of
valuable real estate" (GitHub's MCP server cited at ~23k tokens) and found CLI
utilities a lower-tax path. The practitioner guidance to keep instruction files
under ~200 lines is the same lesson from the other side.

The implication for Lore is sharp: **a knowledge server justifies itself only if it
stays lean — otherwise it becomes the noise it was meant to cure.** Lore already
has the right instincts recorded — a response budget (ADR-033), a minimal
tools-only surface, and a CLI-first posture (ADR-005) — but nothing yet *measures
and bounds* the agent-facing footprint, and the CLI-as-delivery path is
under-documented relative to MCP. This item makes leanness a measured property and
keeps the low-tax delivery option first-class.

## Outcomes

- The agent-facing footprint — tool descriptions, schemas, and response payloads —
  is measured and held within a stated token budget, so Lore does not become the
  context tax it warns against.
- Retrieval is selective and on-demand by default (pull the relevant artifact, not
  the corpus), the documented antidote to context rot.
- The CLI delivery path (`find` / `resolve` / `relationships`) is a documented,
  supported, low-context-tax alternative to the MCP server, not an afterthought.

## Initiatives

### Initiative 1 — Measure and bound the MCP surface

Audit the token cost of the MCP tool surface (descriptions + schemas) and the
typical response, and hold it to a budget — the leanness that ADR-033 asserts,
made measurable and regression-checkable.

### Initiative 2 — Selective, on-demand retrieval by default

Confirm and document that the default path retrieves the *relevant* artifacts, not
the whole corpus, so context rot is avoided by construction — small, scoped,
relevant payloads over bulk inclusion.

### Initiative 3 — CLI-first delivery as a first-class option

Document and, where needed, sharpen the CLI delivery path (`find`/`resolve`/
`relationships`) as the lowest-context-tax way to ground an agent — the path the
MCP critique favours (ADR-005), offered alongside the MCP server, not instead of
it.

## Constraints

- Deterministic and offline (ADR-066): no semantic compression or summarisation to
  shrink payloads.
- Selective delivery respects the response budget (ADR-033); both the MCP server
  and the CLI remain supported surfaces.

## Non-Goals

- Removing or deprecating the MCP server; this keeps both surfaces and makes the
  trade-off explicit.
- AI-based summarisation or compression of artifacts to fit a budget.

## Success Measures

- The agent-facing token footprint is measured and stays within its budget across
  releases.
- A team can ground an agent through the CLI path with materially lower context
  cost than a heavyweight tool surface, with documented guidance on when to use
  which.

## Assumptions

- Context rot and the MCP context tax are real and persistent enough that leanness
  is a durable design constraint, not a passing concern.
- A measured budget plus a documented CLI path is enough; no semantic compression
  is needed for a small, structured corpus.

## Risks

- Optimising for leanness could under-serve an agent that genuinely needs more
  context. Mitigation: selective on-demand retrieval lets the agent pull more when
  it asks, rather than front-loading everything.

## Related Decisions

- adr-033
- adr-005
- adr-066
