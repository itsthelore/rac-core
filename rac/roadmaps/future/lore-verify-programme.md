---
schema_version: 1
id: RAC-KVW1EBQ95RYA
type: roadmap
tags: [structure, org, distribution, verify, agents]
---
# RAC — lore-verify Build Programme (Future)

## Status

Planned

Unscheduled — the full build plan for `lore-verify`, the autonomous-QA consuming
product decided in ADR-083. It is a structural, cross-cutting programme (a new
sibling product), not a feature release on the current series, so it lives in
`future/` and graduates into a versioned plan when prioritised. It mirrors the
delivery discipline of `wayfinder-extraction` (prototype in a subdirectory, brand
early, extract under ADR-064's safety contract) and the topology of
`repo-extraction-programme`.

## Context

ADR-083 splits the autonomous-QA direction three ways: the verification
*evidence and coverage* capability stays in the open-source core
(`rac-capability-verification-evidence`, `capability-verification-coverage`); the
QA *runtime* is a separate consuming product, `lore-verify`; and the commercial
surface is verification *governance* on a separate hosted brand. This programme
builds the middle layer — the product that drives a browser and a terminal,
converts a working session into durable end-to-end tests, runs them across targets
and operating systems, and emits replayable trace/video artifacts — and wires it
to the core over the published contract.

Four decisions, recorded in ADR-083 and confirmed for this programme, shape it:

- **Hosting is a separate brand**, never required for the local path (ADR-035);
  the runner is a pluggable interface so a hosted VM-fabric backend is a drop-in,
  not a re-architecture.
- **Prototype in a `verify/` subproject** inside `rac-core` (ADR-064 safety
  contract), then extract to `itsthelore/lore-verify` once it ships.
- **Branded now** as `lore-verify` (the `lore-*` prefix, ADR-068 — a
  contract-dependent companion, unlike the independently-branded Wayfinder).
- **Clean build**, not a fork of any existing prototype.

The product depends on RAC only through the published contract (`rac export
--graph`, the `lore` MCP read tools) and never on engine internals (ADR-063),
exactly as `decisiongrounding` and the extracted clients do.

**Prior art and positioning.** A mature reference point already exists — the
hand-authored, cross-deployment e2e suite in `RhysSullivan/executor` (compared in
`docs/research/lore-verify-vs-executor-e2e.md`). It independently arrived at this
direction's core thesis ("the test is the review artifact") and is already ahead
on the table-stakes: a `Target`/capabilities interface for multi-deployment runs,
Playwright, and built-in recording/playback. The lesson for positioning is sharp:
autonomous browser-driven QA is becoming commodity, so `lore-verify` must **lead
with coverage of governed intent** — answering "which decided-upon capabilities
are provably verified?" against the Lore corpus — not with "an agent that drives a
browser." The durable moat is the **Lore linkage** (the `verified-by` edge and
coverage), which a general e2e tool cannot replicate without a governed decision
corpus; the session-to-test **Compile** step is high-upside R&D, not a guaranteed
differentiator.

## Outcomes

- `lore-verify` exists as a clean-built product: an agent that, given real
  developer tools, develops against a target and emits durable e2e tests, runs
  them across targets (dev/prod) and operating systems, and produces replayable
  trace artifacts a reviewer can inspect without running anything locally.
- A reviewer can verify an agent's work from the PR alone: the diff carries the
  new `## Verified By` line *and* the test it points at, plus the trace artifact.
- The product consumes the core only over the published contract, and writes back
  to the corpus only by proposing `## Verified By` lines in a human-reviewed PR
  (ADR-065) — it never writes the corpus directly and never imports engine
  internals.
- The `verify/` subproject is self-contained — its own corpus, packaging, tests,
  and CI — and ready to extract to `itsthelore/lore-verify` with history preserved
  under ADR-064's safety contract.
- Adding a hosted runner later is a new backend behind the runner interface, not a
  rebuild.

## Initiatives

### Initiative 1 — Confirm the brand before it is public

