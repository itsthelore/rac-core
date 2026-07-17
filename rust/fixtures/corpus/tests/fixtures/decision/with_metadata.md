# ADR-007 API Versioning

## Status

Accepted

## Category

Architecture

## Supersedes

  ADR-003

## Context

Our public APIs need a versioning strategy as they evolve.

## Decision

Use URL-based versioning (`/v1`, `/v2`).

## Consequences

- The version is explicit in every request.
- Clients migrate on their own schedule.
