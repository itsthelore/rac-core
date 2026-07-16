---
schema_version: 1
id: FIX-0DEC1CACHE00
type: decision
tags:
  - cache
  - storage
---
# ADR-1: Cache Policy for Widget Sync

## Context

Widget sync latency grows with corpus size; a disposable cache bounds it.

## Decision

Adopt a content-addressed widget cache with byte-neutral reads.

## Consequences

Deleting the cache costs latency only, never correctness.

## Status

Accepted

## Applies To

- src/widgets/**
- tools/sync.py

## Related Requirements

- FIX-IDX-REQ1
