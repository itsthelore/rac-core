---
schema_version: 1
id: RAC-KV3MG0SDPPWC
type: design
tags: [lifecycle, status, enforcement]
---
# Design: Generalized Lifecycle Status Across Artifact Types

## Context

Lifecycle `status` is decision-only today. The decision spec declares
`metadata={"status": ("Proposed", "Accepted", "Superseded", "Deprecated")}`,
canonicalised from a `## Status` body section (ADR-025) and validated by
`canonical_value`. The other four types declare no status enum.

Two pressures make this a gap rather than a choice:

- **Enforcement is half-covered.** The v0.14.1 status-consistency rule
  (`rac-cross-artifact-enforcement` REQ-003) flags a live artifact that references
  a *retired decision*, but a retired *requirement*, *design*, *roadmap*, or
  *prompt* is invisible to it. "Nothing points at a superseded artifact" only
  holds for one of five types.
- **The corpus already does it informally.** An audit of `rac/` shows
  requirements using `Proposed`/`Accepted` as prose (20 Proposed, 1 Accepted, 1
  free-form, 19 with no `## Status`), roadmaps using `Planned` (39 Planned, 1
  `Considered (unscheduled)`, 13 with none), and prompts/designs using nothing.
  The convention exists; it is just unvalidated and inconsistent.

The mechanism to close the gap already exists and is generic — `ArtifactSpec.metadata`,
`canonical_value`, and `_validate` work for any type. What is missing is the
*model*: which states each type has, which of them mean "retired," and how the
enforcement rule reads them — all without crossing ADR-017 (RAC manages
knowledge, not work).

## User Need

A reader, an agent over MCP, and CI all need to know, for **any** artifact, whether
it is current or retired — so that:

- a maintainer is warned when a live requirement, design, or roadmap still points
  at superseded knowledge, not only when a decision does;
- an agent retrieving context can tell a current artifact from a replaced one;
- `rac` can report drift uniformly instead of decision-only.

