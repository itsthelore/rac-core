---
schema_version: 1
id: RAC-KV3JY2CHGGRY
type: decision
tags: [okf, interop, metadata]
---
# ADR-050: OKF-Reserved Frontmatter — Adopt tags, Derive Timestamps from Git

## Status

Proposed

## Category

Technical

## Context

OKF reserves a small set of descriptive front-matter fields: `type`, `title`,
`description`, `tags`, and a `timestamp`. Making a RAC repository a richer OKF
bundle invites adopting them as a superset on top of RAC's strict `id`/`type`/
typed relationships. But three of the five collide with decisions RAC has already
recorded, so this is not the near-zero change it first appears:

- **`type` (made mandatory on every file)** conflicts with ADR-010 (Documents Are
  Not Artifacts): untyped documents are legitimate and deliberately skipped. The
  15 currently-unclassified files are real planning docs; forcing a type would
  make them validated artifacts that then fail for missing sections. OKF-bundle
  validity already comes from `rac export --okf`, which excludes documents.
- **`created`/`updated` stored in frontmatter** conflicts with ADR-045 (recency is
  derived from git, not stored): a hand-maintained date drifts and pushes toward
  the work-status modelling ADR-017 rejects.
- **`title`/`description` in frontmatter** collide with RAC's H1-derived title and
  body conventions (ADR-025), requiring conflict-detection rules for marginal gain.

Only `tags` is free of conflict — and ADR-025 already reserved it ("Frontmatter,
if later supported"). This decision adopts the conflict-free subset and resolves
the timestamp tension by deriving timestamps in the *export* rather than storing
them in the source.

## Decision

1. **Adopt `tags`** as an optional frontmatter field: a list of non-empty string
   labels, validated for shape only, never a source of product reasoning. No
   `schema_version` bump — this matches how `id`, `type`, and `relationships` were
   added as optional fields at `schema_version: 1`; the addition is additive and
   backward-compatible.
2. **Derive OKF timestamps from git.** `rac export --okf` projects `created`
   (first commit) and `updated` (last commit) into each bundle artifact's front
   matter, derived from git history (ADR-045). They are never stored in the source
   frontmatter, so the source stays date-free and the bundle is fully timestamped
   for OKF consumers.
3. **Do not adopt `title`/`description` in frontmatter** (they conflict with the
   H1 title and body conventions; revisit only if OKF `description` interop
   demands it).
4. **Do not make `type` mandatory** at the source (ADR-010 stands; documents are
   legitimate). OKF-bundle validity is delivered by `rac export --okf`, which
   already excludes untyped documents.

## Consequences

### Positive

- RAC artifacts gain OKF's `tags` for agent filtering and sorting, and the OKF
  bundle carries `type` + `tags` + `created`/`updated` — four of OKF's five
  reserved fields — with no conflict against any recorded decision.
- The source corpus stays free of drift-prone dates (ADR-045) and free of forced
  typing (ADR-010); both guarantees are preserved.

### Negative

- The OKF bundle's `title` still derives from the H1 (no frontmatter `title`), and
  `description` is absent — slightly less than a full OKF superset.
- The OKF export does two git lookups per artifact (first and last commit), paid
  only on `rac export --okf`, not on the validation or cadence paths.

### Neutral

- `tags` are descriptive only; they do not participate in classification,
  relationships, or review scoring.

## Alternatives Considered

- **Full OKF superset (add `title`/`description`, mandatory `type`, frontmatter
  timestamps).** Rejected: conflicts with ADR-010, ADR-045, and the ADR-025 title
  conventions; high cost for marginal interop gain.
- **Store `created`/`updated` in frontmatter.** Rejected: contradicts ADR-045;
  deriving them in the export gives OKF consumers the same data without the drift.
- **A `schema_version` bump gating the new field.** Rejected: inconsistent with how
  RAC has added optional fields, and unnecessary for an additive optional field.

## Related Decisions

- ADR-025
- ADR-048
- ADR-045
- ADR-010
- ADR-007
- ADR-017

## Related Requirements

- rac-okf-carrier-profile
