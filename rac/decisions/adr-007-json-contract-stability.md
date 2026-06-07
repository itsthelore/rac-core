# ADR-007 JSON Contract Stability

## Status

Accepted

## Context

RAC's JSON output is consumed by scripts and will be consumed by future MCP integrations.

## Decision

JSON outputs are treated as public APIs. Field names (for example `features`) will not change to alternatives (for example `feature_count`) without explicit versioning.

## Consequences

### Positive

- Stable contract for scripts and MCP integrations

### Negative

- Schema changes require a versioning strategy
