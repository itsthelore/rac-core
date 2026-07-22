---
schema_version: 1
id: RAC-KV4ZAHVNGH2J
type: decision
tags: [validation, refactor, engine]
---
# ADR-060: Share Structural Validation Across Per-Type Validators

## Context

Each artifact type has its own validator in `rac.core.validation`
(`_validate_decision`, `_validate_roadmap`, `_validate_prompt`,
`_validate_design`, `_validate_requirement`). Over successive roadmap-led
additions these accumulated copy-pasted structural checks: the title check
(`missing-title` / `multiple-titles`) was duplicated verbatim across all five,
the required-section loop was near-identical across four, and the
requirement validator repeated the same `Counter` + seen-set pattern for both
duplicate-ID and duplicate-text detection. One type — Design — carried a
hand-written special case (`section.replace(' ', '-')`) for its only multi-word
required section, so its issue code read `missing-user-need`.

The duplication made the validators harder to read and risked the per-type
checks drifting apart. The repository's simplification discipline (ADR-047)
prefers moving repeated logic into shared helpers and existing data structures
over leaving copies in place.

## Decision

Extract the shared structural checks into named helpers the per-type
validators call: `_validate_title`, `_validate_required_sections`, and
`_report_duplicates`. Apply the multi-word issue-code rule
(`section.replace(' ', '-')`) uniformly inside `_validate_required_sections`
rather than as a per-type branch, and derive the human label from the type's
`ArtifactSpec` name.

Issue codes, messages, line numbers, severities, and ordering are unchanged.
The uniform hyphen rule is a no-op for single-word required sections, so every
existing code (including `missing-user-need`) is preserved exactly.

## Consequences

Positive: the validators are shorter and read as "title, required sections,
type-specific rules"; the Design special case disappears; complexity of the
requirement validator and the per-type validators drops materially. Behavior is
held constant by the golden-output battery and the existing validation tests.

Trade-off: a uniform rule is slightly less explicit than a visible per-type
branch at the Design call site, but it removes a latent inconsistency (a future
multi-word required section on another type would otherwise need its own copy of
the special case).

## Status

Accepted

## Category

Architecture

## Alternatives Considered

- **Leave the duplication in place.** Each validator stays self-contained, but
  the copies risk drifting and the Design special case stays invisible to the
  other types.
- **Add an `ArtifactSpec` field for per-type issue-code transforms.** Rejected
  as a premature abstraction: it would add configuration consumed by exactly one
  type, where a uniform no-op-for-single-words rule achieves the same result with
  no new data and no behavior change.

## Related Decisions

- adr-047

## Related Roadmaps

- v0.18.0-engine-simplification
