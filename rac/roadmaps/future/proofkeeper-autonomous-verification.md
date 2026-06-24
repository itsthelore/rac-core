---
schema_version: 1
id: RAC-KVW5228P65A3
type: roadmap
---
# RAC — Proofkeeper: Autonomous Verification (Future)

## Status

Planned

Unscheduled — captured as future intent for the autonomous-verification sibling
product whose identity, name, prefix, and boundary are settled in ADR-083.
Nothing here is committed scope; it graduates out of `future/` into its own
versioned series (in `itsthelore/lore-proofkeeper`, not this engine repo) when
the product is actively pursued. This item records the *build shape* of
Proofkeeper; ADR-083 owns the *naming and boundary* decision.

## Context

Proofkeeper is an autonomous QA agent: given a browser and a terminal, it drives
a product the way a developer would, compiles that working session into durable
Playwright end-to-end tests, and asserts fidelity by re-running each emitted test
N times and keeping only the green, stable ones. It then runs the compiled suite
fast and in parallel across targets and operating systems, emitting replayable
traces, so an agent's work is verified by reading the committed test and its
trace in the pull request rather than by a local run.

It is a contract consumer of Lore, not an engine extension (ADR-083, ADR-073,
ADR-063): it reads `rac export --graph` and the `lore` MCP to find product
capabilities that lack verifying tests, and it writes back only by proposing
`## Verified By` links in a human-reviewed pull request (ADR-065). The agent
runtime lives here, in the sibling product, never in Lore's engine (ADR-035,
ADR-002, ADR-069). The faithful session→test conversion — compile a real session
into a test and prove it is stable — is the moat.

## Outcomes

- A recorded build target for Proofkeeper that the eventual
  `itsthelore/lore-proofkeeper` repo derives from, distinct from the engine's
  roadmap and consistent with ADR-083's boundary.
- A coverage read-model that answers "which product capabilities have no
  verifying test?" from Lore's published contract — the free, local hook into
  the corpus.
- A session→test compiler with a fidelity gate (the N-times-rerun stability
  check) that makes emitted tests trustworthy enough to commit unread-and-rerun.
- A parallel, cross-target, cross-OS runner behind a pluggable interface,
  emitting replayable trace artifacts attached to the pull request.
- A human-reviewed write-back path that proposes `## Verified By` links, gated on
  a new typed relationship edge in the engine.
- A commercial tier — Proofkeeper Cloud — that adds hosted, org-scale
  verification without taking custody of the corpus or putting a model in the
  engine.

## Initiatives

### Initiative 1 — Coverage read-model ("what is unverified?")

Consume Lore's published contract (`rac export --graph`, the `lore` MCP) to
report which product capabilities lack a verifying test. This is the free, local
coverage report and the only place Proofkeeper reads the corpus. It never writes
in this initiative.

### Initiative 2 — Drive-and-compile agent

The bring-your-own-model agent loop that drives a product with a browser and a
terminal and compiles the working session into a Playwright end-to-end test.
Runs once, slow, exploratory; the output is a candidate test, not a verdict.

### Initiative 3 — The fidelity gate (the moat)

Re-run each emitted test N times and accept it only if it is green and stable;
discard or quarantine the rest. This faithful session→test conversion is the
differentiator and the reason a reviewer can trust a committed test without
running it locally.

### Initiative 4 — Parallel cross-target runner

Run the accepted suite fast and in parallel across targets (dev, prod) and
operating systems behind a pluggable runner interface, emitting replayable trace
artifacts. The local runner is open-source; the hosted VM-fabric runner is the
commercial tier (Initiative 7).

### Initiative 5 — Human-reviewed write-back and the new edge

Propose `## Verified By` links from a verified capability to its test, only via a
human-reviewed pull request (ADR-065). This depends on adding a `verified-by` /
`verifies` typed relationship to the engine's relationship registry (ADR-055) and
graph export (ADR-074) — engine work that must land before the write-back ships.

