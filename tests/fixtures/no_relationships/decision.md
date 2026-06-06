# ADR-031 Search Index Engine

## Status

Accepted

## Category

Architecture

## Context

Search needs a dedicated index to meet latency targets.

## Decision

Adopt an embedded inverted-index engine maintained alongside the primary store.

## Consequences

- Search latency improves substantially.
- The index must be kept in sync on writes.
