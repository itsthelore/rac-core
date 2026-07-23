---
schema_version: 1
id: RAC-KVW467ZRW4EH
type: roadmap
---
# Lore Slack Bot (Future)

## Status

Planned

Unscheduled — recorded as future intent, not yet on a release. It is gated on the
decision to start a `lore-*` Slack product and must not displace nearer-term work.
The implementation contract (the *how*) already exists: the design
`lore-slack-capture-flow`.

## Context

`lore-capture-surfaces` names the Slack bot (Host C) as the favoured way to reach
a whole team — product managers included — with zero per-user install, capturing
decisions where they are actually made. Unlike the overlay, its architecture is
already fully worked out in `lore-slack-capture-flow`: a message-shortcut/slash
trigger, an assistant-thread interview, ack-in-3s + async + idempotent writes, a
draft pull request through a least-privilege GitHub App, the two-gate approval
model (ADR-077), provenance via `chat.getPermalink`, and the governance posture
for routing thread content to a user-managed gateway (ADR-035). This roadmap
records the *what and why* and the build's acceptance bar — the schedule, not the
design. It is the team-native sibling of `lore-overlay`; both wrap the shared
capture core (`rac-capture-skill`).

## Outcomes

- A team captures a decision from a Slack thread without leaving Slack and with no
  per-user install, and it enters the reviewed corpus only through an independent
  maintainer's pull-request merge (ADR-065, ADR-077).
- Lore reaches the audience the harness skill cannot — non-technical authors who
  live in Slack — proving the team-native host over the shared capture core.

## Initiatives

### Initiative 1 — Capture MVP

A message shortcut ("Save as decision") / slash command → an assistant-thread
interview running the `rac-capture` loop → a draft pull request via the GitHub App
→ the two-gate model. Implements the ack-in-3s + async worker with `event_id`
dedup and an idempotent write keyed on `(channel, ts)`, and stores the
`chat.getPermalink` as provenance. The smallest slice that turns a thread into a
reviewable artifact.

### Initiative 2 — Governance, gateway, and hosting

Route inference through a user-managed OpenAI-compatible gateway (retention/
telemetry off, region-pinned; ADR-035); store metadata/permalink, not transcripts.
Stand up the service (Socket Mode vs a public request URL), OAuth install with
per-workspace token storage, and Slack request-signature verification.

### Initiative 3 — Marketplace / Enterprise-Grid readiness

The disclosure, least-privilege scopes, TLS, and admin-approval posture an app
needs when it exports message content to an external model, so a governed org can
adopt it.

## Constraints

- AI runs in the service behind a user-managed gateway, never in `rac-core`
  (ADR-002, ADR-035, ADR-067); the bot is a thin client over the `rac` contract
  (ADR-063).
- Two gates; the bot's GitHub identity only proposes and never approves/merges,
  and is never on a review-bypass list (ADR-065, ADR-077).
- Capture knowledge, not work (ADR-017): record the durable decision, never
  mirror tickets/owners/sprints. Emit to git; store no transcripts (ADR-024).
- A `lore-*` product in its own repository, not engine code (ADR-068).

## Non-Goals

- Storing raw Slack transcripts (store the permalink + the artifact).
- Giving the bot approval or merge power (it only opens draft PRs).
- Inheriting Slack's first-party privacy guarantees for the external model call —
  the app must provide its own.

## Success Measures

- A teammate turns a Slack thread into a schema-valid artifact (`rac validate`
  exits 0) via the interview, landed as a draft PR promoted only by an independent
  merge, with a working permalink back to the source thread.
- Reprocessing a Slack retry (`event_id` replay) updates in place rather than
  creating a duplicate artifact.
- An Enterprise-Grid admin can approve the app from its disclosed data-flow and
  least-privilege scopes.

## Assumptions

- Slack's assistant/interaction APIs the design relies on stay available (flagged
  fast-moving in `lore-slack-capture-flow`).
- A GitHub App with least-privilege scopes can be installed against the target
  repo from the service.
- The `rac` contract stays stable and additive (ADR-007, ADR-063).

## Risks

- **Fast-moving Slack AI surfaces.** The assistant-thread and streaming APIs change
  often; mitigated by isolating the Slack adapter and re-verifying before build.
- **Governance boundary crossing.** Exporting thread content to an external model
  invites admin scrutiny; mitigated by the gateway, metadata-only storage, and
  disclosure (Initiatives 2–3).
- **Operational surface.** A hosted, multi-tenant service with secrets and OAuth
  tokens is a real attack surface; mitigated by least-privilege scopes and the
  inbound-bot security review parked in `lore-capture-followups`.

## Related Decisions

- ADR-017
- ADR-035
- ADR-065
- ADR-067
- ADR-068
- ADR-077

## Related Designs

- lore-slack-capture-flow

## Related Roadmaps

- rac-capture-skill
