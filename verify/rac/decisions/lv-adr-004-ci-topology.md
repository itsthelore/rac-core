---
schema_version: 1
id: LV-KVW5PYSCSCMM
type: decision
tags: [process, ci, gating]
---
# LV-ADR-004: CI Topology for the verify/ Subproject Inside rac-core

## Context

While `lore-verify` is prototyped in the `verify/` subdirectory of `rac-core`
(LV-ADR-001, RAC ADR-064), its own corpus and suite are **not gated by any CI**.
rac-core's workflows are RAC-only: they run `rac validate rac/`,
`rac relationships rac/ --validate`, and the top-level `tests/` battery, scoped to
the `rac/` and `tests/` paths — a grep of `.github/` for `verify` finds nothing.
Two Accepted process decisions assume a single corpus and a single `tests/` tree:
RAC ADR-027 (CI test topology — per-service batteries globbed from top-level
`tests/`) and RAC ADR-075 (the required pre-merge gate on `main`). Neither covers a
second corpus living in a subdirectory.

The consequence is that the `verify/` corpus and suite **silently rot**: a broken
`LV-` relationship, an invalid LV artifact, or a failing `verify/tests/` test can
land on `main` with no signal — directly defeating LV-ADR-001's claim that
`lore-verify` "dogfoods Lore on itself from day one."

## Decision

While `verify/` lives inside `rac-core` it is gated by its **own CI job**, separate
from the RAC batteries:

- A workflow (or job) keyed to `verify/**` paths runs, on every PR that touches
  `verify/`: `rac validate verify/rac/`, `rac relationships verify/rac/
  --validate`, and the `verify/` suite/lint/types once code exists.
- This job is **part of the ADR-075 required pre-merge gate** for changes under
  `verify/`: a red `verify/` job blocks merge exactly as a red RAC battery does.
  Changes that do not touch `verify/` need not run it (path-filtered), so the RAC
  gate is unaffected when `verify/` is untouched.
- The `verify/tests/` tree is its **own battery**, declared separately from RAC's
  top-level `tests/`. RAC ADR-027's `test_ci_batteries.py` globs only the top-level
  `tests/`, so `verify/tests/` is registered as a distinct battery rather than
  silently sitting outside the topology. (This is recorded as a companion note
  against ADR-027; it does not change ADR-027's RAC batteries.)
- The two corpora stay **separately validated**: RAC CI runs `rac validate rac/`
  and the `verify/` job runs `rac validate verify/rac/`. Neither validates the
  other's corpus (different repository keys, `RAC` vs `LV`).

On extraction to `itsthelore/lore-verify` (RAC ADR-064, programme Initiative 5),
this job becomes that repo's standalone CI and the path filter / companion-battery
arrangement in rac-core is removed.

## Consequences

The `verify/` corpus and suite are gated from the moment the subproject is stood
up, so "dogfoods Lore on itself" is enforced, not aspirational, and a broken LV
artifact cannot reach `main` unseen. The cost is a second CI job and a path-filter
arrangement that is explicitly temporary — it exists only while `verify/` is a
tenant of `rac-core` and is designed to be lifted out cleanly at extraction.

## Status

Accepted

## Category

Process

## Alternatives Considered

- **Fold `verify/rac/` into RAC's existing `rac validate rac/` run.** Rejected: the
  two are separate corpora with different repository keys (`RAC`/`LV`) and separate
  release/extraction lifecycles; validating them together couples what LV-ADR-001
  keeps independent and breaks at extraction.
- **Leave `verify/` ungated until extraction.** Rejected: it lets the LV corpus rot
  on `main` and contradicts the dogfooding claim; the gap the audit found is exactly
  this.
- **Make the `verify/` job a required gate on every PR (no path filter).** Rejected:
  it would run (and could block) the `verify/` battery on unrelated RAC changes;
  path-filtering keeps the gate proportionate.

## Related Decisions

- lv-adr-001-product-identity
