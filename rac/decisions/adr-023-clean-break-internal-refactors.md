---
schema_version: 1
id: RAC-KTQ63DRPK57V
type: decision
---
# ADR-023: Clean-Break Internal Refactors

## Status

Accepted

## Context

RAC's Python package is organized into layers under `src/rac/`:

```text
rac/
  core/      domain and specification primitives
  services/  repository and artifact capabilities
  output/    human, JSON, and template rendering
  explorer/  consumer boundary (intentionally empty today)
```

This layout is the result of an earlier refactor that moved logic out of flat
top-level modules (`rac.models`, `rac.parser`, `rac.validate`, `rac.artifacts`,
`rac.classification`, `rac.relationships`, ...) into the layered packages above.

That refactor was executed as a **clean break**: the old module paths were removed
outright and every importer was rewired in the same change. An audit of the current
tree confirms the practice held:

- No legacy flat modules remain (`src/rac/` contains only `__init__.py` and `cli.py`).
- The old names are unimportable today — `rac.models`, `rac.parser`, `rac.relationships`
  and their peers all raise `ModuleNotFoundError`.
- `core/__init__.py` and `services/__init__.py` carry no re-exports; every internal
  importer names the canonical module that *defines* the symbol it uses.
- The only re-export in the package is `rac.output`, which is a documented **facade**
  for the renderers — an intended public surface, not a legacy stub.

However, this convention was never written down. During the v0.7.5 work to promote
`artifact_identifier` from `services/relationships.py` to a new `core/identity.py`, a
backward-compatibility shim (a re-export left behind in `relationships`) was proposed
before being rejected. The absence of a recorded decision invites this drift to recur
and slowly reintroduce dual ownership and dead import paths.

A second, related observation: several module docstrings still reference the dead flat
paths. These are stale documentation, not functional shims, but they show how easily
the prose lags a clean break.

## Decision

Internal refactors that relocate or rename a Python module or symbol within the `rac`
package shall be **clean breaks**:

- All importers (production code and tests) are updated to the new canonical path in
  the same change.
- No backward-compatibility shim, re-export stub, or legacy module alias is left
  behind to preserve an old `rac.*` import path.
- No test pins or asserts a deprecated import path; tests import from the canonical
  owner.

This decision governs **internal Python import paths only**. It does not relax RAC's
public contracts:

- The CLI command surface (ADR-005) and JSON output (ADR-007) remain stable contracts
  and are explicitly out of scope here.
- An intentional, documented **facade** (such as `rac.output`, which aggregates the
  renderers as the output layer's public surface) is permitted. A facade is a designed
  front door for symbols whose canonical home is elsewhere — it is not a legacy shim,
  and it must be declared as such in the module that provides it.

## Principles

### Principle 1 — Single Canonical Owner

Every symbol has exactly one defining module. Importers name that module directly.
A symbol is never reachable through two supported paths.

### Principle 2 — Move Callers, Not Compatibility Layers

When a symbol moves, the cost is paid once by updating its callers — not amortized
forever by maintaining a parallel access path that future readers must learn to ignore.

### Principle 3 — Facades Are Explicit, Not Accidental

A re-export is acceptable only when it is a deliberate, documented public surface for a
layer (e.g. `rac.output`). It is never acceptable as the residue of a move.

### Principle 4 — Internal Imports Are Not a Public Contract

RAC's public contracts are the CLI and the JSON outputs. Python import paths under
`rac.*` carry no stability guarantee, so a clean break breaks nothing that was promised.

### Principle 5 — Documentation Follows the Code

A clean break updates the docstrings and comments that referenced the old path in the
same change, so the prose never outlives the module it describes.

## Consequences

### Positive

- The import graph stays acyclic and legible: one owner per symbol, no aliases.
- No dead code accretes; there is nothing to later "clean up" or accidentally depend on.
- Layer ownership stays sharp — a symbol's home reflects its true responsibility
  (e.g. identity is a core concept, not a relationship detail).
- Refactors are honest: `git log` shows the move and its callers in one change.

### Negative

- A larger diff at refactor time, since every caller changes at once.
- Any external code importing internal `rac.*` paths will break without a deprecation
  window. This is accepted: those paths were never a supported contract.
- Contributors must update tests and docstrings as part of the move, not afterward.

## Alternatives Considered

### Keep Backward-Compatibility Shims

Leave a re-export at the old path after moving a symbol.

#### Pros

- External importers of internal paths keep working.
- Smaller immediate diff.

#### Cons

- Creates two sources of truth and blurs ownership.
- Accretes dead paths that readers must learn to ignore.
- Contradicts the project's own demonstrated history (the flat-module split shipped
  with no shims).

Rejected.

### Deprecation Period With Warnings

Keep the old path but emit a `DeprecationWarning`, removing it in a later release.

#### Pros

- Gives downstream importers time to migrate.

#### Cons

- Appropriate for public APIs, not internal import paths that carry no guarantee.
- Adds lifecycle bookkeeping for a contract that does not exist.

Rejected.

### Re-export From Package `__init__`

Surface moved symbols from `rac.core` / `rac.services` package roots.

#### Pros

- Shortens import statements.

#### Cons

- Dilutes the single-owner rule; `__init__` becomes an implicit, ever-growing alias
  table. The existing empty `__init__` modules are deliberate.

Rejected.

## Relationship to Other ADRs

### ADR-005 CLI First

Defines the command surface as a stable, user-facing contract — the public boundary
this ADR contrasts with internal import paths.

### ADR-007 JSON Contract Stability

JSON output is a versioned public contract that *must* stay stable. This ADR is its
complement: internal Python imports are explicitly *not* such a contract.

### ADR-008 Agent-Ready Architecture

Stable service APIs are consumed by the CLI, Explorer, and future integrations. Those
consumers depend on the canonical module paths, which clean breaks keep coherent.

### ADR-015 Consumers Before Interfaces

Explorer consumes RAC service APIs rather than reimplementing them. A single canonical
owner per capability (e.g. `core.identity` for artifact identity) is what makes those
APIs safe to consume.

## Success Measures

Evidence that this decision is working:

- Each `rac.*` symbol is importable from exactly one path.
- No re-export exists except documented layer facades.
- Refactor commits move a symbol and its callers together, with docstrings updated.
- No test references a deprecated import path.
- New contributors learn one home per concept, not a current path and a legacy path.

## Review Date

Review before v1.0.0, or if RAC begins publishing a supported Python API (as opposed to
its CLI and JSON contracts), which would warrant a deliberate deprecation policy.
