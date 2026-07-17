---
schema_version: 1
id: RAC-KVW465584DP3
type: design
---
# Lore Capture Overlay

## Status

Proposed

Exploratory — records the architecture for a possible build so the reasoning
lives in the corpus, not a tool's scratch space (ADR-047). It is not an accepted
build; the unscheduled umbrella is the future roadmap `lore-overlay`. It deepens
**Host B** of `lore-capture-surfaces` into a worked *how*, reusing the write and
approval pipeline already designed in `lore-slack-capture-flow`.

## Context

`lore-capture-surfaces` named the desktop overlay (Host B) as one of the favoured
ways to reach an author "alongside any screen", but sketched it in a paragraph.
This design works it out. The job is narrow: a person presses a global hotkey, a
small modal appears over whatever they are doing, they talk a decision through,
and it becomes a proposed artifact — without the author leaving their current app,
learning Markdown, or touching git.

The overlay is a `lore-*` product (ADR-068) that will live in its own repository;
it consumes Lore's published contract rather than reimplementing the engine
(ADR-063), and the language model that runs the interview lives in the app, never
in `rac-core` (ADR-002, ADR-067). Its write-and-approve path is **not new** — it
is the same one `lore-slack-capture-flow` already worked out, so this design
focuses on the desktop-specific shell and points at that pipeline for the rest.

## User Need

A macOS user (a PM, an engineer, anyone) has just decided something and wants it
recorded *now*, mid-task, without context-switching into an IDE or a browser.
They need a capture surface that is always one keystroke away, fast to dismiss,
and that never lands anything in the team's record without review.

## Design

### Shell — summon a modal, do not watch the screen

The overlay is built on **Tauri v2** as a single codebase, **macOS-first** with
Windows a fast-follow and Linux/Wayland deferred (per `lore-capture-surfaces`:
Wayland breaks global hotkeys, always-on-top, and tray). A global hotkey summons a
**non-activating floating panel** (macOS `NSPanel`; Windows `RegisterHotKey` +
`WS_EX_TOPMOST`) from a tray/menu-bar item. The decisive scoping choice from the
capture design holds: the overlay **summons a modal, it does not watch the
screen** — a plain hotkey-plus-panel needs none of the macOS TCC permissions
(Accessibility, Screen Recording) that reading on-screen context would require,
and so carries none of that privacy liability. Reading the active document or
clipboard is a later, explicitly permission-gated enhancement, never the MVP.

### Brain — the `rac-capture` loop, model in the app

Inside the modal the app runs the **`rac-capture`** loop (the skill is the brain;
the host is the interface): capture raw intent first, ask two-to-four pre-filled
questions, draft against the real schema, let the author ratify, and validate. The
model call goes through a **bring-your-own-gateway** seam — a configurable
OpenAI-compatible `base_url` + key + model, sourced from an OS secret store, with
**no prompt-content telemetry** (ADR-035). The app reaches the engine as a thin
client (ADR-063): it shells to a bundled/located `rac` (`rac schema`, `rac new`,
`rac validate`, `rac resolve`/`rac find`) rather than reimplementing
classification or validation.

### Write and approve — reuse the Slack pipeline's two gates

The overlay writes exactly as `lore-slack-capture-flow` specifies, because the
desktop origin changes nothing downstream. It opens a **draft pull request** via a
GitHub App (least privilege: `contents:write` + `pull_requests:write` +
`metadata:read`; branch → file → `draft: true`), credits the human author, and the
app's GitHub identity holds **no approval or merge power**. The **two-gate write
model (ADR-077)** governs: the author's in-app confirmation is *fidelity*, not a
trust boundary; an **independent** maintainer's PR merge is the trust boundary
(ADR-065). The app's own confirmation never lands anything in the trusted corpus.

### Settings

A small settings surface holds the three things the app needs: the **gateway**
(endpoint, key, model), the **target repository + GitHub App** install, and the
**global hotkey**. Nothing else is stored; the app is not a content store
(ADR-024) — it emits artifacts to git and keeps no canonical copy.

