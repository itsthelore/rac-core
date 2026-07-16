---
schema_version: 1
id: FIX-0REQ1SYNC000
type: requirement
tags:
  - sync
  - cache
---
# Widget Sync Quota

## Status

Accepted

## Problem

Cache pressure grows with widget count, and unbounded sync starves tenants.

## Requirements

- [REQ-001] Each tenant can sync at most 500 widgets per cache window.
- [REQ-002] The cache window resets hourly.

## Related Decisions

- FIX-IDX-DEC1
