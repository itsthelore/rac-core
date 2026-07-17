---
schema_version: 1
id: RAC-KTW0M83CGTQV
type: requirement
---
# Requirement: Agent Context Guide (RAC Guide)

## Status

Accepted

## Problem

Coding agents are now active contributors to repositories that store product
knowledge in RAC.

Those agents work without that knowledge:

- Requirements are never loaded into the agent's context.
- Recorded decisions are violated because the agent never reads them.
- Agents re-derive repository understanding by grepping raw files.
- Context files (agent instruction documents) do not scale: they are untyped,
  unreviewed, and carry no relationships.

RAC already provides deterministic repository intelligence through:

- artifact lookup and resolution
- repository search
- relationship analysis
- validation
- portfolio intelligence

These capabilities are CLI-shaped. Agents need them session-shaped: available
as tools the agent can call at the moment a decision or requirement becomes
relevant.

The strategic claim this capability must make provable:

> An agent connected to RAC respects decisions an unconnected agent violates.

## Requirements

- [REQ-001] RAC shall provide an agent context surface called RAC Guide: an MCP server started with `rac mcp`, speaking stdio, read-only, exposing tools only in v1.

- [REQ-002] Guide shall expose exactly four tools — `get_artifact`, `search_artifacts`, `get_related`, `get_summary` — with pinned output contracts, intent-bearing tool descriptions, a per-response character budget, and structured not-found errors.

- [REQ-003] Guide shall consume RAC Core services in-process with zero duplicated intelligence, deterministically (identical repository state and identical input produce identical output), read-only by construction, and ship inside the existing package and PyPI artifact.

- [REQ-004] Guide shall start with zero required flags from a repository root, accept an optional `--root PATH` override, and be installable into Claude Code, Claude Desktop, and Cursor through verified copy-paste configuration blocks, supported by an examples corpus and registry submission on release.

- [REQ-005] The release shall include a reproducible grounding demo: a true-to-life decision artifact, a code task whose naive implementation violates it, a scripted with/without contrast in which the grounded agent cites the correct decision ID in at least 8 of 10 runs, and a screen recording of at most 90 seconds as a release asset.

## Product Goal

Move RAC from:

> A deterministic CLI a human runs.

toward:

> Repository knowledge present in every agent session.

## Product Model

RAC provides multiple surfaces over the same underlying intelligence.

```text
RAC Core
    |
    +-- Explorer
    |     Understand repository state
    |
    +-- Guide
    |     Ground agents in repository knowledge
    |
    +-- Watchkeeper (deferred)
          Understand repository change
```

Explorer answers:

> What exists and what needs attention?

Guide answers:

> What does the agent need to know right now?

Watchkeeper, when built, answers:

> What changed and does it require review?

## User Story

As a team whose repository is modified by coding agents,

when an agent implements work that is constrained by recorded requirements
and decisions,

I want the agent to retrieve and cite that knowledge before acting,

so that recorded decisions are respected instead of silently violated.

## Dependency

Guide consumes existing RAC capabilities:

- Artifact lookup and resolution
- Repository search
- Relationship analysis
- Portfolio intelligence
- Repository indexing
- Stable JSON output contracts

Guide shall not implement independent repository intelligence.

All repository intelligence shall remain within RAC Core.

## Interface

Required:

```bash
rac mcp
```

Optional:

```bash
rac mcp --root PATH
```

Client configuration for Claude Code, Claude Desktop, and Cursor is delivered
as verified copy-paste blocks in user-facing documentation.

## Tool Surface

Guide exposes four read-only tools:

### get_artifact

Retrieve one artifact by its identifier: resolution metadata plus the
artifact's Markdown content.

### search_artifacts

Search artifacts by query text, optionally filtered by artifact type,
returning resolution metadata for each match.

### get_related

Retrieve the relationships of one artifact: the references it declares and
the artifacts that reference it.

### get_summary

Retrieve a repository-level overview: artifact counts, validation state,
relationship health, and attention items.

Tool names, signatures, description text, response shapes, error shapes, and
truncation behavior are pinned by the `guide-tool-surface` design artifact.

## Non-Goals

Guide shall not:

- expose write, edit, or Git operations
- expose MCP resources or MCP prompts in v1
- speak HTTP or SSE transports in v1
- cache repository state between tool calls
- detect conflicts or exercise semantic judgment
- replace Explorer or Watchkeeper
- require hosted infrastructure
- duplicate RAC Core logic

## Architecture Requirements

Guide shall operate as a consumer of RAC capabilities.

Repository intelligence shall remain accessible through RAC Core services and
commands.

Guide shall not become the sole interface to repository intelligence.

Capabilities surfaced through Guide shall remain accessible through RAC
commands and machine-readable outputs, and Guide tool output shall not
diverge from the equivalent CLI JSON output.

## Design Authority

This requirement defines the purpose, capabilities, and intended outcomes of
Guide.

Tool contracts, description text, response budgets, error shapes, and the
grounding demo protocol are delegated to associated design artifacts.

## Acceptance Criteria

A user can:

1. Install RAC.
2. Add one configuration block to their agent client.
3. Ask the agent a question about their repository's product knowledge.
4. Receive an answer that cites artifact identifiers.

without the agent reading raw repository files or the user authoring
artifacts first.

## Success Metrics

Guide succeeds when:

- the grounded agent cites the correct decision ID in at least 8 of 10
  scripted demo runs
- a user on a clean machine reaches a grounded agent answer in under five
  minutes using only the documentation
- Guide tool output matches the equivalent CLI JSON output for the same
  repository state
- zero parsing, resolution, or relationship logic is duplicated between Guide
  and RAC Core

## Risks

- Agent behaviour is stochastic; the demo may fail live. Mitigated by
  engineered tool descriptions, scripted prompts tested across runs, and a
  recording captured in advance.
- Client configuration formats drift. Mitigated by verifying each block
  against current client versions at release.
- A contrived demo scenario reads as a strawman. Mitigated by lifting the
  scenario from a true-to-life decision a real team would record.

## Assumptions

- stdio transport is sufficient for all target clients in v1.
- Core service functions are sufficient for all four tools; any gap is closed
  by extending Core, never by server-side logic.
- A single package keeps the install story one step.

## Related Decisions

- ADR-029
- ADR-030
- ADR-031
- ADR-032
- ADR-033
- ADR-034
- ADR-002
- ADR-007
- ADR-008
- ADR-012
- ADR-015
- ADR-026

## Related Designs

- guide-tool-surface
- guide-grounding-demo

## Related Roadmaps

- v0.10.0-guide-foundation
- v0.10.1-guide-onboarding
- v0.10.2-guide-grounding-demo

## Related Requirements

- rac-product-knowledge-navigator-explorer
- rac-product-intent-ci-watchkeeper

## Future Considerations

Future versions may introduce MCP resources or prompts, additional transports
for hosted use cases, or write workflows — each behind an explicit decision.
Watchkeeper, when built, consumes the same Core services and contracts Guide
consumes.
