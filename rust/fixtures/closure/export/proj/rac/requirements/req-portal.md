---
schema_version: 1
id: RAC-AAAA2222BBBB
type: requirement
tags: [portal, export]
---
# Requirement: Portal Export

## Problem

Users cannot view the corpus offline, and bodies carrying raw HTML such as
<script>alert("portal")</script> or a comment <!-- keep hidden --> must
survive export unchanged.

## Requirements

- [REQ-001] The portal MUST export a standalone HTML file.

## Success Metrics

Exported file opens offline.

## Related Decisions

- ADR-001
