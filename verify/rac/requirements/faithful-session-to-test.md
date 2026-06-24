---
schema_version: 1
id: LV-KVW1HX4S2Z1V
type: requirement
tags: [user-facing, compile, fidelity]
---
# Requirement: Faithful Session-to-Test Compilation

## Status

Proposed

Classification: `[user-facing]` — the property the whole product is bought for.
An agent driving a target proves nothing unless the test it emits reproduces the
same assertions deterministically, without the agent in the loop.

## Problem

The defining risk of autonomous QA is that an agent explores a product, declares
success, and emits a test that is flaky, asserts nothing meaningful, or is
over-fitted to one DOM snapshot. The value proposition — "verify an agent's work
purely by looking at the test and its output" — collapses if the emitted test is
not a faithful, stable reproduction of what the agent verified. This is the
hardest part of the product and its moat (RAC ADR-083 records it as the
load-bearing engineering).

## Requirements

- [REQ-001] The Compile step MUST emit a durable end-to-end test (Playwright as the execution/recording spine) that carries intent-level assertions derived from the agent's session, not merely a replay of raw input events.
- [REQ-002] An emitted test MUST be accepted only after a fidelity check: it is re-run headless N times and accepted only if every run is green and stable. A test that is flaky across the N runs MUST be rejected or quarantined, never committed as passing.
- [REQ-003] An accepted test MUST be target-agnostic: it MUST run unchanged against any configured target (dev, production) and operating system, with `baseURL`, auth strategy, and OS/browser injected at run time (LV-ADR-002), never hardcoded.
- [REQ-004] Each accepted test MUST produce a replayable trace artifact a reviewer can inspect without a local run, so the test and its evidence are reviewable together in the pull request.
- [REQ-005] The Compile step MUST NOT write any reference into a Lore corpus directly; a passing, faithful test results in a *proposed* `## Verified By` reference in a human-reviewed PR (RAC ADR-065, LV-ADR-001).

## Success Metrics

- A compiled test, re-run N times across at least one non-host OS and both a dev
  and a production target, is green and stable before acceptance — measured, not
  assumed.

## Risks

- The N-run gate is too weak to catch real flake. Mitigation: make N and the
  stability criteria configurable and conservative by default; treat any
  non-determinism as a rejection, not a warning.
- Intent extraction produces assertions that pass but mean nothing. Mitigation:
  assertions are derived from observable target state the agent acted on, and the
  reviewer sees both the assertion and the trace in the PR.

## Assumptions

- Playwright (or an equivalent driver) provides the deterministic auto-waiting and
  trace capture the fidelity check and the replay artifact depend on.
- A target can be exercised idempotently or with seedable state for dev; the
  production target is verified with read-only / idempotent test variants.

## Related Decisions

- lv-adr-001-product-identity
- lv-adr-002-pluggable-runner

## Related Designs

- drive-compile-run-architecture
