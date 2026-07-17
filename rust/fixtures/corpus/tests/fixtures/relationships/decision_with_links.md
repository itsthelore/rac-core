# ADR-020 Event Bus

## Status

Accepted

## Category

Architecture

## Context

Services need decoupled communication as the platform grows.

## Decision

Adopt an internal event bus for service-to-service messaging.

## Consequences

- Services decouple via published events.
- Debugging spans more hops.

## Supersedes

ADR-011

## Related Requirements

- REQ-014

## Related Roadmaps

- ROADMAP-PLATFORM

## Related Designs

- DESIGN-EVENT-CONSOLE
