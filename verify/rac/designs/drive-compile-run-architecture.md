---
schema_version: 1
id: LV-KVW1HXB07YYG
type: design
---
# Drive / Compile / Run Architecture

## Status

Proposed

Exploratory — the internal shape of `lore-verify`'s product surface, the *how* for
the `faithful-session-to-test` requirement and LV-ADR-001 / LV-ADR-002.

## Context

`lore-verify` must do three different things with three different runtime
profiles: explore a product with an AI agent (slow, non-deterministic), turn that
session into a durable test (the fidelity-critical translation), and run the
resulting tests fast across many environments (deterministic, parallel). Conflating
them is the usual failure mode — the agent ends up "the test," which is flaky and
unreproducible. This design separates them into three modules.

## User Need

- A **developer** wants to point an agent at their app, let it work, and get back
  committed tests that actually re-verify the behaviour.
- A **reviewer** wants to read the test and a replayable trace in the PR and trust
  it, without running anything locally.
- The **consuming repo** wants those tests to run unchanged against dev, prod, and
  multiple operating systems.

## Design

### Drive

The AI agent loop with real developer tools: a CDP-driven browser and a sandboxed
terminal. Slow, exploratory, AI-powered; BYO credentials, local models supported
(LV-ADR-001). Drive runs **once** to discover and verify behaviour; it is not what
runs in CI.

### Compile

The session-to-test translator. It emits a durable Playwright test carrying
intent-level assertions (not raw event replay) and asserts fidelity by re-running
the emitted test headless N times, accepting it only if green and stable
(`faithful-session-to-test`). This module is the product's moat.

### Run

Executes a compiled test behind the **runner interface** (LV-ADR-002):
target (`baseURL` + auth) and OS/browser are injected, never compiled in. The
local runner ships open; a hosted VM-fabric runner is a drop-in backend. Run is
fast and parallel, and emits the replayable trace artifact.

### The seam to Lore

Drive's worklist comes from `rac export --graph` / the `lore` MCP (which
capabilities lack a `verified-by` edge). After Run confirms a faithful test,
`lore-verify` opens a PR proposing `## Verified By` lines; a human merges them,
closing the matching `unverified-capability` gap in `rac coverage` (LV-ADR-001,
RAC ADR-065).

## Constraints

- The agent runs once (Drive); compiled tests run everywhere (Run) — the two
  runtimes are never merged.
- No coupling to RAC internals; only the published contract (LV-ADR-001, RAC
  ADR-063).
- Compiled tests are target- and OS-agnostic via injection (LV-ADR-002).
- Write-back to Lore is proposal-only, via human-reviewed PR (RAC ADR-065).

## Rationale

Separating Drive from Run is what lets a thorough, slow agent coexist with fast,
multi-OS test execution, and putting the fidelity gate in Compile is what makes the
emitted artifact trustworthy rather than a recording of one lucky run. Routing the
runner through an interface keeps the open/hosted split honest from day one.

## Alternatives

- **Replay the agent's raw actions as the test.** Rejected: brittle and
  assertion-poor; `faithful-session-to-test` REQ-001 requires intent-level
  assertions.
- **Run the agent in CI as the test.** Rejected: non-deterministic and slow; Run
  executes compiled tests, not the agent.
- **One monolithic module.** Rejected: it forces one runtime profile on three
  different jobs and reintroduces the agent-is-the-test failure mode.

## Open Questions

- The intent-extraction strategy in Compile (how observable target state becomes
  stable assertions) — the deepest unknown, to be prototyped first.
- The anchor grammar a `## Verified By` reference uses to point at a specific
  compiled test/case (coordinate with the RAC-side design
  `capability-verification-evidence`).

## Related Decisions

- lv-adr-001-product-identity
- lv-adr-002-pluggable-runner

## Related Requirements

- faithful-session-to-test
