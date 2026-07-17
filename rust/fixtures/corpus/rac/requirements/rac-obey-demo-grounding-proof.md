---
schema_version: 1
id: RAC-KV6KFQZHDFR5
type: requirement
tags: [user-facing, demo, grounding, proof]
---
# Requirement: Obey-Demo Grounding Proof

## Status

Accepted

Classification: the release's non-cuttable success anchor (Tier 2). It is the
v0.23.0 definition of done made observable. It stays a manual smoke, never a CI
gate; the cut line sits above it, so WS6/WS5/WS8/WS10 are dropped before the
demo, never the demo itself.

Delivered as `examples/obey-demo/` — replay steps (`README.md`) plus an unedited
capture (`capture.md`) of one real grounded run. It reuses the already
PR-reviewed `examples/guide/` fixture corpus (whose Accepted `ADR-001`,
`GUIDE-KTW9YBDWDBFM`, forbids hard `DELETE`) rather than minting a second
corpus; the verbatim prompt asks for that forbidden hard delete and the agent
(Claude Code, over the four read-only tools) declines and cites
`GUIDE-KTW9YBDWDBFM`. It is not wired into CI or the test suite (REQ-003/004).

## Problem

The release's definition of done is an outcome, not green CI: a real coding
agent must demonstrably stop relitigating a recorded decision after consulting
Lore. An automated multi-agent CI harness to prove this would be
non-deterministic, slow, costly, and only half-automatable in a week, and a
verdict tool that decides "this violates a decision" is barred from core
(ADR-034). What is needed instead is one reproducible, honest manual
demonstration in which the agent — not RAC — recognizes the conflict and cites
the governing decision.

This artifact pins the recording down concretely so it is turnkey to produce
once the release's features exist: it exercises WS1's fixture corpus, WS2's
explainable retrieval, WS3's `rac doctor`, WS5's provenance fields, and WS11's
trust model, driven by one live agent over the four read-only tools.

## Requirements

- [REQ-001] The release MUST produce one reproducible manual demonstration with three fixed parts: (a) a fixture or partner-representative repo whose corpus contains an `Accepted` ADR that forbids a specific, named change and that itself reached the corpus through human PR review (the trust boundary, ADR-065); (b) a real coding agent wired to exactly the four read-only MCP tools (`get_artifact`, `search_artifacts`, `get_related`, `get_summary`) and nothing that can issue a verdict; (c) one verbatim prompt that asks for the change the ADR forbids, recorded alongside the demo.
- [REQ-002] The captured recording or log MUST show, in order: the agent calling at least one retrieval tool (`search_artifacts` and/or `get_related`) and `get_artifact` to read the governing ADR; the agent then DECLINING the forbidden change; and the agent citing the governing decision by its id (e.g. `RAC-…` / `ADR-0xx`) as the reason. The tool calls and their results MUST be visible in the capture, not summarized after the fact.
- [REQ-003] The demonstration MUST ship with written, repeatable steps (the fixture path, the exact prompt, the agent and its tool wiring, and how to replay) and MUST NOT be a CI gate or a golden test.
- [REQ-004] The release MUST NOT build an automated multi-agent CI harness; this manual obey-demo supersedes that intent. No tool in the loop renders a conflict verdict — the agent supplies the judgment, Lore supplies the facts (ADR-034).
- [REQ-005] Results MUST be genuine. The recording MUST be of a real run with the real tool calls and real model output; faked, staged, or hand-edited transcripts are unacceptable. Because the behaviour is stochastic (ADR-034), the steps MUST describe how the run was obtained honestly (e.g. the run is reproducible from the written steps and the capture is unedited); cherry-picking a lone success while hiding failures is a faked result.

## Acceptance Criteria

- A recorded, unedited capture plus written replay steps exists, showing the
  tool calls, the declined change, and the cited decision id.
- The forbidding ADR is `Accepted` and entered the corpus via human PR review.
- It is explicitly a manual smoke, not a CI gate or golden test, with no faked
  results and no verdict tool in the loop.
- Setup notes for additional agents (Cursor, Codex) MAY be documented but are
  not required.

## Success Metrics

- The release success criterion is met: a real or partner-representative agent,
  given the recorded prompt, consults Lore and declines the forbidden change
  while citing the governing decision id — with no verdict tool involved.

## Risks

- A single demo may not generalize. Mitigation: source the scenario from a real
  or partner-representative decision and document the steps so it can be re-run
  and extended.
- The behaviour is stochastic, so one run is not a guarantee (ADR-034).
  Mitigation: keep the capture unedited and the steps replayable; report the
  run honestly rather than presenting a cherry-picked success as typical.

## Assumptions

- A real coding agent wired to the four read-only tools is sufficient to
  demonstrate grounding without bespoke harness infrastructure.
- The fixture corpus, explainable-retrieval output, provenance fields, and
  trust-model docs from the Tier 1 / Tier 2 workstreams exist before the demo
  is recorded.

## Related Decisions

- adr-034
- adr-065

## Related Requirements

- rac-artifact-trust-model
- rac-grounding-eval-benchmark

## Related Roadmaps

- v0.23.0-hardening
