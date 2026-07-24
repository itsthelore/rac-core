---
schema_version: 1
id: EVAL-M8R1BJ63YM1E
type: design
tags: [sync, collaboration]
---
# Conflict Resolution UX

## Status

Accepted

## Context

When offline edits merge on reconnect, the merged result can surprise a writer
who did not see the other author's changes. The merge itself is automatic, but
the writer needs to understand what happened.

## User Need

A writer returning online needs to see what changed while they were away and
trust that none of their own edits were lost.

## Design

On reconnect, merged-in remote changes are briefly highlighted in the document
and summarised in a dismissible banner ("3 paragraphs updated by Sam"). No
modal blocks editing; the merge is already applied and the surface is purely
explanatory.

## Constraints

The highlight must not alter document content and must fade without leaving
formatting behind. The summary must be legible to assistive technology.

## Rationale

Because the underlying merge is deterministic and lossless, the UX only has to
explain the result, not ask the writer to resolve anything by hand.

## Related Decisions

- EVAL-STK2ZW0AWS3V