### Initiative 6 — Repository, packaging, and release

Stand up `itsthelore/lore-proofkeeper`, publishing `lore-proofkeeper` (PyPI) and
`@itsthelore/proofkeeper` (npm), per ADR-068 and ADR-073. The `lore-` prefix is
fixed by ADR-083; confirm registry and trademark availability before any public
release, per the Wayfinder name-check discipline (ADR-069).

### Initiative 7 — Proofkeeper Cloud (commercial tier)

A Lore-branded hosted tier (ADR-012, `commercial-layer-positioning`): a VM-fabric
runner over real operating systems, the flake-elimination / fidelity guarantee,
and org-scale verification governance (multi-repo coverage aggregation and audit
reporting). Sequenced after the open core; it adds hosted intelligence over the
corpus without taking custody of it.

## Constraints

- No model or inference enters Lore's engine; the agent runtime is this sibling
  product's alone (ADR-035, ADR-002, ADR-069).
- Proofkeeper consumes Lore's published contract, never engine internals
  (ADR-063, ADR-073).
- The corpus stays files-in-git as the single source of truth; the write-back is
  a proposed pull request a human reviews, never a direct mutation (ADR-065,
  ADR-080, ADR-024).
- `rac validate rac/`, `rac relationships rac/ --validate`, and `rac review rac/`
  stay clean over the artifacts this item adds to the engine corpus.

## Non-Goals

- Becoming a coding agent, a codegen tool, or a general-purpose agent runtime.
  Proofkeeper produces verification evidence and nothing else.
- A Lore-core feature: the runtime, browsers, and test execution live in the
  sibling product, not in `rac-core`.
- A fourth standalone commercial brand or per-seat pricing for Proofkeeper Cloud
  (`commercial-layer-positioning`); the hosted tier is Lore-branded and priced
  per-org.
- Taking custody of the corpus or becoming a system of record other than git
  (ADR-080, ADR-024).

## Success Measures

- A single recorded build shape exists for Proofkeeper that the eventual repo and
  any pitch derive from, distinct from the engine roadmap and from
  `commercial-layer-positioning`.
- The coverage report answers "what is unverified?" from the published contract
  with no write to the corpus.
- An emitted test that passes the fidelity gate re-runs green and stable in CI,
  and its trace is readable in the pull request without a local run.
- The `## Verified By` write-back lands only through a human-reviewed pull request
  and only after the `verified-by` edge exists in the registry and graph export.
- Requests to "build the verifier into Lore core" or "give it its own brand" are
  answered by ADR-083, not by scope drift.

## Assumptions

- Lore's published contract (`rac export --graph`, the `lore` MCP) exposes enough
  capability structure to compute meaningful verification coverage.
- The fidelity gate can reach an acceptably low flake rate on compiled tests;
  this is the load-bearing technical bet and the moat.
- Teams that want autonomous, committed, replayable verification evidence are a
  real segment, and the hosted VM-fabric / governance tier is where commercial
  investment concentrates (ADR-012).

## Risks

- The fidelity gate cannot drive flake low enough, undermining the trust-the-
  committed-test premise. Mitigation: the gate is Initiative 3, the explicit
  moat, with stability as its acceptance bar.
- Scope creep into general agent runtime or codegen erodes the determinism and
  open-core trust that justify the boundary. Mitigation: the Non-Goals and
  ADR-083's discipline boundary, mirroring the Wayfinder precedent.
- The write-back ships before the relationship edge exists, producing references
  the engine cannot validate. Mitigation: Initiative 5 gates the write-back on
  the new edge landing in ADR-055 / ADR-074 surfaces first.
- Brand-explanation load grows with a fourth product. Mitigation: ADR-083 fixes
  the `lore-` prefix and the "Lore Proofkeeper" display form, and the commercial
  tier stays a Lore-branded tier rather than a new name.

## Related Decisions

- adr-083
- adr-084
- adr-012

## Related Roadmaps

- commercial-layer-positioning
