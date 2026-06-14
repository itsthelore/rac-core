---
schema_version: 1
id: DG-ADR-LOG-001
type: decision
tags: [logging, observability]
---

# DG-ADR-LOG-001: Structured JSON Application Logs

## Status

Accepted

## Context

Logs are consumed by an aggregation pipeline that parses fields. Free-text log
lines break the parser and lose searchability.

## Decision

All application logs must be emitted as structured JSON with a `timestamp`,
`level`, and `message` field. Adding new log statements is permitted and
encouraged; they simply must follow the structured JSON format.

## Consequences

### Positive

- Logs are machine-parseable and searchable.

### Negative

- Slightly more verbose call sites.
