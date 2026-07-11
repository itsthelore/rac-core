---
schema_version: 1
id: RAC-KX8EACS410ZE
type: design
---
# Guide Capture Path — Agent-Originated Drafts Over MCP

## Status

Proposed

## Context

The Guide surface is read-only by decision (ADR-031, ADR-034): five tools,
no write-capable service imported, enforced by the MCP isolation battery.
Capture today is CLI + skill + human PR (the two-gate model, ADR-077). July
2026 demand research (`research/2026-07-agentic-tooling-demand.md`) shows
cross-session agent memory as a top unmet need, and the specific failure is
mid-session: an agent grounds through `lore`, makes or observes a decision
with its human, and has no path to record it through the same channel — the
knowledge evaporates when the session ends.

## User Need

A developer working with an agent that is already connected to `lore`. When
the session produces a decision, requirement, or design worth keeping, they
need the agent to draft it into the corpus *at the moment it happens*, with
no context switch to the CLI — while the team keeps the guarantee that
nothing enters the trusted corpus without human review by someone other
than the author.

## Design

Add a capture path that writes only untrusted drafts, keeping both gates of
ADR-077 intact:

- The capability mounts as a sibling write surface, not inside Guide
  (ADR-113): a separately-mounted module the Guide server layer never
  imports, so the ADR-031 isolation battery passes unchanged and any
  future desktop or web application face consumes the same write path.
- A single additive tool (working name `propose_artifact`) accepting a type,
  a title, and body Markdown. It runs `rac new` semantics (engine mints the
  id, canonical template, never overwrites), writes under the untrusted
  drafts location (`drafts/` or a capture branch, per ADR-077), validates
  structurally, and returns the draft path plus validation findings. It
  never writes into the trusted corpus tree and never merges.
- Gate one remains the human ratifying the draft in conversation; gate two
  remains promotion by human-reviewed PR (ADR-065). The tool automates only
  the mechanical write between the gates.
- The tool ships opt-in (off by default; enabled by explicit server flag or
  config) so the default Guide surface stays read-only for consumers who
  ratified that posture.
- The tool description instructs the agent to interview before proposing,
  mirroring the `rac-capture` skill's contract, and to report the draft
  path and next step (open a PR) to the human.

## Constraints

- ADR-034 (agent reasoning boundary) and ADR-031 (in-process core
  consumption) — the engine still never judges content; validation stays
  structural.
- ADR-030 pins the Guide tools-only surface and ADR-033 budgets it;
  ADR-113 resolves the mounting question — the capture surface is a
  sibling with its own pinned contract and budget, and Guide is not
  amended.
- ADR-065: artifact content is untrusted input; the draft location must be
  outside what `lore` serves as trusted grounding.
- ADR-077: both gates preserved; the tool must be incapable of promotion.
- HTTP serving (ADR-098) must scope the write path per-corpus and keep the
  audit trail (ADR-084) covering writes as well as reads.

## Rationale

The alternative interpretations — amend ADR-034 to allow general writes, or
keep capture CLI-only — either dissolve a settled safety boundary or leave
the demand unmet. Draft-only writes to an untrusted location change neither
the trust boundary nor the reasoning boundary: the corpus a consumer grounds
on is exactly as trustworthy as before. The two-gate model was designed for
precisely this shape of automation.

## Alternatives

- A separate `lore-capture` MCP server binary, fully outside Guide. Cleanest
  contract story, but doubles the setup burden the demand research flags as
  the adoption choke point, for the same effective surface.
- Deep links that pre-fill the `rac-capture` skill or CLI. Zero server
  change, but breaks the mid-session flow — the agent still cannot act on
  the channel it grounds through.
- Amending ADR-034 to permit trusted-tree writes with agent-side review.
  Rejected outright: it removes the human gate ADR-065 depends on.

## Open Questions

- Drafts location: `drafts/` directory versus capture branch — which does
  the promotion PR flow handle with less friction?
- Should the tool accept relationship links, or leave linking to the
  promotion review where the human can see resolution results?

## Related Decisions

- adr-030
- adr-031
- adr-033
- adr-034
- adr-065
- adr-077
- adr-084
- adr-098
- adr-113

## Related Roadmaps

- lore-capture-followups
- agentic-demand-alignment
