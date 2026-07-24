---
schema_version: 1
id: EVAL-FCTMD6C13A4N
type: requirement
tags: [editor, offline]
---
# Offline Editing

## Status

Accepted

## Problem

Writers lose connectivity on trains and planes but expect to keep editing. When
the network drops today the editor goes read-only, which interrupts the writing
they came to Aurora to do.

## Requirements

- [REQ-001] The editor MUST let a user keep editing a already-open document while offline, queueing edits locally.
- [REQ-002] On reconnect the editor MUST merge queued offline edits into the shared document without dropping any edit.
- [REQ-003] The editor MUST show a clear indicator of offline state and of pending unsynced edits.

## Success Metrics

- Zero edits lost across a disconnect/reconnect cycle in the sync test suite.
- Reconnect merge completes within two seconds for a typical document.

## Related Decisions

- EVAL-STK2ZW0AWS3V
