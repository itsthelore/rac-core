# Lore Capture Overlay (MVP — provisional name)

> **Name is provisional.** "overlay" is a working title; the product name is
> still TBD. The corpus artifacts use `lore-overlay` / `lore-capture-overlay`;
> rename here and in `rac/designs/lore-capture-overlay.md` +
> `rac/roadmaps/future/lore-overlay.md` when the product name is settled.

A small, always-one-keystroke-away desktop app that lets someone capture a
decision or requirement **mid-task**: press a global hotkey, a modal appears over
whatever they're doing, they talk it through, and it becomes a **proposed**
artifact — a draft pull request — without leaving their current app, learning
Markdown, or touching git.

This is **Host B** of `rac/designs/lore-capture-surfaces.md`; the architecture is
`rac/designs/lore-capture-overlay.md` and the build plan is
`rac/roadmaps/future/lore-overlay.md`.

It is a `lore-*` product (ADR-068) developed here as a **staging directory** in
`rac-core`, to be extracted to its own `itsthelore/lore-overlay` repo later — the
same develop-in-repo-then-extract pattern used for the VS Code extension.

## Two surfaces: a verified brain and a scaffolded shell

```
lore-overlay/
  core/   the platform-agnostic capture "brain" — Rust library, FULLY TESTED here
  app/    the Tauri v2 desktop shell — authored, NOT built here (needs macOS)
```

**The skill is the brain; the host is the interface.** `core/` implements the
whole capture flow over three trait seams — the `rac` engine, the model gateway,
and the GitHub writer — so it is exercised offline with fakes and against the real
`rac`. `app/` is the thin desktop shell (global hotkey → modal → invoke the core).

### The two-gate write model (ADR-077)

- **Gate 1 — fidelity.** `CaptureFlow::propose` turns the author's words into a
  proposal they confirm in the modal. No file is written, nothing is pushed.
- **Gate 2 — trust boundary.** `CaptureFlow::publish` writes the artifact,
  validates it with `rac`, and opens a **draft** pull request. An independent
  maintainer's merge is the trust boundary. The `Publisher` trait has **no
  approve/merge method by construction**, and the flow refuses any non-draft PR —
  so a host built on this core cannot self-approve.

### Bring-your-own gateway (ADR-035)

The model call goes through a configurable **OpenAI-compatible** endpoint
(`base_url` + key + model) — a self-hosted LiteLLM proxy, a cloud vendor, or a
local model. No AI runs in the engine (ADR-002/067); the key lives in the OS
secret store, not in any serialized config.

### Rendered body (Gate 1)

The review step shows the drafted body as **rendered CommonMark** by default, with
a one-click **Edit** toggle back to the raw source (the textarea stays the source
of truth for publish). Rendering uses **markdown-it** (`html: false`) and the
output is sanitized with **DOMPurify** before it touches `innerHTML` — artifact
content is untrusted input (ADR-065), so the render path must not become an
injection vector. These are the app's only frontend dependencies; `npm install`
pulls them, and the frontend needs a bundler (e.g. Vite) to resolve the
bare-module imports.

## What is verified vs not

This MVP was developed in a Linux container, which **cannot build, run, sign, or
notarize a macOS app**. So:

| Part | Status | How checked |
| --- | --- | --- |
| `core/` logic (flow, fill-keeping-frontmatter, id parse, draft-PR guard) | **Verified** | `cargo test` — 4 hermetic tests pass |
| `core/` ↔ real `rac` shell | **Verified** | `LORE_TEST_RAC=… cargo test` exercises `rac schema` |
| `core/` network clients (gateway + GitHub) | **Compiles** | `cargo check --features net` |
| `app/` Tauri desktop shell (hotkey, panel, build, sign) | **Not built / not run** | requires macOS; authored as a scaffold only |

## Build & run

### Core (works anywhere with Rust)

```bash
cd lore-overlay/core
cargo test                     # hermetic suite
cargo check --features net     # compile the gateway + GitHub clients
# exercise the real rac shell:
LORE_TEST_RAC="rac" cargo test real_rac_client_reads_schema_when_configured
```

### Desktop app (macOS first; needs a Mac)

Prerequisites: Rust, Node + npm, the Tauri CLI (`cargo install tauri-cli`), and
Xcode command-line tools.

```bash
cd lore-overlay/app
npm install
cargo tauri dev                # run the dev build
cargo tauri build              # produce a .app / .dmg
```

Signing & notarization (required for distribution outside the App Store): sign
with a **Developer ID** certificate and notarize with `notarytool`. Windows
(fast-follow) uses **Authenticode** — practically **Azure Trusted Signing** — plus
the SmartScreen-reputation ramp and a bundled/bootstrapped **WebView2** runtime.

## Configuration

`core::Config` holds everything the app needs:

- `gateway` — `base_url`, `model`, and an `api_key` (read from the OS secret
  store at runtime; never serialized).
- `repo` — `owner`, `repo`, `base_branch` (default `main`).
- `hotkey` — Tauri accelerator (default `CmdOrCtrl+Shift+L`).
- `rac_command` — how to invoke the engine (bundled, on `PATH`, or a wrapper).

## Open questions (from the design)

- **Desktop GitHub-App auth** — the OAuth **device flow** to install the App and
  obtain an installation token, and where that token is cached on-device. The
  core takes a bearer token; acquiring it is the shell's job.
- **Embed vs shell `rac`** — bundle the CLI with the app, require it on `PATH`, or
  consume the TypeScript SDK once published. Thin-client either way (ADR-063).
- **Offline** — capture-and-queue when there's no network; open the draft PR on
  reconnect.

## Corpus pointers

- Design (the *how*): `rac/designs/lore-capture-overlay.md`
- Build plan: `rac/roadmaps/future/lore-overlay.md`
- Trust model: `rac/decisions/adr-077-two-gate-capture-write-model.md`
- Shared pipeline it reuses: `rac/designs/lore-slack-capture-flow.md`
