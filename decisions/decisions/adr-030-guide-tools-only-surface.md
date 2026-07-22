---
schema_version: 1
id: RAC-KTW0M8184YYT
type: decision
---
# ADR-030: Guide Tools-Only Surface

## Status

Accepted

## Category

Product

## Context

MCP offers three primitives a server can expose: tools, resources, and
prompts.

Client support is not uniform across them. Tools are the one primitive every
target client (Claude Code, Claude Desktop, Cursor) invokes reliably and
autonomously: the agent decides to call a tool mid-task based on its
description. Resources commonly require user attachment, and prompts require
user invocation — neither fits the grounding goal, where the agent must reach
for repository knowledge at the moment it becomes relevant without being
told.

There is also a surface-discipline question. An earlier roadmap stub
(v1.2-mcp-server) sketched a broad tool-per-command surface: validate, diff,
stats, inspect, review. Each additional tool dilutes the description budget
agents use to choose tools, and widens the contract surface that must be
pinned by tests and kept stable.

The wedge the Agent Context Guide requirement must prove is narrow: an agent
retrieves the right artifact at the right moment and respects it.

## Decision

Guide v1 exposes tools only — no MCP resources, no MCP prompts.

The surface is exactly four read-only tools:

- `get_artifact` — one artifact by identifier, metadata plus content
- `search_artifacts` — query search with optional type filter
- `get_related` — one artifact's declared and incoming relationships
- `get_summary` — repository-level overview

Tool descriptions are a designed product surface: they are the only interface
the agent sees when deciding whether to call, so their text is engineered for
triggering and pinned verbatim in the `guide-tool-surface` design artifact.

The broad tool-per-command surface sketched in the v1.2 roadmap stub is
explicitly superseded by this decision.

## Consequences

### Positive

- Every exposed capability works identically in all target clients.
- Four descriptions fit comfortably in agent context; each earns attention.
- The pinned contract surface stays small enough to test exhaustively.
- The grounding demo depends only on primitives agents invoke autonomously.

### Negative

- Capabilities like validate, diff, and review are not reachable over MCP in
  v1, even though Core exposes them.
- Clients with good resource support get no resource listing of the corpus.

### Risks

- Four tools may prove too few for real agent workflows. Mitigation: the
  surface is additive — new tools are an extension, not a break, and demand
  is observable through user reports.
- Description text that triggers well on today's models may regress on
  future models. Mitigation: descriptions are pinned in a design artifact
  and measured by the demo's citation rate, so drift is detectable.

## Alternatives Considered

### Resources for artifacts

Expose each artifact as an MCP resource.

#### Advantages

- Natural mapping: one artifact, one resource URI.

#### Disadvantages

- Inconsistent client support; commonly requires manual user attachment.
- Resources take no parameters, so search and filtering still need tools.
- Does not serve the autonomous-retrieval goal.

### Prompts for workflows

Ship MCP prompts encoding RAC workflows.

#### Advantages

- Could encode grounding instructions directly.

#### Disadvantages

- User-invoked, not agent-invoked; the grounding moment is missed.
- Prompt support varies most across clients.

### Broad tool-per-command surface

Mirror the CLI: validate, diff, stats, inspect, review, resolve, find as
tools.

#### Advantages

- Maximum capability exposure from day one.

#### Disadvantages

- Dilutes tool-selection attention across many descriptions.
- Multiplies the pinned-contract and testing surface.
- None of the extra tools serves the provable wedge.

Tools only, exactly four, is selected.

## Relationship to Other Decisions

- ADR-003 (structured outputs first): tool responses reuse the structured
  shapes Core already emits.
- ADR-008 (agent-ready architecture): Guide is the first dedicated agent
  consumer of the service layer that decision prepared.
- ADR-026 (opaque artifact identities): tools accept and return the same
  identifiers the resolver owns.
- ADR-029 defines how Guide ships; this decision defines what it exposes.
- ADR-034 bounds what the tools may compute.
- ADR-067 additively extends this surface with a fifth read-only tool,
  `find_decisions` — the additive-extension path this decision anticipated (see
  Risks). The tools-only surface and the four foundational tools above remain in
  force; this is an extension, not a supersession.

## Success Measures

- All four tools work unmodified in Claude Code, Claude Desktop, and Cursor.
- The grounded demo agent selects the right tool without prompt-side tool
  coaching.
- No v1 issue requires a resource or prompt to resolve.

## Review Date

Review when a concrete client use case requires resources or prompts, or
when user reports show the four tools are insufficient for real agent
workflows.

## Related Requirements

- rac-agent-context-guide

## Related Designs

- guide-tool-surface

## Related Roadmaps

- v0.10.0-guide-foundation
