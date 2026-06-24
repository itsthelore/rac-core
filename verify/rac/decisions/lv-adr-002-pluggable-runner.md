---
schema_version: 1
id: LV-KVW1HWYTJCFN
type: decision
tags: [architecture, runner, hosting]
---
# LV-ADR-002: The Test Runner Is a Pluggable Interface

## Context

`lore-verify` runs compiled end-to-end tests against targets (dev, production) and
across operating systems. RAC ADR-083 records that hosting is a *separate brand*,
never required for the local path, but that adding it later should be cheap — "a
new backend, not a re-architecture." That property has to be designed in from the
first prototype, or retrofitting it later means rewriting the execution core.

## Decision

The component that executes a compiled test is defined behind a **runner
interface** from day one. A runner takes a compiled test, a resolved target
(`baseURL` + auth strategy), and an OS/browser selection, and returns a result
plus a replayable trace artifact.

- The **local runner** — running Playwright on the developer's machine — ships in
  the open product and is the only runner needed for the local path.
- A **hosted runner** — a VM fabric providing real operating systems the user does
  not own — is a drop-in backend behind the same interface, owned by the separate
  hosted brand (RAC ADR-083, Initiative 6 of `lore-verify-programme`).
- Target resolution and OS/browser selection are **configuration injected into the
  runner**, never compiled into a test, so the same compiled test runs unchanged
  across runners, targets, and operating systems.

## Consequences

Hosting becomes additive: the hosted brand implements one interface rather than
forking the execution core, and the open product never depends on it. The cost is
holding the interface stable as both runners evolve; it is the single seam that
makes the open/hosted split honest.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

- **Hardcode a local runner now, add hosting later.** Rejected: retrofitting an
  abstraction across the execution core is the re-architecture RAC ADR-083 says to
  avoid.
- **Build the hosted runner now.** Rejected: hosting is a separate track and brand
  (RAC ADR-083); the prototype only needs the interface and a local
  implementation.

## Related Decisions

- lv-adr-001-product-identity
