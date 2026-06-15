---
schema_version: 1
id: DG-ADR-RETRY-002
type: decision
tags: [reliability, request-handlers]
---

# DG-ADR-RETRY-002: Request Handlers Fail Fast

## Status

Accepted

## Context

Synchronous request handlers hold a client connection open. Retrying a failed
external call inside a handler ties up the connection and amplifies load during
an outage.

## Decision

Request handlers must not retry failed external calls. A handler must fail fast
and return an error to the caller. This decision applies to synchronous request
handlers only.

## Consequences

### Positive

- Handlers shed load instead of amplifying it during downstream outages.

### Negative

- The caller, not the handler, owns any retry policy.