Confirm `lore-verify` is available as a published name (PyPI / npm distribution,
the `itsthelore/lore-verify` repo, any trademark concern) before it is committed
to a public surface — the step `wayfinder-extraction` added after Wayfinder's
PyPI clash. Initial check: no `lore-verify` distribution exists on PyPI or npm;
the scoped `@itsthelore/lore-verify` is free; the `lore` family brand
(distinct from Epic Games' unrelated "Lore" VCS) is the pre-existing
consideration, not specific to verify. If a clash surfaces, choose the
alternative here before publishing.

### Initiative 2 — Stand up the `verify/` subproject with its own corpus

Create `verify/` as a self-contained subproject inside `rac-core`, the way
`wayfinder/` was: its own `pyproject`/package manifest, tests, LICENSE, CI, and
its **own RAC corpus** under `verify/rac/` with the repository key `LV`
(`LV-` artifact ids), seeded with its first decisions, requirements, a design,
and a roadmap. The subproject imports no `rac` internals; it consumes the
published contract only. Its corpus validates independently
(`rac validate verify/rac/`), so `lore-verify` dogfoods Lore on itself from day
one.

### Initiative 3 — Build the product surface: Drive, Compile, Run

Three internal modules, the load-bearing engineering:

- **Drive** — the agent loop with real developer tools (a CDP-driven browser and a
  sandboxed terminal). Slow, exploratory, AI-powered; BYO credentials (ADR-035's
  posture carries into the companion product). Local and self-hosted models
  supported.
- **Compile** — the session-to-test translator that emits durable e2e tests
  (Playwright as the execution/recording spine) and *asserts fidelity*: the
  emitted test is re-run headless N times and accepted only if green and stable.
  This is the product's moat and the hardest part — an agent passing a session
  proves nothing unless the emitted artifact reproduces the assertions
  deterministically.
- **Run** — target-parameterized (`baseURL` + auth strategy injected, never
  hardcoded) and OS-matrixed, behind a **pluggable runner interface** (a local
  runner ships open; a hosted VM-fabric runner is a later drop-in). Traces are the
  replayable video artifact.

The agent runs once (Drive); the compiled tests run everywhere (Run) — keeping
those two runtimes separate is what lets "thorough agent" and "fast, multi-OS
tests" coexist.

### Initiative 4 — Wire the contract seam to the core

The only coupling to RAC, deliberately thin and bidirectional:

- **Read:** consume `rac export --graph` / the `lore` MCP read tools to learn the
  live capabilities and which carry no `verified-by` edge — the worklist of what
  to verify.
- **Write-back:** after Compile/Run produce a trustworthy test, open a PR adding
  `## Verified By` lines to the relevant capability artifacts. A human reviews and
  merges (ADR-065, ADR-067, ADR-063). `lore-verify` never writes the corpus
  directly.

This closes the loop with `capability-verification-coverage`: the core reports
the gap, `lore-verify` fills it, the human ratifies it, and `rac coverage` shows
it closed.

### Initiative 5 — Extract to `itsthelore/lore-verify`

Once the subproject reaches a shippable state and is confirmed standalone (its
suite, lint, and types pass in a clean environment with no `rac` source on the
path — only the published contract), lift `verify/` to its own repository with
history preserved (`git subtree split`, the Wayfinder method), and remove it from
`rac-core` under ADR-064's safety contract (never delete until the capability
lives elsewhere). The corpus artifacts that record the decision (ADR-083, the
requirement, the design, this roadmap) stay in `rac-core` as the historical
record.

### Initiative 6 — Hosted offering (separate track, out of scope here)

Recorded as the next destination, not built by this programme: a hosted brand
provides the VM-fabric runner backend (real OSes the user does not own), the
fidelity/flake-elimination guarantee, and org-scale verification governance
(multi-repo aggregation of `rac coverage`, audit reporting). It plugs into the
runner interface from Initiative 3. It is a separate offering with its own
decisions and is never required for the local path (ADR-035, ADR-083).

## Constraints

- **No engine coupling** (ADR-063): `lore-verify` consumes the published contract
  and the public CLI / `lore` MCP only — never `rac` internals and never the
  `.rac/` namespace of the host repo.
- **Knowledge/work boundary** (ADR-017, ADR-024): execution, results, videos, and
  traces live in `lore-verify` and the consuming repo, never in `rac-core`.
- **Human-declared write-back** (ADR-065, ADR-074, ADR-082): evidence references
  enter a corpus only by a reviewed PR; `lore-verify` proposes, a human ratifies.
- **AI-optional posture carried over** (ADR-035): BYO credentials, local models
  supported, no mandatory hosted inference for the open path.
- **Deterministic compiled tests**: the emitted tests are the durable, reviewable
  artifact; fidelity is asserted before a test is accepted.
- **Safety sequencing** (ADR-064): nothing is removed from `rac-core` until
  `lore-verify` lives in its own repo; history is preserved across the move.
- **Clean build**: no fork of any existing prototype. The clean-build rule governs
  *code*, not *learning*: the `Target`/capabilities interface in `RhysSullivan/executor`'s
  `e2e/` suite is a working reference for the runner abstraction (LV-ADR-002) and
  should be studied rather than reinvented (see
  `docs/research/lore-verify-vs-executor-e2e.md`).

## Non-Goals

- Building the hosted service or the VM fabric (Initiative 6 is a separate track).
- Folding in or depending on any third-party prototype (clean build, ADR-083).
- Adding any test runtime, browser driver, or test-result storage to `rac-core`
  (ADR-083, ADR-017, ADR-024).
