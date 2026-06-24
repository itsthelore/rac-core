---
schema_version: 1
id: RAC-KVW520ZXJ7HJ
type: decision
---
# ADR-083: Proofkeeper — Autonomous Verification as a Lore-Dependent Product

## Context

The Lore family has settled a pattern for naming the surfaces a team installs:
evocative agentive role-nouns that describe a function, several on a custodial
`-keeper` suffix — Gatekeeper (the PR enforcement gate, ADR-049), Watchkeeper
(the CI change reviewer, ADR-043), Explorer (the navigator, ADR-028) — plus one
independent sibling, Wayfinder (ADR-069), the prompt-complexity router.

A new capability is proposed: an autonomous QA agent that, given real developer
tools (a browser and a terminal), drives a product the way a developer would
(an AI agent loop, bring-your-own-model, run once, slow, exploratory), compiles
that working session into durable end-to-end tests (Playwright), and asserts
*fidelity* — it re-runs each emitted test N times and keeps it only if it is
green and stable. It then runs the compiled suite fast and in parallel across
targets (dev, prod) and operating systems behind a pluggable runner, emitting
replayable trace artifacts. The point: an agent's work is verified purely by
reading the committed test and its trace in the pull request — no local run.

This needs a name in the family, a prefix decision, a stated boundary against
the engine, and a commercial-tier shape. Several recorded decisions fence it and
must not be contradicted:

- **ADR-068** fixes the naming principle: `lore-*` is anything a user or team
  *installs*; `rac-*` is the engine and its build-coupled internals.
- **ADR-069** establishes that an *independent* brand (Wayfinder) is earned
  **only** by zero runtime dependency on Lore — a router must not force
  installing a knowledge engine.
- **ADR-073** records the discriminator for repo shape: an installable product
  with independent cadence and ownership earns its own repo; a thin contract
  consumer does not.
- **ADR-049 / ADR-035 / ADR-002** keep inference and runtime concerns out of the
  engine; **ADR-069** is the precedent that such concerns live in a *sibling*
  product, not in Lore core.
- **ADR-065** records that the trust boundary is human PR review; artifact
  content is untrusted until a reviewer accepts it.
- **ADR-012** and `commercial-layer-positioning` reserve commercial value for
  org-scale / hosted capability and prefer a *Lore-branded hosted tier, not a
  fourth standalone name* (the git → GitHub pattern).

A brand-clash note also bears on the name: Epic Games shipped an open-source
version-control system named "Lore" (2026-06-17). It targets a different
audience (game studios, large binary assets) but shares the broad
developer-tooling category, so the family's distinctive role-noun names — and the
`itsthelore` handle — are the practical disambiguators.

## Decision

The product is **Proofkeeper**, a Lore-dependent sibling product. It is the one
sanctioned runtime in the Lore family, scoped narrowly to verification.

### Name

**Proofkeeper.** It sits on the family's custodial `-keeper` pattern beside
Gatekeeper and Watchkeeper and names the function, not a feature: it *keeps the
proof* — the stable test plus its replayable trace — accepting only the tests
that survive N green, stable re-runs and discarding the rest. The display brand
is **Lore Proofkeeper** where disambiguation helps (notably against Epic's
"Lore" VCS), and **Proofkeeper** when spoken plainly, exactly as Gatekeeper is
spoken while its repo is `lore-gatekeeper`.

### Prefix — `lore-`

Proofkeeper carries the `lore-` prefix. It is an installable surface (ADR-068),
and it has a hard runtime dependency on Lore's published contract: it reads
`rac export --graph` and the `lore` MCP to learn which product capabilities lack
verifying tests, and it writes back `## Verified By` links. It therefore fails
Wayfinder's zero-dependency test (ADR-069) and does **not** earn an independent
brand. It ships as `lore-proofkeeper` (PyPI), `@itsthelore/proofkeeper` (npm),
in its own repository `itsthelore/lore-proofkeeper` — its own repo, not a
consolidated module, because it is an installable product with independent
cadence and ownership (ADR-073). The `lore-` prefix governs the package and
repository identity; it does not change the spoken brand.

### Boundary — a contract consumer, not an engine extension

Proofkeeper owns all runtime and content — browsers, test runs, traces; Lore
owns the knowledge. It consumes Lore's published contract (ADR-063) and never
engine internals. It writes back **only** by proposing `## Verified By` links in
a human-reviewed pull request (ADR-065), never directly into the corpus. No
model enters Lore's engine; the agent runtime lives in this sibling product,
exactly the Wayfinder precedent (ADR-069, ADR-035, ADR-002). The boundary in one
line: **Lore records and reports verification; Proofkeeper produces and runs the
evidence.**

