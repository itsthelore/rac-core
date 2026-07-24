---
schema_version: 1
id: EVAL-KRRRS99DSV9W
type: decision
tags: [auth, session]
---
# Static Session Token Expiry

## Status

Superseded

## Context

The Aurora editor issues a session token when a user signs in. The first
release needed a simple, predictable expiry policy that the gateway could
enforce without coordinating state across services.

## Decision

Session tokens are valid for a fixed one-hour window from issue. When the
window elapses the user is signed out and must authenticate again.

## Consequences

A fixed window is trivial to reason about, but it forces a hard re-login on
every active user each hour, which the editor's long writing sessions made
painful. This policy was replaced once refresh became available.

## Category

Technical