- Creating the `itsthelore/lore-verify` repository as part of this corpus task;
  the repo is created when Initiative 5 runs.

## Implementation Contract

**Subproject layout** (mirrors `wayfinder/`'s self-contained shape):

```text
verify/
├── README.md
├── pyproject.toml            # or package.json — own packaging, own name
├── src/lore_verify/          # Drive / Compile / Run modules
├── tests/
├── rac/                      # its OWN corpus, key LV
│   ├── decisions/            # LV-ADR-001 … (identity, boundary, runner interface)
│   ├── requirements/
│   ├── designs/
│   └── roadmaps/
└── .rac/config.yaml          # repository_key: LV
```

**Stand up the subproject corpus** (Initiative 2):

```bash
rac init --key LV verify
# then `rac new` run from within verify/ for LV- ids, and
# `rac validate verify/rac/` as the subproject's own gate
```

**Extract when shipped** (Initiative 5), history-preserving:

```bash
git subtree split --prefix=verify -b lore-verify-extract
# push lore-verify-extract to itsthelore/lore-verify main, verify standalone,
# then remove verify/ from rac-core under ADR-064's safety contract
```

After extraction, `rac-core`'s `rac validate rac/`, `rac relationships rac/
--validate`, and `rac review rac/` gates stay green and `pytest` passes.

## Success Measures

- `lore-verify` drives a target, emits a durable e2e test, runs it against
  dev and prod and across at least one non-host OS, and produces a replayable
  trace — all from a single local install with the user's own AI credentials.
- A compiled test, re-run N times, is green and stable before it is accepted
  (fidelity asserted, not assumed).
- Opening `lore-verify` against a Lore corpus produces a PR adding `## Verified
  By` lines that, once merged, clear the matching `unverified-capability` gaps in
  `rac coverage`.
- The subproject's suite, lint, and types pass with no `rac` source on the path
  (only the published contract), confirming zero internal coupling.
- After extraction, `rac-core` carries no test-runtime code and its corpus gates
  stay green.

## Assumptions

- The published contract (`rac export --graph` and the `lore` MCP read tools) is
  sufficient for `lore-verify` to learn the verification worklist without engine
  internals; `capability-verification-coverage` ships the `verified-by` export
  edge it reads.
- ADR-083 is accepted before this programme is scheduled; it is Proposed until
  then.
- The `itsthelore` organisation can host the sibling repository when Initiative 5
  runs.
- `lore-verify` is available as a public distribution name (Initiative 1
  confirms); the chosen name is applied consistently if an alternative is needed.

## Risks

- **Fidelity gap.** An agent "passes" but the emitted test is flaky or asserts
  nothing. Mitigation: Compile's N-run stability gate is the acceptance bar, not
  the agent's say-so — the load-bearing engineering.
- **Auto-compilation may not pay off.** The closest prior art
  (`RhysSullivan/executor`, see `docs/research/lore-verify-vs-executor-e2e.md`)
  deliberately *sidesteps* this step by hand-authoring tests, and hand-authored
  tests are inherently more reliable than auto-compiled ones. If Compile proves too
  flaky, `lore-verify` collapses toward "executor's e2e plus Lore coverage" — still
  valuable for the coverage linkage, but not novel on the runtime side. Mitigation:
  de-risk intent-extraction *first* (v0.1.0 Initiative 1, the design's lead Open
  Question), and keep a hand-authored-tests-plus-coverage fallback so the product's
  value does not depend solely on Compile succeeding.
- **Scope creep back into the core.** Pressure to put a runner or results in
  `rac-core` for convenience. Mitigation: the boundary is recorded in ADR-083 and
  `rac-capability-verification-evidence` REQ-007; this programme keeps all runtime
  in `verify/`.
- **Contract drift.** `lore-verify` lags the export contract after extraction.
  Mitigation: it pins a published major and depends on no internals (ADR-063),
  the same discipline as the other extracted repos.
- **Brand clash.** The `lore-verify` name is taken. Mitigation: Initiative 1
  confirms availability before any public surface, the Wayfinder lesson.
- **Prototype lingers, extraction never happens.** Mitigation: Initiative 5 is
  explicit and gated on the product shipping, per ADR-064's cutover discipline.

## Related Decisions

- adr-083
- adr-064
- adr-068
- adr-069
- adr-063
- adr-067
- adr-035
- adr-012
- adr-065
- adr-017
- adr-024

## Related Requirements

- rac-capability-verification-evidence

## Related Designs

- capability-verification-evidence

## Related Roadmaps

- capability-verification-coverage
- repo-extraction-programme
