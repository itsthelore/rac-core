# ADR-003: Détente — café ünïcode strategy

## Context

Raw HTML like <script>alert("x")</script> and a comment <!-- hidden -->
exercise the portal payload escapes.

## Decision

Escape </ and <!-- sequences before injecting the payload.

## Consequences

The embedded JSON parses unchanged inside the shell.

## Status

Accepted
