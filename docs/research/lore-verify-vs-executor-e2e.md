# lore-verify vs. executor `e2e/` — Prior-Art Comparison

> **Status: research document, not a RAC artifact.** Per ADR-010 ("Documents Are
> Not Artifacts") and ADR-024 ("RAC Is Not a Content Store"), this is reference /
> working material, not part of the validated `rac/` corpus. Its *actionable*
> conclusions are captured as corpus artifacts — see "What this produced" below.
>
> **Scope:** how the planned `lore-verify` product (RAC ADR-083 and the
> `lore-verify-programme` roadmap) compares to the existing, mature e2e suite in
> `RhysSullivan/executor` — the "ok version" this direction was inspired by.
> **Method:** direct read of the public repo (`e2e/AGENTS.md`, `package.json`,
> `scenarios/`, `scripts/`, directory structure).
> **Date:** 2026-06.
> **Source:** <https://github.com/RhysSullivan/executor/tree/main/e2e>

---

## Executive summary

Executor's `e2e/` is a **mature, hand-authored, cross-deployment test harness**
with strong review-artifact discipline and built-in playback. It is *ahead of the
`lore-verify` plan on nearly everything we considered table stakes*, and it
independently arrived at our core thesis ("the test is the review artifact"),
which is strong validation that the thesis is right.

`lore-verify` is genuinely differentiated on only **two** things:

1. **Compile** — driving a product via an agent and *auto-generating* a durable
   test with a fidelity gate. Executor sidesteps this entirely by hand-authoring
   tests. This is our novel runtime bet **and our biggest risk**.
2. **Coverage of governed intent** — linking tests back to a governed Lore
   requirements corpus and reporting *which decided-upon capabilities are provably
   verified*. This is **structurally impossible for executor** without a governed
   decision corpus, and is the durable, Lore-native wedge.

One-sentence read:

> Executor answers *"do these flows pass?"*; `lore-verify` should answer *"which
> of the things we decided must stay true are provably verified?"* — and treat
> auto-compilation as high-upside R&D, not a guaranteed differentiator.

---

## What executor's `e2e/` already does (and is ahead of our plan on)

| Capability | executor `e2e/` | `lore-verify` plan | Read |
| --- | --- | --- | --- |
| **Multi-target** | A `Target` interface with typed *capabilities* (API, browser, billing, telemetry, MCP-OAuth); "a scenario is ONE user-meaningful journey, written once against the Target interface and run on every deployment" (cloud + selfhost + desktop + cli) | LV-ADR-002 runner/target injection (planned) | A more sophisticated, **built** version of our target abstraction — effectively a reference implementation of our runner seam. |
| **Playback / video** | `recordings/` + a custom `viewer/` (monaco + asciinema-player); traces/videos/screenshots auto-emit to `runs/<target>/` | "traces as the artifact" (planned) | Done, and richer (terminal *and* browser, plus a "desk" virtual-desktop mode). |
| **Cross-deployment breadth** | cloud / selfhost / desktop / desktop-packaged / cli / local | dev/prod + OS matrix (v0.2.0, planned) | Broader scope, already wired. |
| **Determinism discipline** | Effect finalizers, `newIdentity()` isolation, slug-prefixed resources, public-surface-only rule | stated as constraints | Operationalized, not aspirational. |

## Where executor validates our bets (independent convergence)

- **Playwright as the execution/recording spine** — same choice (`playwright ^1.60`).
- **Test-as-review-artifact** — stated almost verbatim: *"The test source is the
  review artifact. A reviewer judges correctness by reading the test; write it so
  it reads as a spec."*
- **Assert user outcomes, drive public surfaces only** — exactly our intent-level
  assertion stance.

Two independent designs landing on the same philosophy is the strongest available
signal the philosophy is correct.

## Our two genuine differentiators

### 1. Compile (drive → auto-generate a durable test + fidelity gate)

Executor's agents **hand-author** scenarios (`scenarios/*.test.ts` are
hand-written TypeScript journeys; the `record-*` / `film.ts` scripts produce
*media for playback*, not compiled tests). Nobody drives the product via
computer-use and compiles the session into a test. `lore-verify`'s
`faithful-session-to-test` (Drive → Compile, accept only after N green, stable
re-runs) is the novel runtime capability — and the harder, riskier path.

### 2. Coverage-of-intent against a governed corpus

Executor's scenarios are "product promises" expressed as test *names*, but there
is **no link back to a durable, governed requirements graph** and **no
deterministic answer to "which capabilities are provably verified?"**. The Lore
mechanism — a `verified-by` asset reference, the `unverified-capability` coverage
class, and the `rac export --graph` worklist — is something executor **cannot
replicate without a governed decision corpus**. This is the defensible wedge.

## The honest risk

Differentiator #1 is also the biggest liability: executor *sidesteps the hardest
problem* by hand-authoring tests, and hand-authored tests are inherently more
reliable than auto-compiled ones. If Compile/fidelity proves too flaky,
`lore-verify` collapses back toward "executor's e2e, but with Lore coverage" —
still valuable because of #2, but no longer novel on the runtime side. Mitigation
already in the plan: v0.1.0 Initiative 1 and the design's lead Open Question both
target intent-extraction *first*, so Compile is de-risked before breadth — with a
hand-authored-tests-plus-coverage fallback if it does not pan out.

## Strategic implications

1. **Don't reinvent the harness — study theirs.** `e2e/targets/` and the
   `Target`/capabilities interface is essentially LV-ADR-002's runner abstraction,
   already built; even with a clean build, the *interface design* is worth
   learning from (and there is an obvious collaboration angle).
2. **Lead positioning with coverage-of-intent (#2), not autonomous browsing
   (#1).** Agent-driven browser QA is increasingly commodity (executor,
   browser-use/qa-use, desplega/qa-use); "coverage of governed intent" is the
   Lore-native wedge no general e2e tool can match.
3. **Reframe the moat.** The more durable moat is the **Lore linkage** (#2);
   Compile (#1) is high-upside R&D, not a guaranteed differentiator.

## What this produced (actionable conclusions captured in the corpus)

- The **risk** ("executor sidesteps Compile by hand-authoring; auto-compilation is
  the load-bearing, riskiest bet") is recorded in the `lore-verify-programme`
  roadmap Risks.
- The **positioning** ("lead with coverage-of-intent, not autonomous browsing;
  Compile is R&D, the Lore linkage is the moat") is recorded in the
  `lore-verify-programme` roadmap Context.
- The **harness-reuse** note (study executor's `Target` interface rather than
  reinvent) is recorded in the programme's assumptions/constraints.
