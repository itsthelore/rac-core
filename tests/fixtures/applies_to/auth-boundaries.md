---
schema_version: 1
id: RAC-F1XTVREAVTH0
type: decision
---
# Auth module boundaries

## Context

Golden fixture: a live decision scoped to the auth module.

## Decision

Auth flows live under src/auth/ and nowhere else.

## Consequences

Auth changes are reviewable in one place.

## Status

Accepted

## Applies To

- src/auth/
- the login surface
