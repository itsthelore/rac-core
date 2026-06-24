# lore-verify

Autonomous QA for [Lore](https://github.com/itsthelore/rac-core). An agent is
given real developer tools — a browser and a terminal — to develop against a
target, then **converts the working session into durable end-to-end tests**,
runs them across targets (dev, production) and operating systems, and emits
replayable trace artifacts you can review without running anything locally.

> **Status: prototype-in-progress.** `lore-verify` is being prototyped in this
> `verify/` subdirectory of `rac-core` (RAC ADR-064 safety contract) and will be
> extracted to `itsthelore/lore-verify` once it ships. This directory is a
> self-contained subproject with its own corpus, packaging, and tests.

## What it is — and isn't

`lore-verify` is a **contract consumer of Lore, not an extension of the engine**
(see `rac/decisions/lv-adr-001-product-identity.md`):

- It learns *what to verify* from the published Lore contract (`rac export
  --graph`, the `lore` MCP read tools) — never RAC engine internals.
- It writes back **only by proposing** `## Verified By` references in a
  human-reviewed pull request. It never writes a corpus directly.
- It owns all runtime and content (driving the browser/terminal, running tests,
  producing traces) — which Lore deliberately does not.

The boundary: **Lore records and reports verification; `lore-verify` produces and
runs the evidence.** The commercial/hosted offering (a VM-fabric runner and
org-scale verification governance) is a *separate brand* that plugs into the
runner interface; it is never required for the local path. See RAC
ADR-083 (`itsthelore/rac-core`) for the full split.

## Architecture

Three modules with three runtime profiles (see
`rac/designs/drive-compile-run-architecture.md`):

| Module | Role | Profile |
|---|---|---|
| **Drive** | AI agent loop with browser + terminal; explores and verifies behaviour | slow, AI-powered, runs once |
| **Compile** | Turns the session into a durable test and asserts fidelity (re-run N times, green and stable) | the product's moat |
| **Run** | Executes compiled tests behind a pluggable runner interface; injects target + OS; emits traces | fast, parallel, runs everywhere |

The agent runs once (Drive); the *compiled* tests run everywhere (Run). Keeping
those runtimes separate is what lets a thorough agent and fast multi-OS tests
coexist.

## This subproject's corpus

`lore-verify` dogfoods Lore on itself. Its decisions, requirements, designs, and
roadmaps live under `rac/` with the repository key `LV`, validated independently:

```bash
rac validate verify/rac/
rac relationships verify/rac/ --validate
```

## Build plan

The full programme is recorded in `rac-core` at
`rac/roadmaps/future/lore-verify-programme.md`; the first milestone is
`rac/roadmaps/v0.1.0-prototype.md` in this subproject.
