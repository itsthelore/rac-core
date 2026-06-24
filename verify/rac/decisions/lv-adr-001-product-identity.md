---
schema_version: 1
id: LV-KVW1HQNK5RN4
type: decision
tags: [identity, boundary, product]
---
# LV-ADR-001: lore-verify Identity and Boundary

## Context

`lore-verify` is the autonomous-QA consuming product decided in RAC ADR-083
(`RAC-KVW05R49X701`). It gives an agent real developer tools — a browser and a
terminal — to develop against a target, converts the working session into durable
end-to-end tests, runs them across targets and operating systems, and emits
replayable trace artifacts a reviewer can inspect without running anything
locally.

It is prototyped in the `verify/` subdirectory of `rac-core` (RAC ADR-064 safety
contract) and extracted to `itsthelore/lore-verify` once it ships, carrying this
self-contained corpus with it. This decision records what the product is and the
boundary it keeps with Lore, so neither side drifts into the other.

## Decision

`lore-verify` is a **contract consumer of Lore, not an extension of the engine**:

- It learns *what to verify* by reading the published Lore contract — `rac export
  --graph` and the `lore` MCP read tools — never RAC engine internals and never
  the host repo's `.rac/` namespace (RAC ADR-063).
- It writes back *only by proposing* `## Verified By` references in a
  human-reviewed pull request; a human ratifies and merges (RAC ADR-065). It never
  writes a corpus directly.
- It owns all runtime and content — driving the browser/terminal, running tests,
  and producing videos/traces — which RAC deliberately does not (RAC ADR-017,
  ADR-024). Execution lives here; knowledge lives in Lore.
- It is AI-using but credential-agnostic: bring-your-own provider, local models
  supported, no mandatory hosted inference for the local path (RAC ADR-035).
- It is a **clean build** under the `lore-*` brand (RAC ADR-068), a
  contract-dependent companion to Lore — distinct from Wayfinder, which earned an
  independent brand by having zero dependency on RAC.

The boundary, stated once: **Lore records and reports verification; `lore-verify`
produces and runs the evidence.**

## Consequences

The product can be developed and extracted without coupling to the engine, and
Lore stays a deterministic, offline knowledge engine with no test runtime. The
cost is a thin contract seam to maintain on both sides; it is versioned and
additive (RAC ADR-007), and `lore-verify` pins a published major rather than
tracking internals.

## Status

Accepted

## Category

Product

## Alternatives Considered

- **Build verification into `rac-core`.** Rejected by RAC ADR-083 / ADR-017 /
  ADR-024: it would drag a runtime and content into a knowledge engine.
- **Make it an independently-branded product like Wayfinder.** Rejected: unlike
  Wayfinder, `lore-verify` is useless without a Lore corpus to verify, so it stays
  a `lore-*` companion (RAC ADR-068).
- **Fork an existing prototype.** Rejected: a clean build avoids inheriting a
  design that predates this boundary (RAC ADR-083).

## Related Decisions

- lv-adr-002-pluggable-runner
