---
schema_version: 1
id: DG-ADR-RL-001
type: decision
tags: [reliability]
---

# DG-ADR-RL-001: Public Endpoints Are Rate Limited

## Status

Accepted

## Context

Unbounded request rates have caused outages.

## Decision

Public endpoints must enforce a request rate limit. This decision governs
request rate limiting only.

## Consequences

### Positive

- Endpoints degrade gracefully under load.
