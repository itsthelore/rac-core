---
schema_version: 1
id: RAC-KTQ63DPZ42BG
type: decision
---
# ADR-008 Agent Ready Architecture

## Status

Accepted

## Context

Future versions of RAC may be used by Claude, Codex, Cursor, and other AI systems.

The architecture should avoid coupling business logic to the CLI.

## Decision

All RAC capabilities will be implemented in reusable service layers.

The CLI will be a thin wrapper around those services.

## Alternatives Considered

### CLI-only Architecture

Pros:
- Simpler initially

Cons:
- Difficult to expose as SDK or MCP server

## Consequences

### Positive

- Easy MCP support
- Easy SDK support
- Easier testing

### Negative

- Slightly more abstraction
- Additional project structure
