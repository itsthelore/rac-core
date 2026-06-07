# ADR-003 Structured Outputs First

## Status

Accepted

## Context

RAC commands need to be consumable by scripts, SDKs, and future integrations — not just humans.

## Decision

Every command returns typed result models.

## Consequences

### Positive

- JSON output becomes trivial
- SDK usage becomes trivial
- MCP integration becomes trivial
- CI integration becomes trivial