### Distribution

macOS: Developer ID signing + notarization. Windows (fast-follow): Authenticode —
practically a cloud signing service such as Azure Trusted Signing — plus the
SmartScreen-reputation ramp and a bundled/bootstrapped WebView2 runtime (Tauri
renders in the OS webview).

## Constraints

- **No AI in the engine (ADR-002, ADR-067); credentials are user-managed
  (ADR-035).** The interview model runs in the app behind a configurable gateway.
- **Thin client over the contract (ADR-063).** The app drives the `rac` CLI; it
  reimplements no engine behaviour.
- **Two gates; the writer only proposes (ADR-065, ADR-077).** In-app confirm is
  fidelity; an independent PR merge is the trust boundary; the app's GitHub
  identity never approves or merges.
- **Not a content store (ADR-024).** Emit to git; store only configuration.
- **A `lore-*` product in its own repo (ADR-068).** Not engine code in `rac-core`.
- **Summon-a-modal, not watch-the-screen.** No Accessibility/Screen-Recording
  permissions in the MVP; on-screen context is a later, permission-gated option.

## Rationale

Tauri v2 over native AppKit keeps Windows a cheap fast-follow on one codebase
without stranding the favoured B+C pair (Slack already covers Windows users), for
a modest polish cost versus native. Summon-a-modal is the highest-leverage scoping
call: it delivers the "alongside any screen" feel while sidestepping the entire
macOS permission gauntlet and its standing privacy liability. Reusing the Slack
pipeline's GitHub-App + two-gate write path means the overlay is genuinely a
*shell* over shared machinery — the capture core, the gateway seam, and the
approval model are identical, so the net-new surface is small and the trust
properties are inherited rather than re-argued.

## Alternatives

- **Native Swift/AppKit — rejected.** Locks the surface to macOS; Tauri keeps
  Windows a cheap fast-follow for a modest polish cost.
- **Electron — rejected.** Heavier than Tauri for the same OS-webview UI, with no
  offsetting benefit for a small capture modal.
- **Watch-the-screen / Accessibility capture (Cluely-shaped) — rejected for the
  MVP.** Buys context the capture job does not need at the price of the full TCC
  permission surface and a standing privacy liability; deferred as a
  permission-gated option.
- **Reimplement the engine in the app — rejected.** Violates thin-client (ADR-063);
  the app shells to `rac` instead.

## Accessibility

- **Keyboard-first by construction.** Summoned by a hotkey; the modal takes
  keyboard focus on open and is fully operable and dismissible from the keyboard.
- **Provenance legibility.** A captured draft is clearly marked *proposed* until
  an independent maintainer merges it; the app never presents its own confirmation
  as ratification.
- **Plain-language interview.** Essential, pre-filled questions only; no schema
  jargon or empty required fields shown to the author.

## Style Guidance

- `lore-*` brand (ADR-068); the app is a Lore product, the engine stays `rac-*`.
- Vocabulary stays honest: the app *captures* and *proposes*; the author
  *confirms* (fidelity); an independent maintainer *merges* (trust boundary).
- Flag the fast-moving externals (macOS permission cadence, Windows cloud-signing,
  WebView2) rather than asserting frozen behaviour.

## Open Questions

- **Engine access**: bundle the `rac` CLI with the app, require it on PATH, or
  consume the published TypeScript SDK once it ships? (Thin-client either way.)
- **GitHub App auth for a desktop app**: the OAuth **device flow** for install /
  token, and where the installation token is cached on-device.
- **Offline behaviour**: capture-and-queue when there is no network, draft PR on
  reconnect.
- **Live-viewer tie-in**: should the overlay also host the repo-watching
  `rac export` viewer (Thread A of `lore-frontend-optionality`), or stay
  capture-only?

## Related Decisions

- ADR-002
- ADR-024
- ADR-035
- ADR-063
- ADR-065
- ADR-067
- ADR-068
- ADR-077

## Related Roadmaps

- lore-overlay
- rac-capture-skill
