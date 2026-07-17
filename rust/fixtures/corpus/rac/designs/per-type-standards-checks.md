---
schema_version: 1
id: RAC-KV4134WX22MT
type: design
tags: [standards, requirements, ears, validation]
---
# Design: Per-Type Standards Checks

## Context

ADR-056 decides to encode the decidable parts of the requirements standards
(29148, EARS, BCP-14) as deterministic checks, and v0.17.1 also adds
roadmap horizon/outcome/linkage and decision MADR-field recognition. This design
works out *how* those checks plug into the existing validator without crossing the
no-AI-in-core line (ADR-002).

The validator dispatches per type in `rac.core.validation.validate`, which already
routes `requirement`/`roadmap`/`decision`/etc. to a `_validate_<type>` arm and
returns a flat `list[Issue]` with per-rule severities. The severity-override layer
(ADR-053) and SARIF output (ADR-054) consume that list unchanged, so new checks
that emit `Issue`s inherit overrides and SARIF for free.

## User Need

A maintainer (and CI) needs requirement quality flagged at write time — lowercase
normative keywords, non-EARS phrasing, unverifiable lines — with the same
deterministic, overridable, file+code+fix diagnostics the existing rules give, and
without any rule that needs a model to judge prose.

## Design

### Requirements checks (ADR-056)

A new `_validate_requirement_standards(product)` helper, called from the
requirement arm, iterates `product.requirements` (the parsed `[REQ-NNN]` lines)
and emits `Issue`s:

- **BCP-14 (error, `requirement-normative-keyword`).** A case-sensitive scan: a
  lowercase `shall`/`must`/`should` in a requirement line is flagged; uppercase
  `MUST`/`SHOULD`/`MAY` are accepted as normative. A small word-boundary regex.
- **29148 well-formedness (error/warning).** Singular: more than one normative
  keyword in one line warns (`requirement-not-singular`). Verifiable: extend the
  existing ambiguous-verb heuristic. Only the decidable characteristics; no
  prose-quality scoring.
- **EARS (warning).** Classify each line by keyword into the five patterns, then
  check clause cardinality (0..* preconditions, 0..1 trigger, one system, 1..*
  responses) and temporal order via a clause-segmenting regex. A line matching no
  pattern warns (`requirement-not-ears`); a malformed pattern warns with the
  specific clause problem. Pure string analysis — deterministic.

### Roadmap and decision checks

- **Roadmap (`roadmap-*`).** Check that the artifact declares a horizon (a
  `## Horizon` value in `now`/`next`/`later` or a `Qn YYYY` quarter, or the
  existing outcome wording), an outcome/metric, and at least one resolved
  relationship into the graph (reusing the relationship resolver). Field-presence
  and graph checks, not prose.
- **Decision MADR-4.0.** Recognise optional MADR fields (decision drivers,
  considered options, confirmation, consulted/informed) as known sections so they
  are not edge-unsupported; do not require them (the Nygard floor + ADR-051 status
  lifecycle already ship).

### Diagnostics and severity

Every `Issue` carries a stable code, a message that names the standard and the
fix, and (for requirement lines) the source line number. All route through the
ADR-053 override layer, so a team downgrades or silences a check via
`.rac/config.yaml`. SARIF picks them up unchanged.

## Constraints

- **No AI in core (ADR-002).** Every check is decidable by parsing; anything
  needing prose judgement is out of scope.
- **Determinism (ADR-002).** Same artifact, same findings and ordering.
- **Additive (ADR-007).** New codes only; existing requirement codes and the JSON
  contract are unchanged; EARS/29148-warning defaults keep legacy corpora green
  enough, and are overridable (ADR-053).
- **Spec-driven.** Roadmap/decision field recognition reads `ArtifactSpec`, not
  per-type branches in the rule body, where practical.

## Rationale

Emitting `Issue`s into the existing per-type arms means overrides, SARIF, exit
codes, and `rac review` all work with no new plumbing. Keeping EARS and most
29148 checks at warning severity makes the strongest-backed type enforceable
without breaking the many legacy requirements that predate the standards.

## Alternatives

- A separate `rac lint` command rather than folding into `rac validate`: rejected
  — splits the gate and the override/SARIF surfaces.
- A grammar/parser-combinator for EARS: heavier than the keyword + clause regex
  the decidable subset needs; revisit only if the regex proves brittle.

## Open Questions

- How much of 29148 "verifiable/feasible" is decidable before it becomes prose
  judgement (kept deliberately narrow for v0.17.1)?
- Should the roadmap horizon be a new `## Horizon` section or inferred from
  existing outcome wording? (Leaning: an optional section, validated when present.)

## Related Decisions

- adr-056
- adr-057
- adr-049

## Related Requirements

- rac-cross-artifact-enforcement

## Related Roadmaps

- v0.17.1-per-type-standards-enforcement
