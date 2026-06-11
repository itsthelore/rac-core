---
schema_version: 1
id: RAC-KTW0M8104880
type: decision
---
# ADR-029: Guide Delivery Surface

## Status

Accepted

## Category

Architecture

## Context

The Agent Context Guide requirement defines an MCP server that serves RAC
repository knowledge to coding agents.

Two delivery questions must be settled before implementation:

1. How does Guide ship — inside the existing `requirements-as-code` package,
   or as a separate distribution artifact?
2. How do clients connect — stdio, HTTP/SSE, or both?

The adoption constraint dominates both questions. An MCP server nobody can
configure in under five minutes will not be adopted. Every additional install
step, version pairing, or transport option multiplies the configuration
surface that must be documented, verified, and kept working.

The target clients — Claude Code, Claude Desktop, and Cursor — all spawn
stdio MCP servers from a local command. None of them requires HTTP for a
local repository server, and RAC has an explicit non-goal of hosted
infrastructure.

The Explorer surface decision (ADR-028) set the precedent: a new consumer
surface ships inside the existing package, launched by a `rac` subcommand,
and its delivery mechanics are recorded as one decision.

## Decision

RAC Guide ships as the `rac mcp` subcommand inside the existing
`requirements-as-code` package and PyPI artifact.

- Transport is stdio only in v1. No HTTP, no SSE.
- The server is built on FastMCP from the official MCP Python SDK.
- The MCP SDK is a standard dependency, not an optional extra: a plain
  `pip install requirements-as-code` yields a working server, so one
  configuration block works without install-time variants.
- `rac mcp` starts the server with zero required flags from a repository
  root; an optional `--root PATH` overrides the repository location.
- There is no separate repository, no separate PyPI package, and no separate
  versioning: one install step, one version, one release pipeline.

## Consequences

### Positive

- One configuration block per client, with no extras or version pairing to
  document.
- Guide releases ride the existing PyPI publishing pipeline unchanged.
- The server and the Core it imports are always the same version.
- stdio matches what every target client spawns natively.

### Negative

- The base install gains the MCP SDK dependency even for users who never run
  `rac mcp`.
- Hosted or remote use cases are not served until a transport decision
  supersedes this one.
- The package release cadence couples server fixes to CLI releases.

### Risks

- Dependency weight complaints from CLI-only users. Mitigation: the SDK is
  light at time of decision; revisit the extra split only if a real user
  reports it — do not pre-optimize.
- Client configuration formats drift. Mitigation: configuration blocks are
  verified against current client versions at each release.

## Alternatives Considered

### Separate `rac-mcp` package

A dedicated distribution artifact for the server.

#### Advantages

- CLI-only installs stay dependency-minimal.
- The server could version independently.

#### Disadvantages

- Two install steps and a version pairing matrix.
- A second release pipeline for no v1 benefit.
- Risk of version skew between server and Core.

### MCP SDK as an optional extra

`pip install 'requirements-as-code[mcp]'`.

#### Advantages

- Base install unchanged.

#### Disadvantages

- The most common failure mode becomes "configured the client, forgot the
  extra" — a five-minute setup turns into a debugging session.
- Documentation forks into with-extra and without-extra variants.

### HTTP/SSE transport

Serve over HTTP for remote or hosted clients.

#### Advantages

- Supports hosted and multi-client scenarios.

#### Disadvantages

- No target client requires it for a local repository server.
- Adds ports, lifecycles, and security surface to document.
- Contradicts the hosted-infrastructure non-goal.

The in-package stdio subcommand is selected.

## Relationship to Other Decisions

- ADR-005 (CLI-first delivery): the server is reached through the existing
  CLI entry point, not a new binary.
- ADR-012 (open core strategy): Guide is core capability and ships in the
  open package.
- ADR-028 (Explorer surface): establishes the pattern of recording a
  consumer surface's delivery mechanics as one decision; its future
  evolution notes already anticipated MCP-based interfaces.
- ADR-030 defines what the server exposes; this decision defines how it
  ships and connects.

## Success Measures

- A user on a clean machine goes from nothing to a connected client in under
  five minutes using only the documentation.
- No issue reports trace to install-step or version-pairing confusion.
- The release pipeline required no changes to ship Guide.

## Review Date

Review before adding any second transport or any second distribution
artifact, or if dependency weight draws real user complaints.

## Related Requirements

- rac-agent-context-guide

## Related Roadmaps

- v0.10.0-guide-foundation
- v0.10.1-guide-onboarding
