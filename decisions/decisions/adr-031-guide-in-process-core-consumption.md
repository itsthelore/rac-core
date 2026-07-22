---
schema_version: 1
id: RAC-KTW0M81B0GBB
type: decision
---
# ADR-031: Guide In-Process Core Consumption

## Status

Accepted

## Category

Architecture

## Context

RAC's architecture rests on one rule: RAC Core owns parsing, resolution,
relationships, and intelligence; consumers consume (ADR-015). Explorer holds
that line through an adapter layer that invokes services and owns no
repository intelligence.

A hastily built MCP server is the first place that rule would break:
re-implementing ID resolution "just for now", parsing Markdown in the server
layer, or computing relationships locally. Any divergence creates two sources
of truth and silently corrupts every future consumer.

There are two honest ways for the server to reach Core:

1. Import service functions in-process.
2. Shell out to the CLI and parse its JSON output.

The server must also be read-only. The grounding use case never writes, and a
server that cannot write is categorically safer to recommend than one that
promises not to.

## Decision

Guide imports RAC Core in-process.

- Tool implementations call `rac.services` functions directly — resolution,
  search, relationships, portfolio — and serialize through the same
  `to_dict` shapes the CLI's JSON output uses.
- The server layer re-implements no parsing, resolution, relationship
  extraction, validation, or scoring. Any capability Core does not expose is
  added to Core first and consumed, never implemented server-side.
- The server layer may filter and shape service results for presentation —
  the same boundary Explorer's adapter holds — but owns no intelligence.
- Guide is read-only by construction: the server imports only pure read
  services. No file creation, modification, deletion, or Git operation is
  importable from the server layer, enforced by an isolation test rather
  than by convention.
- Tool output contracts are pinned by tests, matching the project's golden
  practice for CLI output.

## Consequences

### Positive

- Zero duplicated logic between server and Core.
- No subprocess latency or JSON re-parsing per tool call.
- Tool output cannot drift from CLI JSON output: both serialize the same
  objects.
- Read-only is a structural property, verifiable by a test, not a promise.

### Negative

- The server couples to Core internals at the Python API level; Core
  refactors can break the server at import time.
- In-process faults in Core surface inside the server process.

### Risks

- The coupling becomes painful if the server is ever split into its own
  package. Acceptable: same package, same release cadence (ADR-029); this
  decision is the one to revisit if a split ever happens.
- Presentation-level filtering in the server quietly grows into
  intelligence. Mitigation: the isolation battery and code review hold the
  same line Explorer's adapter tests hold.

## Alternatives Considered

### CLI subprocess with JSON parsing

Spawn `rac ... --json` per tool call and parse stdout.

#### Advantages

- Total isolation from Core internals; only the public CLI contract is
  consumed.

#### Disadvantages

- Process spawn latency on every tool call.
- A parsing layer and error-channel mapping for no v1 benefit.
- Version skew becomes possible if the binary on PATH differs from the
  installed package.

### Separate service daemon

A long-lived RAC process the MCP server queries.

#### Advantages

- One loaded corpus shared across consumers.

#### Disadvantages

- A daemon lifecycle to manage, contradicting the stateless model
  (ADR-032) and the hosted-infrastructure non-goal.

In-process import is selected.

## Relationship to Other Decisions

- ADR-015 (Explorer as consumer): Guide is to agents what Explorer is to
  humans — same consumer boundary, same prohibition on owned intelligence.
- ADR-007 (JSON contract stability): the `to_dict` shapes the tools
  serialize are the same stable contracts the CLI emits; tool responses
  inherit their stability rules.
- ADR-008 (agent-ready architecture): the service layer this decision
  consumes exists because that decision kept logic out of the CLI.
- ADR-027 (CI test topology): the isolation battery joins the existing
  battery structure.

## Success Measures

- Code review finds zero duplicated parsing or resolution logic in the
  server layer.
- The dogfood corpus served over MCP matches the same content retrieved via
  CLI JSON output for equivalent queries.
- The isolation battery fails if the server layer imports a write-capable
  API or if Core imports the server.

## Review Date

Review if Guide is ever split into a separate package or process, or if a
Core refactor breaks the server twice in one release series.

## Related Requirements

- rac-agent-context-guide

## Related Roadmaps

- v0.10.0-guide-foundation
