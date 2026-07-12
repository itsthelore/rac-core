# ADR-002: Widget Storage Engine v2

## ID

FIX-CHAIN-002

## Status

Deprecated

## Context

Flat files proved too slow for widget storage at scale.

## Decision

Use an embedded key-value store for widgets.

## Consequences

Faster widget lookups, more moving parts.

## Supersedes

FIX-CHAIN-001
