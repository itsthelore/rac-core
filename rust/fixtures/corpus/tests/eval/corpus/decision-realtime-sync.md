---
schema_version: 1
id: EVAL-STK2ZW0AWS3V
type: decision
tags: [sync, collaboration]
---
# CRDT-Based Realtime Sync

## Status

Accepted

## Context

Multiple authors edit the same Aurora document at once. We need concurrent
edits to converge without a central lock and without losing keystrokes when
clients reconnect after going offline.

## Decision

Realtime sync is built on conflict-free replicated data types (CRDTs). Each
client applies edits locally and exchanges operations that merge
deterministically, so every replica converges to the same document state.

## Consequences

Offline edits merge cleanly on reconnect and no edit is silently dropped. The
cost is a richer document representation and the memory the CRDT metadata
carries per document.

## Category

Architecture
