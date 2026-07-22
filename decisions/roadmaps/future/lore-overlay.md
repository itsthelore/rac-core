---
schema_version: 1
id: RAC-KVW466JX9931
type: roadmap
---
# Lore Overlay (Future)

## Status

Planned

Unscheduled — recorded as future intent, not yet on a release. It is gated on the
decision to start a `lore-*` desktop product and must not displace nearer-term
work. The implementation contract (the *how*) lives in the design `lore-overlay`.

## Context

`lore-capture-surfaces` names a desktop overlay (Host B) as one of the favoured
ways to reach a non-technical author "alongside any screen", and
`lore-capture-overlay` (design) works out its architecture: a Tauri v2 app,
macOS-first, that summons a
modal from a global hotkey, runs the `rac-capture` loop behind a bring-your-own
gateway, and opens a draft pull request through the same GitHub-App + two-gate
path as `lore-slack-capture-flow`. This roadmap records the *what and why* and the
build's acceptance bar, kept as intent rather than a scheduled release. It is the
desktop sibling of `lore-slack-bot`; both wrap the shared capture core
(`rac-capture-skill`).

## Outcomes

- A macOS user captures a decision from a global hotkey, mid-task, without leaving
  their current app, learning Markdown, or touching git — and nothing enters the
  reviewed corpus except through an independent maintainer's pull-request merge
  (ADR-065, ADR-077).
- Lore proves a **desktop host** over the shared capture core, so a second
  installable surface exists alongside the harness skill and (eventually) the
  Slack bot.

## Initiatives

### Initiative 1 — macOS MVP

A Tauri v2 menu-bar app: global hotkey → non-activating modal → the `rac-capture`
interview → a draft pull request via the GitHub App → the two-gate model. Includes
the settings surface (gateway endpoint/key/model; target repo + GitHub App;
hotkey). Signed with Developer ID and notarized. This is the smallest end-to-end
slice that captures a real decision.

### Initiative 2 — Windows fast-follow

Bring the same codebase to Windows (tray via `Shell_NotifyIcon`, hotkey via
`RegisterHotKey`, always-on-top via `WS_EX_TOPMOST`), with Authenticode / Azure
Trusted Signing, the SmartScreen-reputation ramp, and a bundled/bootstrapped
WebView2 runtime.

### Initiative 3 — Polish and the optional live viewer

Quality-of-life (capture-and-queue when offline; richer pre-fill), and a decision
on whether the overlay also hosts the repo-watching `rac export` viewer (Thread A
of `lore-frontend-optionality`) or stays capture-only.

## Constraints

- AI runs in the app behind a user-managed gateway, never in `rac-core` (ADR-002,
  ADR-035, ADR-067); the app is a thin client over the `rac` contract (ADR-063).
- Two gates; the app's GitHub identity only proposes and never approves/merges
  (ADR-065, ADR-077).
- A `lore-*` product in its own repository, not engine code (ADR-068); it emits to
  git and stores no content (ADR-024).

## Non-Goals

- Screen-watching / Accessibility-based on-screen capture — out of the MVP; a
  later, permission-gated option at most.
- Linux/Wayland support — deferred (portal-gated, compositor-uneven).
- Bundling or hosting a model — the app calls a user-configured endpoint.

## Success Measures

- A macOS user produces a schema-valid artifact (`rac validate` exits 0) from a
  hotkey-summoned interview, choosing no id and writing no Markdown, landing it as
  a draft PR promoted only by an independent merge.
- The app reuses `lore-slack-capture-flow`'s write/approve path and the
  `rac-capture` core with no `rac-core` change.
- Evidence that authors use a desktop hotkey surface (the signal that would
  schedule this out of `future/`).

## Assumptions

- The `rac` contract the app depends on (`schema`, `new`, `validate`, `resolve`/
  `find`) stays stable and additive (ADR-007, ADR-063).
- A GitHub App with least-privilege scopes can be installed against the target
  repo and authenticated from a desktop app (device flow).
- The summon-a-modal scope is sufficient for capture; on-screen context is not
  needed for the MVP.

## Risks

- **Distribution tax.** Signing/notarization (macOS) and Authenticode +
  SmartScreen reputation + WebView2 (Windows) are real, ongoing costs; mitigated
  by macOS-first and a cloud signing service.
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

## Related Designs

- lore-capture-overlay

## Related Roadmaps

- rac-capture-skill
