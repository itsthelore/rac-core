---
schema_version: 1
id: EVAL-JTDKWHNVD8GG
type: decision
tags: [auth, session]
---
# Refresh Token Rotation

## Status

Accepted

## Context

Fixed one-hour session expiry signed active writers out mid-session. We need a
policy that keeps a writing session alive without weakening revocation.

## Decision

Aurora issues a short-lived access token alongside a long-lived refresh token.
The client silently exchanges the refresh token for a new access token on a
fixed rotation interval, and each exchange rotates the refresh token so a
stolen token is usable only until the next rotation.

## Consequences

Active writers stay signed in across long sessions, and revocation still takes
effect within one rotation interval. The client gains the responsibility of
storing and rotating the refresh token securely.

## Category

Technical

## Supersedes

- EVAL-KRRRS99DSV9W
