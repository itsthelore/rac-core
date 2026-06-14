---
schema_version: 1
id: DG-ADR-SEC-001
type: decision
tags: [security, logging]
---

# DG-ADR-SEC-001: Do Not Log Personal Data

## Status

Accepted

## Context

Logs are retained and broadly readable, so personal data in logs is a privacy
risk.

## Decision

Personal data must not be written to application logs. This decision governs
log content only.

## Consequences

### Positive

- Logs are safe to retain and share internally.
