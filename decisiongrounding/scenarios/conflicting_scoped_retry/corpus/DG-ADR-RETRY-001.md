---
schema_version: 1
id: DG-ADR-RETRY-001
type: decision
tags: [reliability, background-jobs]
---

# DG-ADR-RETRY-001: Background Jobs Retry With Backoff

## Status

Accepted

## Context

Background and queue workers run asynchronously, so retrying a transient
external failure is safe and improves throughput.

## Decision

Background jobs must retry failed external calls using exponential backoff. This
decision applies to background and queue workers only; it does not govern
synchronous request handlers.

## Consequences

### Positive

- Transient failures in async work self-heal.
