---
schema_version: 1
id: RAC-KWQAZXY975K3
type: design
---
# MCP Registration Helper

## Status

Proposed

Exploratory — Opportunity 3 of `adoption-opportunity-survey`. This is **not** a
new direction: `lore-frontend-optionality` (Thread D) already concluded that
distributing the MCP surface Lore ships is the highest-leverage move, and left
the *mechanism* — "should Lore ship a documented snippet or a `rac mcp init`
helper per host?" — as an Open Question. This design answers that mechanism
question so the recorded #1 lever can graduate from an open question to a
buildable item. It does not re-argue Thread D's conclusion.

## Context

`rac mcp` is a read-only stdio MCP server (ADR-029, ADR-030) that plugs into
every MCP host (Claude Code, Cursor, Codex, and peers) at child-process
latency. The barrier to that distribution is not capability — it is the
per-host wiring a team must hand-author (`.mcp.json` and each host's
equivalent) and the fact that `lore` is not listed where users discover MCP
servers. Thread D named this; nothing yet closes it.

## User Need

- A **team** adopting Lore for agent grounding wants to point every agent at the
  committed server in one step, without learning each host's config dialect.
- A **user browsing an MCP registry** should be able to find and install `lore`
  the way they find any other server — the discovery half of distribution.

## Design

Two complementary pieces:

1. **`rac mcp init [--host <host>]`** — an engine affordance that writes (or
   prints) the correct registration snippet for a host: the project-scoped
   `.mcp.json` block for Claude Code, and the documented equivalents for Cursor,
   Codex, and peers. It writes only registration config pointing at
   `rac mcp`; it introduces no new server capability and no write surface (the
   MCP surface stays read-only, ADR-029/030). Idempotent and additive.
2. **Registry listings** — publish `lore` in the MCP registries with a
   maintained `server.json`-style manifest, so discovery works without knowing
   the project exists.

## Constraints

- **Read-only, tools-only MCP (ADR-029, ADR-030).** This is distribution of the
  existing surface, never new write capability.
- **Thin config over the contract (ADR-063), additive (ADR-007).** `rac mcp
  init` emits registration config; it changes no engine behaviour and no
  existing output.
- **Brand/topology (ADR-068).** `rac mcp init` is an engine affordance (`rac-*`);
  a registry listing is a distribution artifact for the `lore` product.
- **Positioning stated, not altered (ADR-036).** Grounding-as-authority is the
  recorded identity; this distributes it, it does not reposition.

## Rationale

Thread D ranks this the cheapest path to the largest strategic payoff, and the
survey confirms it is the record's own #1 lever sitting unbuilt. The mechanism
is small (a snippet generator plus listings), reuses a shipped surface, and
compounds every other adoption lever — an agent that has `lore` registered is
an agent that can be grounded.

## Alternatives

- **Documentation only (no `rac mcp init`).** A per-host doc snippet is the
  minimum; the helper removes the copy-paste-and-adapt step. Ship the docs
  regardless; the helper is the affordance that makes it one command.
- **A new "installer" product.** Over-built: registration is config, not a
  product; the engine affordance plus registry listings suffice.
- **Leave it in Thread D as an open question.** The status quo — which is
  precisely why the record's top lever is unbuilt.

## Accessibility

`rac mcp init` output is plain text config a user can inspect before applying;
it never writes silently without showing what it wrote. Registry listings
follow each registry's accessibility conventions.

## Style Guidance

Neutral, factual snippets that match each host's documented format exactly.
Name the surface `lore` (ADR-036). No promotional framing in registry copy —
state what the server does (read-only decision grounding) and what it does not.

## Open Questions

- Which hosts does `rac mcp init` cover first (Claude Code project scope is the
  established pattern; Cursor and Codex next), and does it write files or only
  print?
- Which MCP registries are worth listing in, and who maintains the manifest as
  the surface evolves?
- Should this graduate to a `future/` roadmap item on its own, or ride the
  `agnostic-surfaces` / distribution track?

## Related Decisions

- adr-007
- adr-029
- adr-030
- adr-036
- adr-063
- adr-068

## Related Roadmaps

- growth-programme
- agnostic-surfaces
