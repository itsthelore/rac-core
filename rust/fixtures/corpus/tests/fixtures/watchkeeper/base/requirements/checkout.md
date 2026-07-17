# Checkout

## Problem

Checkout confirmation is slow and customers abandon payment.

## Requirements

[REQ-001] Payment confirmation must complete within 2 seconds
[REQ-002] User can retry a failed payment once

## Acceptance Criteria

- A successful payment shows confirmation within the budget on 3G

## Success Metrics

- Payment confirmation p95 stays under 2 seconds

## Risks

- Provider latency spikes could break the confirmation budget
