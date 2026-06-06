# Search Latency

## Problem

Search results take too long to return for large workspaces.

## Requirements

- [REQ-001] User receives search results within 500ms for workspaces under 10k items.

## Success Metrics

- 95th-percentile search latency stays under 500ms.

## Risks

- Index rebuilds may temporarily degrade latency.
