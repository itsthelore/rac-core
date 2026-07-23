---
schema_version: 1
id: RAC-KV5DJYE5FGH0
type: decision
tags: [sdk, api, architecture, packaging]
---
# ADR-062: The Python SDK's Public Surface Is `rac.__all__`

## Context

RAC has always been "agent-ready architecture" (ADR-008): pure analysis lives
in `rac.core`, reusable capabilities behind the service gate in `rac.services`,
and thin interfaces (CLI, MCP, Explorer) on top, with "easy SDK support" named
as an explicit goal. ADR-015 reinforces this — build the consumer-facing service
first, then point the interface at it.

The capability to consume RAC as a library already exists: services return typed
dataclasses with a stable `to_dict()` JSON contract (ADR-007), and the package
ships src-layout with optional `explorer` / `ingest*` extras. What was missing is
a *sealed, discoverable* surface. Before this decision, `import rac` exposed only
`__version__`; a programmatic consumer had to deep-import private module paths
(`from rac.services.review import build_review`), every service exception
inherited `Exception` directly with no common root, and nothing said which names
were public and stable versus internal and free to change.

Two distinct questions had to be answered: *what is the public API* (so consumers
and maintainers share one boundary), and *how stable is it* (what a consumer may
rely on). The first is decidable now; the second depends on what a future `1.0`
will mean, which is not yet settled.

## Decision

The RAC Python SDK's public surface is exactly the set of names exported in
`rac.__all__`. Three rules pin it:

1. **One flat namespace.** Everything a consumer is expected to use is importable
   directly from the top-level package — `from rac import build_review,
   validate_directory, RACError`. `rac.services.__all__` mirrors the
   service-layer subset. Anything not listed in `rac.__all__` (modules under
   `rac.core`, `rac.cli`, the output renderers, helper functions) is internal and
   may change without notice.

2. **One exception root.** Every error a public SDK function raises derives from
   `rac.errors.RACError`, so a consumer can catch the whole family with a single
   `except RACError`. Concrete subclasses keep their names and messages and live
   beside the service that raises them; new service errors inherit from `RACError`
   rather than `Exception`.

3. **Additive results.** SDK result objects keep the `to_dict()` JSON contract and
   evolve additively under ADR-007 — fields are added, never removed or
   repurposed, and `schema_version` gates any breaking shape change.

The meaning of `1.0` — whether it freezes the surface, and whether semantic
versioning then governs breaking changes — is **explicitly deferred** and is not
decided here. Until then RAC is pre-1.0: breaking changes to `rac.__all__` are
permitted but must be called out in the release that makes them. This ADR
establishes *what the public surface is*, not a stability pledge over it.

## Consequences

Consumers get a single, documented import boundary and one exception to catch;
maintainers get a clear line between public and internal, so refactors inside
`rac.core` or a service's private helpers are free as long as `rac.__all__` and
the result contracts hold. The exception re-rooting is mechanical and backward
compatible — `RACError` is an `Exception` subclass, so existing `except` clauses
that name a concrete error keep working.

Trade-offs: re-exporting the service surface at the top level makes `import rac`
import the service tree eagerly (a small import-time cost, acceptable for a
library), and the public list is now a maintained artifact — adding a capability
means deciding, deliberately, whether it belongs in `rac.__all__`. Leaving `1.0`
semantics open is itself a trade-off: consumers cannot yet assume a frozen API,
which is the honest position for a pre-1.0 project and avoids a premature pledge.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

- **Leave consumers to deep-import private module paths.** The status quo.
  Rejected: it couples consumers to internal layout, so no refactor is safe and
  there is no public/internal boundary at all.
- **Export every service function and result class.** Rejected: a maximal surface
  is as hard to keep stable as no boundary — the public list should be the
  curated capabilities a consumer needs, not the entire service tree.
- **Pledge semver and freeze the API now (declare 1.0).** Rejected: RAC is pre-1.0
  and still evolving its artifact families; committing to a frozen surface before
  the SDK has real consumers would force either churn or stagnation. The pledge is
  deferred to whenever `1.0` is defined.
- **Keep exceptions rooted at `Exception`.** Rejected: without a common root a
  consumer must import and enumerate every service's exception types to handle
  RAC failures generically, which defeats a usable SDK.

## Related Decisions

- adr-007
- adr-008
- adr-015

## Related Roadmaps

- v0.20.0-python-sdk-foundation
