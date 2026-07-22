---
schema_version: 1
id: RAC-KV3MPPW4XGFP
type: decision
tags: [lifecycle, status, enforcement]
---
# ADR-051: Lifecycle Status Is Knowledge Lifecycle, Generalized Across All Artifact Types

## Status

Proposed

## Category

Architecture

## Context

Lifecycle `status` is decision-only today: the decision spec declares
`metadata={"status": ("Proposed", "Accepted", "Superseded", "Deprecated")}`,
validated from a `## Status` body section; the other four types declare no enum.
Two consequences follow. The v0.14.1 status-consistency rule
(`rac-cross-artifact-enforcement` REQ-003) can only flag references to retired
*decisions*, so "nothing live points at a superseded artifact" holds for one of
five types. And the corpus already uses status informally and inconsistently —
requirements as prose `Proposed`/`Accepted`, roadmaps as `Planned`, prompts and
designs not at all — so the convention exists without a contract.

The design `generalized-lifecycle-status` works out the *how*. This ADR records
the *decision* and, critically, the boundary that keeps it from drifting into the
project-management modelling ADR-017 rejects.

## Decision

1. **Generalize lifecycle status to all five artifact types**, declared per-type
   via `ArtifactSpec.metadata["status"]` on a shared `Proposed → live → retired`
   spine. Decisions are unchanged. The enums are:

   | Type | Live | Retired |
   | --- | --- | --- |
   | decision | `Proposed`, `Accepted` | `Superseded`, `Deprecated` |
   | requirement | `Proposed`, `Accepted` | `Superseded`, `Deprecated` |
   | design | `Proposed`, `Accepted` | `Superseded`, `Deprecated` |
   | prompt | `Active` | `Deprecated` |
   | roadmap | `Planned` | `Superseded`, `Abandoned` |

2. **Status means knowledge lifecycle, never work status (binding, interprets
   ADR-017).** It answers "is this the team's current position, or has it been
   replaced?" — not "is someone building it?". The states `In Progress`,
   `In Review`, `Blocked`, `Done`, `Shipped`, `Assigned`, and any date or
   workflow-owner field are out of scope and MUST NOT be added as status. For
   roadmaps specifically, `Planned` denotes current intent and `Superseded`/
   `Abandoned` denote replaced or dropped intent — knowledge states, not delivery
   tracking; per-milestone delivery progress stays out.

3. **Each spec declares a `retired_status` set** (a subset of its status enum) as
   the single source of truth for terminality. The status-consistency rule
   generalizes from `_is_retired_decision` to `_is_retired_artifact`, reading
   `spec.retired_status`, so a live artifact of any type that references any
   retired artifact is reported `relationship-target-superseded`. The `supersedes`
   exception and the retired-source exemption are unchanged.

4. **Status stays an optional, validated `## Status` body section** (ADR-025): not
   frontmatter, validated only when present, so the artifacts with no status keep
   validating and only a value outside the type's enum is an error.

5. **Additive (ADR-007).** The decision status enum, the
   `relationship-target-superseded` code, and its shape are unchanged; the rule's
   reach widens. The two existing free-form status values are normalized to enum
   values as part of delivery.

## Consequences

### Positive

- The "nothing live points at a retired artifact" guarantee covers all five types,
  not just decisions.
- Agents and `rac` can tell a current artifact from a replaced one uniformly.
- The change is mostly declarative data on each `ArtifactSpec` plus a one-line
  predicate swap, reusing existing validation machinery — no per-type branching.

### Negative

- Five lifecycles to maintain, each a place the ADR-017 boundary must be guarded
  on every future change.
- A small migration: two free-form status values to normalize; optional backfill
  of status-less artifacts.

### Neutral

- Status remains optional; artifacts without a `## Status` section stay valid.
- Templates for the four types MAY later seed a `## Status` section; not required.

## Alternatives Considered

- **One shared status vocabulary for all types.** Rejected: a roadmap is `Planned`,
  not `Accepted`; forcing one vocabulary erases real lifecycle differences.
- **Exclude roadmaps as too work-adjacent.** Considered seriously (the sharpest
  ADR-017 case) and rejected: `Planned → Superseded/Abandoned` is a defensible
  *knowledge* lifecycle, and a uniform model across all five types is worth more
  than carving out one. The boundary is held by excluding delivery states, not by
  excluding the type.
- **Status in frontmatter.** Rejected: contradicts ADR-025.
- **Keep status decision-only.** Rejected: that is the enforcement gap.
- **Make status required.** Rejected: forces a disruptive backfill and fights
  ADR-010; optional-but-validated delivers the value without it.

## Related Decisions

- ADR-017
- ADR-025
- ADR-049
- ADR-007
- ADR-016

## Related Requirements

- rac-cross-artifact-enforcement

## Related Designs

- generalized-lifecycle-status
