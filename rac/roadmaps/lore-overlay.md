---
schema_version: 1
id: RAC-KVW466JX9931
type: roadmap
---
# Lore Overlay

## Status

Planned

Graduated out of `future/`: the gate this item was recorded behind — the
decision to start a desktop product — is ratified as ADR-100 (Tauri v2,
cross-platform from the outset, admin-provisioned deployment, own
`rac-overlay` repository). It must not displace scheduled engine work. The
implementation contract (the *how*) lives in the design `lore-capture-overlay`.
Execution is tracked in GitHub (ADR-093): the epic in `## Related Tickets`
carries ordering and task state.

## Context

`lore-capture-surfaces` names a desktop overlay (Host B) as one of the favoured
ways to reach a non-technical author "alongside any screen", and
`lore-capture-overlay` (design) works out its architecture: a Tauri v2 app
that summons a modal from a global hotkey, runs the `rac-capture` loop behind
an admin-provisioned gateway, and opens a draft pull request through the same
GitHub-App + two-gate path as `lore-slack-capture-flow`. ADR-100 ratified the
product and reset the platform posture from macOS-first to cross-platform:
macOS and Windows are both first-class targets of the initial release cycle.
This roadmap records the *what and why* and the build's acceptance bar. It is the
desktop sibling of `lore-slack-bot`; both wrap the shared capture core
(`rac-capture-skill`).

## Outcomes

- An author on macOS or Windows captures a decision from a global hotkey, mid-task, without leaving
  their current app, learning Markdown, or touching git — and nothing enters the
  reviewed corpus except through an independent maintainer's pull-request merge
  (ADR-065, ADR-077).
- Lore proves a **desktop host** over the shared capture core, so a second
  installable surface exists alongside the harness skill and (eventually) the
  Slack bot.

## Initiatives

### Initiative 1 — Cross-platform MVP

A Tauri v2 tray app on macOS and Windows (ADR-100: both first-class in the
initial release cycle): global hotkey → non-activating modal → the
`rac-capture` interview → a draft pull request via the GitHub App → the
two-gate model. Includes the settings surface (gateway endpoint/key/model;
target repo + GitHub App; hotkey) and both distribution pipelines: Developer
ID signing + notarization on macOS; Authenticode / Azure Trusted Signing, the
SmartScreen-reputation ramp, and a bundled/bootstrapped WebView2 runtime on
Windows (tray via `Shell_NotifyIcon`, hotkey via `RegisterHotKey`,
always-on-top via `WS_EX_TOPMOST`). This is the smallest end-to-end slice
that captures a real decision on either platform.

### Initiative 2 — Extraction and admin provisioning

Extract the staging spike (`lore-overlay/` in rac-core, PR #202) into the
product's own `rac-overlay` repository with history preserved (ADR-092,
ADR-100), and build the admin-provisioned setup path: an administrator
configures the model gateway, the GitHub App identity, and the target
repository once (composing with the ADR-088 profile scaffold), so the
author-facing surface is only hotkey → interview → fidelity confirmation.
The provisioning documentation is a first-class deliverable of this
initiative, not an afterthought.

### Initiative 3 — Polish and the optional live viewer

Quality-of-life (capture-and-queue when offline; richer pre-fill), and a decision
on whether the overlay also hosts the repo-watching `rac export` viewer (Thread A
of `lore-frontend-optionality`) or stays capture-only.

## Constraints

- AI runs in the app behind a user-managed gateway, never in `rac-core` (ADR-002,
  ADR-035, ADR-067); the app is a thin client over the `rac` contract (ADR-063).
- Two gates; the app's GitHub identity only proposes and never approves/merges
  (ADR-065, ADR-077).
- A product in its own repository — `rac-overlay` per ADR-092/ADR-100, Lore
  brand at org/marketplace level — not engine code (ADR-068); it emits to
  git and stores no content (ADR-024).

## Non-Goals

- Screen-watching / Accessibility-based on-screen capture — out of the MVP; a
  later, permission-gated option at most.
- Linux/Wayland support — deferred (portal-gated, compositor-uneven).
- Bundling or hosting a model — the app calls a user-configured endpoint.

## Success Measures

- An author on macOS or Windows produces a schema-valid artifact
  (`rac validate` exits 0) from a hotkey-summoned interview, choosing no id and
  writing no Markdown, landing it as a draft PR promoted only by an independent
  merge.
- The app reuses `lore-slack-capture-flow`'s write/approve path and the
  `rac-capture` core with no `rac-core` change.
- An admin completes the one-time provisioning (gateway, GitHub App, target
  repo) from the documentation alone, after which a non-technical author
  never sees a configuration surface.
- Evidence that authors use a desktop hotkey surface — corpus lift from
  authors who are not maintainers is the adoption signal.

## Assumptions

- The `rac` contract the app depends on (`schema`, `new`, `validate`, `resolve`/
  `find`) stays stable and additive (ADR-007, ADR-063).
- A GitHub App with least-privilege scopes can be installed against the target
  repo and authenticated from a desktop app (device flow).
- The summon-a-modal scope is sufficient for capture; on-screen context is not
  needed for the MVP.

## Risks

- **Distribution tax.** Signing/notarization (macOS) and Authenticode +
  SmartScreen reputation + WebView2 (Windows) are real, ongoing costs — and
  ADR-100 accepts both pipelines in the first cycle; mitigated by a cloud
  signing service and by treating distribution as Initiative 1 scope, not a
  follow-up surprise.
- **Desktop GitHub-App auth.** The device-flow install and on-device token caching
  are the least-charted part; mitigated by treating it as Initiative 1's spike.
- **Scope creep into screen-watching.** The temptation to read on-screen context;
  mitigated by the summon-a-modal Non-Goal.

## Related Decisions

- ADR-035
- ADR-063
- ADR-065
- ADR-067
- ADR-068
- ADR-077
- ADR-100

## Related Designs

- lore-capture-overlay

## Related Roadmaps

- rac-capture-skill

## Related Tickets

- itsthelore/rac-core#321
