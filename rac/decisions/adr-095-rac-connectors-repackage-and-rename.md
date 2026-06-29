---
schema_version: 1
id: RAC-KW8ZTVEQJ366
type: decision
tags: [structure, org, connectors, distribution, contract]
---
# ADR-095: rac-connectors Repackage, PyPI Rename, and Outbound Field Rename

## Context

ADR-092 converges the `itsthelore` organisation onto `rac-*` repository slugs,
and the `rac-connectors` roadmap renames `lore-connectors` → `rac-connectors`.
ADR-073 had already consolidated the backend connectors into one repository with a
subdir per backend; ADR-063/ADR-002 fix them as thin consumers of the public
export contract that reimplement no engine internals.

The convergence series is framed as **topology only** — slugs and locations, not
code or contracts. Landing `rac-connectors` surfaced three changes that go beyond
a slug rename and therefore need a recorded decision rather than being folded
silently into a topology move:

1. The Python **distribution and import package** still carried the `lore`
   name (`lore-connectors` / `lore_connectors`), leaving the `rac-*` convergence
   half-applied inside the repo.
2. The **CLI entry point** was `lore-connect`, incoherent with a `rac-connectors`
   distribution.
3. The connectors write an **outbound field** `lore_id` (and a cognee `Lore-Id:`
   header) into external backends; its value is already the canonical `RAC-*`
   artifact id, so the field name and its value disagreed (`lore_id: RAC-…`).

The engine's export contract is unaffected: `rac export` emits `"id"`
(`rac/services/export.py`); the `lore_id`/`rac_id` field is a name the connectors
coin on the way out, mapped from that `id`.

## Decision

Land `rac-connectors` with the `rac-*` naming applied through the package and its
outbound surface, as one distribution.

1. **One distribution, providers as submodules.** The distribution is
   `rac-connectors` (to be registered on PyPI), the import package is
   `rac_connectors`, and each integration stays a submodule under
   `src/rac_connectors/` (`cognee/`, `letta/`, `mem0/`, `neo4j/`, `supermemory/`,
   `zep/`) sharing the core (`base`, `contract`, `records`, `graph`, `cli`). This
   is "subdir per integration" (ADR-092) realised within a single distribution;
   future integrations (e.g. `atlassian/`) join as sibling submodules. A provider
   graduates to its own distribution only via the ADR-092 escape hatch.
2. **CLI entry point** `lore-connect` → `rac-connect`.
3. **Outbound field rename** `lore_id` → `rac_id`, and the cognee header
   `Lore-Id:` → `Rac-Id:`. The value is unchanged (the canonical `RAC-*` id), so
   the field name now agrees with its value. This is a deliberate change to the
   connectors' *outbound* data contract (the records written into Supermemory,
   mem0, zep, letta, cognee), accepted before broad adoption rather than carried
   as a permanent `lore`-named field.
4. **Retained on purpose.** The "Lore" product brand in prose, the `itsthelore`
   org name, and the engine export field `"id"` are unchanged — consistent with
   ADR-036/ADR-039 keeping the Lore brand at the product surface while slugs go
   `rac-*`.

History is preserved across the move (the package directory rename is a tracked
`git mv`; `git log --follow` traces through it).

## Consequences

### Positive

- The `rac-*` scheme is consistent end to end for connectors: repo slug,
  distribution, import package, CLI, and the outbound id field.
- The outbound id field name and value agree (`rac_id: RAC-…`).
- No engine or export-contract change; connectors stay thin contract consumers
  (ADR-063, ADR-002).

### Negative

- A PyPI registration for `rac-connectors` is required, and the old
  `lore-connectors` repo/name must be archived with a redirect.
- The outbound-field rename is a contract break: records already pushed to a
  backend under `lore_id` would need a re-push, and any downstream reader keyed on
  `lore_id` updated. Accepted because it lands before broad adoption.

### Risks

- A backend already holds `lore_id`-keyed records in production. Mitigation: do
  the rename now, ahead of adoption; if such data exists, re-push and update
  readers as a one-time migration.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

### Pure slug rename, keep `lore_connectors` / `lore-connect` / `lore_id`

Rejected: it leaves the `rac-*` convergence half-applied inside the repo and keeps
the field name disagreeing with its `RAC-*` value, deferring the same churn to a
later, post-adoption break.

### Split integrations into separate top-level distributions

Rejected: it fragments the shared core (`base`, `contract`, `records`) across
distributions and contradicts the one-`rac-connectors`-dist intent. A provider can
still graduate later via the ADR-092 escape hatch if it grows independent cadence.

## Related Decisions

- adr-092
- adr-073
- adr-063
- adr-002
- adr-036

## Related Roadmaps

- rac-connectors
- repo-topology-convergence
