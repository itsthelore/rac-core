---
schema_version: 1
id: RAC-KV3P8MSKB276
type: decision
tags: [okf, interop, schema, enforcement]
---
# ADR-052: rac-core Is the Code-Defined OKF-Superset Envelope, Conformance Enforced at Write Time

## Status

Proposed

## Category

Architecture

## Context

A hardening brief proposed founding RAC's extensibility on an authoritative
JSON Schema 2020-12 `rac-core` (every type composing it via `allOf`), with
`type` and `title` as required frontmatter, stored timestamps, an OKF
conformance gate over every file, and a codemod across the corpus. Taken
literally that is a large, partly-destructive change — and it collides with
decisions RAC has already recorded:

- **Mandatory `type`** contradicts ADR-010 (untyped documents are legitimate and
  deliberately skipped).
- **Frontmatter `title`/`description`** contradict ADR-025 (title is H1-derived;
  product reasoning stays in the body).
- **Stored `timestamp`** contradicts ADR-045 (recency is git-derived, never
  stored in source).
- **A full OKF superset + codemod** is exactly what ADR-050 considered and
  rejected, adopting only the conflict-free `tags` field.
- **JSON Schema files as the source of truth** cuts against ADR-049, which names
  the per-type schema *table stakes* and the cross-artifact graph the product —
  and against the working reality that the frontmatter envelope is already
  defined in code (`core/frontmatter.py`, `core/metadata.py`) and exercised by
  the full test suite.

What is *genuinely* missing is small. ADR-048 requires every RAC repository to
be a conformant OKF v0.1 bundle, but conformance was only ever a side-effect of
`rac export --okf`; nothing failed CI when the corpus could not produce a
conformant bundle. This decision records how RAC closes that gap without
adopting the conflicting machinery above.

## Decision

1. **`rac-core` is the existing code-defined frontmatter envelope**, not a new
   JSON Schema artifact. The reserved fields — `schema_version`, `id`, `type`,
   `relationships`, `tags` (ADR-025, ADR-050) — are a strict superset of OKF's
   reserved set, validated in `core/frontmatter.py`. "Validates against rac-core"
   means the envelope, *when present*, parses clean; legacy artifacts without
   frontmatter stay valid (ADR-025) and untyped documents stay legitimate
   (ADR-010). No `allOf` composition, no JSON Schema dialect, no new dependency.

2. **OKF v0.1 conformance becomes a write-time gate** in `rac validate`
   (`services/okf_conformance.py`, Layer 0). Over a corpus it checks, per typed
   artifact, that the `type` maps to an OKF type and that no typed artifact
   occupies a reserved filename (`index.md`/`log.md`). Untyped documents are
   excluded (ADR-010). Referential integrity ("links resolve") remains owned by
   `rac relationships --validate` and is not duplicated here.

3. **The RAC→OKF type mapping and reserved filenames live once in `core/okf.py`**
   and are shared by the bundle export and the conformance check (ADR-002: one
   deterministic source of truth).

4. **No mandatory fields, no codemod, no stored dates.** ADR-010, ADR-025, and
   ADR-045 stand unchanged. The conformance result is additive to the directory
   `validate` JSON contract (ADR-007); no `schema_version` bump.

5. **Custom JSON Schema dialects/vocabularies remain deferred** (post-PMF); if a
   design partner ever needs repo-local custom types, schema composition over
   this code-defined core is the intended path and will be recorded as its own
   ADR — never a silent edit to an accepted decision.

## Consequences

### Positive

- OKF conformance (ADR-048) is now enforced deterministically in CI, not merely
  produced on export — consistent with ADR-049's "enforcement is the product".
- The change is additive and small: a new check plus a shared constants module,
  reusing existing parsing and the directory-validate surface. Every recorded
  decision is preserved; no artifact changes shape.
- Future type additions cannot silently fall out of the OKF bundle — an unmapped
  type fails conformance with a file-named diagnostic.

### Negative

- rac-core is documented in code and ADRs rather than a publishable JSON Schema
  file, so external JSON Schema tooling cannot consume it directly today. A
  derived schema export is left as a future, pull-based option.

### Neutral

- The conformance check overlaps in spirit with `rac export --okf`'s exclusion
  of untyped files; the export stays the derived view, the check the write-time
  gate.

## Alternatives Considered

- **Authoritative JSON Schema 2020-12 `rac-core` + `allOf`, mandatory
  `type`/`title`, stored timestamps, codemod (the brief's literal path).**
  Rejected: conflicts with ADR-010, ADR-025, ADR-045, ADR-050, and the
  table-stakes posture of ADR-049; large and partly destructive for marginal
  gain over the code-defined envelope RAC already enforces.
- **A derived `rac-core` JSON Schema generated from the code spec (like the OKF
  export).** Deferred, not rejected: useful for external tooling, but not
  required to close the conformance gap; recordable later if demand appears.
- **Leave OKF conformance as an export-only side-effect.** Rejected: ADR-048
  requires conformance and ADR-049 requires it be enforced; an unenforced
  guarantee drifts.

## Related Decisions

- ADR-048
- ADR-049
- ADR-050
- ADR-025
- ADR-010
- ADR-045
- ADR-007

## Related Requirements

- rac-okf-carrier-profile
- rac-cross-artifact-enforcement
