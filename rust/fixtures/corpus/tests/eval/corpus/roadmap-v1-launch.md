---
schema_version: 1
id: EVAL-BB7BF4CHZEVN
type: roadmap
tags: [release, launch]
---
# v1 Launch

## Status

Planned

## Context

The v1 launch bundles the capabilities that make Aurora usable for real
collaborative writing: durable storage, realtime collaboration, resilient
sessions, and offline editing.

## Outcomes

- Writers can collaborate on a shared document in realtime and never lose an edit.
- Writers stay signed in across long sessions and can keep working offline.

## Initiatives

- Ship realtime collaboration on the agreed sync foundation.
- Ship resilient sessions so writers are not signed out mid-session.
- Ship offline editing with lossless reconnect merges.

## Success Measures

- A pair of writers can co-edit a document for an hour with zero lost edits.
- A continuous eight-hour session never forces an interactive re-login.

## Related Decisions

- EVAL-STK2ZW0AWS3V
- EVAL-JTDKWHNVD8GG

## Related Requirements

- EVAL-FCTMD6C13A4N
- EVAL-1ZM9RM9559B2