The need is *knowledge lifecycle* ("is this artifact still the team's current
position?"), explicitly not *work status* ("is someone building it?").

## Design

### 1. Per-type status enums on a shared spine

Each `ArtifactSpec` declares its own `metadata["status"]` enum. The vocabularies
differ because the lifecycles differ, but they share a spine —
`Proposed → live → retired` — so a single notion of "retired" generalises.

| Type | Live states | Retired states |
| --- | --- | --- |
| decision | `Proposed`, `Accepted` | `Superseded`, `Deprecated` |
| requirement | `Proposed`, `Accepted` | `Superseded`, `Deprecated` |
| design | `Proposed`, `Accepted` | `Superseded`, `Deprecated` |
| prompt | `Active` | `Deprecated` |
| roadmap | `Planned` | `Superseded`, `Abandoned` |

Decisions are unchanged. The deliberately excluded states are the work/delivery
ones — `In Progress`, `In Review`, `Blocked`, `Done`, `Shipped`, `Assigned` — which
would pull RAC into project management (ADR-017). "Retired" means *replaced or no
longer endorsed*, never *finished*.

### 2. A declared "retired" set per spec

The status enum alone does not say which values are terminal. Each spec gains a
small, explicit retired-set (e.g. `retired_status={"Superseded", "Deprecated"}`),
a subset of its `metadata["status"]`. This is the single source of truth the
enforcement rule reads, so "retired" is never inferred from a string convention.

### 3. Status stays an optional, validated `## Status` section

Status remains a Markdown body section (ADR-025), not frontmatter. It stays
**optional** and **validated-if-present** — exactly the decision contract today —
so the 30-plus artifacts with no status keep validating, and only a *malformed*
status (a value outside the type's enum) is an error. This keeps migration
friction near zero.

### 4. Generalized status-consistency

The v0.14.1 rule changes from decision-specific to type-generic:
`_is_retired_decision(product, spec)` becomes `_is_retired_artifact(product, spec)`,
which reads the first `## Status` line and tests it against `spec.retired_status`.
Everything else in the rule is unchanged: the `supersedes` exception, the
retired-source exemption, and the "uniquely-resolved, non-self" guard all still
hold. The result: a live artifact of any type that references *any* retired
artifact is reported as `relationship-target-superseded`.

### 5. Migration

- Normalise the two free-form values (`Considered (unscheduled)`,
  `Proposed — drafted to open the discussion…`) to enum values, or add the values
  to the enums if they are wanted.
- Backfilling the ~32 status-less artifacts is optional (status stays optional);
  it can be done lazily as artifacts are touched.
- `rac new` templates for requirement/roadmap/design/prompt MAY gain a `## Status`
  section seeded with the type's first live state, so new artifacts adopt it.

## Constraints

- **ADR-017 (knowledge, not work).** Status captures knowledge currency only.
  No work/delivery/assignment states, no dates, no owners-as-workflow. This is the
  binding constraint and the design's main risk surface.
- **ADR-025 (hybrid metadata).** Status stays a `## Status` body section, never
  frontmatter.
- **ADR-007 (contract stability).** Additive: the decision status enum and its
  validation are unchanged; new enums are added; status stays optional. The
  `relationship-target-superseded` code and shape are unchanged — only its reach
  widens.
- **Spec-driven (no per-type branching).** New behaviour comes from data on each
  `ArtifactSpec`, not from `if artifact_type == ...` in the rule.
- **Determinism (ADR-002).** Same corpus state, same findings.

## Rationale

Per-type enums beat one shared vocabulary because the lifecycles genuinely differ
— a roadmap is `Planned`, not `Accepted`; a prompt is `Active`, not `Proposed`.
A shared *retired-classification* on top of them is what the enforcement rule
needs, so the graph guarantee generalises without flattening the vocabularies.
Keeping status optional preserves ADR-010's spirit (not everything must be fully
specified) and avoids a disruptive backfill. Reusing the existing
metadata/`canonical_value` machinery means the change is mostly data plus a
one-line predicate swap in the rule.

## Alternatives

- **One shared status vocabulary for all types.** Rejected: forces unnatural
  values (a roadmap that is "Accepted"?) and erases real lifecycle differences.
- **Status in frontmatter.** Rejected: contradicts ADR-025 (status is a body
  section) and reopens the conflict-detection problem.
- **Keep status decision-only (status quo).** Rejected: leaves the enforcement
  guarantee covering one of five types — the gap this design closes.
- **Make status required.** Rejected: forces a backfill of 30-plus artifacts and
  fights ADR-010; optional-but-validated delivers the value without the friction.
- **Infer "retired" from a hard-coded string set in the rule.** Rejected: a
  per-spec `retired_status` keeps the model declarative and spec-driven.

## Accessibility

Status values stay human-readable words in plain Markdown (no codes or colour
dependence), legible in any text editor and in `rac inspect`/review output —
consistent with RAC's viewer-agnostic, plain-text model (ADR-014).

## Style Guidance

Follow the existing decision convention exactly: a `## Status` section whose first
non-empty line is one enum value, title-cased. New per-type enums reuse the
decision spelling where a value is shared (`Proposed`, `Accepted`, `Superseded`,
`Deprecated`).

## Open Questions

Resolved by ADR-051: roadmaps are **in** the model (`Planned → Superseded /
Abandoned` as a knowledge lifecycle, delivery states excluded), and the
"status is knowledge lifecycle, never work status" boundary is ratified by that
ADR rather than left to this design. Remaining:

- **Do requirements/designs need a "delivered/met" state?** It is the most useful
  and the most ADR-017-dangerous addition; the table above omits it deliberately.
- **Backfill now or lazily?** And should the four templates gain a seeded
  `## Status` section?
- **Version fence.** Which release carries this (a v0.14.2 enforcement follow-on,
  or its own series)?

## Related Requirements

- rac-cross-artifact-enforcement

## Related Decisions

- adr-051
- adr-049
- adr-017
- adr-025
- adr-016
- adr-007
