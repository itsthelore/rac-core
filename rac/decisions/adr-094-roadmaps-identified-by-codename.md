---
schema_version: 1
id: RAC-KW6NQ4Y814N7
type: decision
tags: [process, roadmap, naming, identity]
---
# ADR-094: Roadmaps Are Identified by Stable Codename, Not a vX.Y.Z Scope-Fence

## Context

Roadmap artifacts carried a `vX.Y.Z-<slug>` filename inside a `vX.Y.x-<theme>`
series directory. That numbering was a planning **scope-fence**: ADR-076 records
that "Roadmap `vX.Y.Z` numbers stay as internal scope-fences, decoupled from
release identifiers. They schedule and bound work; they are not releases," and the
session-start prompt distilled it to "Version numbers are scope fences."

Two later decisions emptied the fence:

- **ADR-076** decoupled the number from releases — releases are CalVer
  (`YYYY.MM.N`).
- **ADR-093** decoupled it from execution order — "Ordering is the board's job,
  not the roadmap number's," and it explicitly left "whether to drop the numeric
  scheme entirely … a separate decision, not settled here."

What remained was a fence with nothing to fence: it does not bound a release, does
not order work, and does not identify the artifact (identity is the opaque
frontmatter `id`, ADR-026). It only imposed costs — it implies a sequence that is
fiction, blocks order-independent work, and competes with the bare-codename
convention the `future/` series already uses. This decision retires it.

## Decision

A roadmap is identified by a **stable, human-meaningful codename**, not a
`vX.Y.Z` scope-fence.

1. **Codename is the label.** A roadmap's filename and its series directory use a
   descriptive slug with no version prefix (`rac/roadmaps/repo-topology/rac-ci.md`,
   not `v0.31.x-repo-topology/v0.31.1-rac-ci.md`) — the `future/` convention. The
   H1 title drops the version too (display-only). Single-item series may flatten to
   a flat file.
2. **The codename is not identity.** Per ADR-026 the canonical reference is the
   opaque `id`; the codename is a filename-stem alias. A rename never changes
   identity, so it is graph-neutral when every stem reference is repointed.
3. **Sequence is not in the name.** Ordering lives on the GitHub board (ADR-093);
   lifecycle lives in `## Status` (ADR-061). No `order:` field is added.
4. **Codenames must be globally unique** across the roadmap tree (the filename
   stem is a resolvable alias); they should be self-describing.
5. **History stays versioned.** Achieved/shipped roadmaps and `archive/` keep
   their `vX.Y.Z` names: *versioned = shipped record; codename = live intent.* The
   versioned name on a shipped item is a timestamp of record, not a stale fence.
6. **CalVer and the SemVer tags are unaffected.** Release identity stays
   `YYYY.MM.N` (ADR-076); the immutable `v0.1.0`…`v0.19.0` tags stand. "Version"
   now means the *release* version only.

This amends **ADR-076 as a sibling** (not a status flip — ADR-076 is the live
CalVer authority and flipping it would cascade and wrongly retire CalVer): where
ADR-076 keeps `vX.Y.Z` as a roadmap scope-fence, ADR-094 governs for live
roadmaps. It also reconciles the corpus statements of the old convention: the
session-start prompt line, the `[roadmap:vX.Y.Z]` commit-trailer guidance (live
roadmaps use `[roadmap:<codename>]`), and the scope-fence wording in the
release-versioning requirement; and it closes the question ADR-093 left open.

## Consequences

### Positive

- Live roadmaps read truthfully — a codename claims no sequence, so order-
  independent work is honest, not contradicted by the filename.
- Converges live with the `future/` convention; the corpus stops carrying two
  roadmap-naming styles for active work.
- Graph-neutral: identity is the opaque `id`, so renames never break edges.

### Negative

- A mixed corpus during and after migration (versioned history, codenamed live).
  Accepted: the split maps cleanly to lifecycle and is legible.
- A one-time migration must repoint every stem reference (edges + prose + the
  directory token + the H1 version), verified by a fail-closed sweep.

### Risks

- Stem collisions once the version prefix is dropped (real ones exist among
  historical items). Mitigation: codenames must be globally unique; the migration
  asserts it before any move; a future `rac validate` stem-uniqueness check can
  enforce it.

## Status

Accepted

## Category

Process

## Alternatives Considered

### Keep the vX.Y.Z scheme for roadmaps

Rejected: the number no longer bounds a release (ADR-076), orders work (ADR-093),
or identifies the artifact (ADR-026); it only implies a false sequence and blocks
order-independent work.

### Rename every roadmap, including shipped history

Rejected: it rewrites ~87 historical items and ~150 external references (CHANGELOG,
docs) that are correct as-is, surfaces real cross-series stem collisions, and
destroys the version-as-timestamp audit value. History stays versioned.

### Encode order in a frontmatter field instead of the number

Rejected: ADR-093 already moved ordering to the board; re-encoding it in the
artifact re-imports the coupling that decision removed.

## Related Decisions

- adr-093
- adr-076
- adr-061
- adr-026
- adr-047

## Related Requirements

- rac-release-versioning
