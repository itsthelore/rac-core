# Checkout

## Problem

Checkout confirmation is slow and customers abandon payment.

## Requirements

[REQ-001] Payment confirmation should complete quickly
[REQ-002] User can retry a failed payment once

## Success Metrics

- Payment confirmation p95 stays under 2 seconds

## Risks

- Provider latency spikes could break the confirmation budget
