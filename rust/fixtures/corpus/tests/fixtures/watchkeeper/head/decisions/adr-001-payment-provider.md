# ADR-001: Payment Provider

## Status

Accepted

## Category

Architecture

## Context

Checkout and upload flows need a payment provider with webhooks.

## Decision

Adopt a single hosted payment provider for all checkout flows.

## Consequences

- One provider integration to maintain.

## Related Requirements

- checkout
- legacy-upload