The write-back introduces a new typed relationship — a `verified-by` /
`verifies` edge — to the relationship registry (ADR-055) and the graph export
(ADR-074). That edge is a prerequisite for the write-back and is sequenced in the
`proofkeeper-autonomous-verification` roadmap, not assumed to exist.

### Open-core split and the commercial tier

Following ADR-012, the free, local, open-source surface is the agent, the
session→test compiler, the local runner, and the "which capabilities are
unverified?" coverage report. The paid tier is **Proofkeeper Cloud** — a
Lore-branded hosted *tier*, not a fourth standalone brand — comprising a
VM-fabric runner (real operating systems the team does not own), the
flake-elimination / fidelity *guarantee*, and org-scale verification governance
(multi-repo coverage aggregation and audit reporting). This is consistent with
`commercial-layer-positioning`, which prefers a Lore-branded tier over a fourth
name; the brief's "separate hosted brand" framing is recorded under Alternatives
as considered and not taken. Evocative tier vocabulary (e.g. "Crucible") may be
used only as a sub-tier label under the Lore / Proofkeeper brand, never as a bare
standalone name, given the direct dev-tools clash with Atlassian Crucible.

## Consequences

### Positive

- The family gains a role-noun that fills the unclaimed "tests-and-certifies"
  axis without colliding with the guard/watch roles of Gatekeeper and
  Watchkeeper, and `proofkeeper` is clear on PyPI, npm, and GitHub at the bare
  name (cleared further by the `lore-` prefix and the `itsthelore` org).
- Lore's no-inference identity survives intact: the agent runtime is a sibling
  product, reinforcing ADR-035 / ADR-069 rather than eroding it.
- The contract-consumer boundary and the human-reviewed write-back keep Lore the
  system of record and the human the trust boundary (ADR-065, ADR-024).
- The commercial tier maps onto ADR-012's reserved org-scale value without
  minting a fourth brand to explain.

### Negative

- A fourth installable product to position and maintain alongside the engine,
  Lore, and Wayfinder, with its own repo, release cadence, and runtime surface
  (browsers, runners) the engine deliberately avoids.
- The `## Verified By` write-back cannot ship until the new relationship edge
  lands in the registry and graph export — a dependency on engine work.

### Risks

- Scope drift toward a general-purpose agent runtime or codegen, forfeiting the
  determinism and open-core trust that justify the boundary. Mitigation: the
  scope is fixed to verification here and in the roadmap's Non-Goals, per the
  Wayfinder / commercial-layer discipline boundary.
- Brand confusion with Epic's "Lore" VCS. Mitigation: the distinctive role-noun
  name and the `itsthelore` handle disambiguate; "Lore Proofkeeper" is used where
  the parent brand alone would be ambiguous.

## Status

Proposed

## Category

Product

## Alternatives Considered

### An independent brand (the Wayfinder model)

Give the product its own un-prefixed brand with no `lore-` tie.

#### Disadvantages

- Independence is earned only by zero runtime dependency on Lore (ADR-069).
  Proofkeeper reads Lore's contract and writes back into the corpus — the exact
  coupling that disqualifies independence. Rejected.

### A flat, literal name (Verifier / the `lore-verify` working title)

Name it after the act it performs.

#### Disadvantages

- A generic feature-noun breaks the family's evocative role-noun pattern,
  collides with existing testing tools (Verify / VerifyTests), and doubles down
  on the weak working title. Rejected for distinctiveness and family fit.

### A name on the guard / watch axis (Sentinel, Warden)

Reuse a custodial guarding metaphor.

#### Disadvantages

- These semantically overlap Watchkeeper and Gatekeeper — this product produces
  proof, it does not stand guard — and both are trademark-saturated in the
  dev-tools and security space (HashiCorp / Microsoft Sentinel; multiple
  "Warden" products). Rejected.

### A separate hosted brand for the commercial tier

Launch the VM-fabric runner / governance tier under its own fourth brand.

#### Disadvantages

- `commercial-layer-positioning` and ADR-012 prefer a Lore-branded hosted tier,
  not a fourth name, to contain brand-explanation load; and every evocative
  candidate (Crucible, Proving Ground, Foundry, Bastion, Tribunal) is
  trademark-contested in an adjacent dev/test/security class — Tribunal is even
  taken by a same-niche agent-QA rival. Rejected in favour of **Proofkeeper
  Cloud** as a Lore-branded tier.

## Related Decisions

- adr-068
- adr-069
- adr-073
- adr-012
- adr-049
- adr-065
- adr-035
- adr-002

## Related Roadmaps

- proofkeeper-autonomous-verification
- commercial-layer-positioning
