---
schema_version: 1
id: EVAL-1ZM9RM9559B2
type: requirement
tags: [auth, session]
---
# Session Authentication

## Status

Accepted

## Problem

Aurora users need to stay signed in across long writing sessions without
re-entering credentials, while the team needs to be able to revoke a
compromised session quickly.

## Requirements

- [REQ-001] A signed-in session MUST persist across an extended writing session without an interactive re-login.
- [REQ-002] The system MUST be able to revoke an active session within one rotation interval.
- [REQ-003] Session credentials MUST be stored on the client in a way that a stolen credential is short-lived.

## Success Metrics

- No interactive re-login during a continuous eight-hour writing session.
- A revoked session stops working within one rotation interval in tests.

## Related Decisions

- EVAL-JTDKWHNVD8GG
