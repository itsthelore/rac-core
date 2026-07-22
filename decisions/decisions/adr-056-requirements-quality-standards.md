---
schema_version: 1
id: RAC-KV4134WXHR72
type: decision
tags: [standards, requirements, validation, ears]
---
# ADR-056: Encode Requirements Quality Standards (29148, EARS, BCP-14) as Deterministic Checks

## Status

Proposed

## Category

Product

## Context

Requirements are the artifact type with the strongest external standards backing,
and RAC validates only their structure today (a `## Requirements` section of
`- [REQ-NNN] ...` lines, plus an ambiguous-verb warning). It does not check the
*quality* standards it aligns to: ISO/IEC/IEEE 29148:2018 well-formedness, the
EARS syntax (Mavin et al.), and BCP-14 normative keywords (RFC 2119 + RFC 8174).

The product premise (ADR-002) forbids LLM judgement in the validation core: a rule
is in scope only if it is decidable by parsing. Much of these standards *is*
decidable — keyword presence and case, clause cardinality and order, a closed set
of well-formedness heuristics — and that decidable subset is what this decision
encodes. The moment a rule needs a model to judge prose quality, it is out of
scope.

This interprets the enforcement posture (ADR-049), determinism (ADR-002), the
contract-stability rules (ADR-007), and the severity-override model (ADR-053).

## Decision

RAC adds per-type quality checks for `requirement` artifacts, all deterministic
and decidable by parsing:

1. **BCP-14 keyword discipline (error).** Only uppercase `MUST`/`MUST NOT`/
   `SHOULD`/`SHOULD NOT`/`MAY` carry normative weight. A lowercase `shall`/`must`/
   `should` inside a requirement line is flagged as ambiguous normative language —
   an error inside `requirement` artifacts.

2. **29148 well-formedness (error/warning).** Encode the structurally checkable
   "well-formed requirement" characteristics — singular (one requirement per
   `[REQ-NNN]` line), verifiable, and unambiguous (extending the existing
   ambiguous-verb heuristic). The decidable subset only; "feasible/complete" and
   prose-quality judgement are explicitly out of scope (they need a human or a
   model).

3. **EARS syntax (warning).** Detect the five patterns by keyword — Ubiquitous
   (none), Event-Driven (`When`), State-Driven (`While`), Unwanted Behaviour
   (`If … then`), Optional (`Where`) — and validate keyword presence, clause
   cardinality (0..* preconditions, 0..1 trigger, exactly one system name, 1..*
   responses), and temporal clause order. **Warning** severity: legacy
   requirements will not comply, and warnings-first onboarding is a requirement.

4. **Severity is overridable.** All of the above route through the v0.15.2 model
   (ADR-053), so a team can downgrade or silence a check during onboarding.

5. **Diagnostics cite the standard.** Each finding names the standard (29148 /
   EARS / BCP-14) and the fix, so the check teaches rather than nags.

Roadmaps (horizon/outcome/linkage) and decisions (MADR-4.0 optional fields) are
delivered in the same milestone but are wiring/field-presence checks, not a
standards-encoding decision; they need no separate ADR. Prompt↔dotprompt interop
is ADR-057.

## Consequences

### Positive

- RAC's strongest-backed artifact type is enforced against the standards it cites,
  deterministically and offline — the product premise (no AI in core) holds.
- BCP-14 discipline removes a real ambiguity (lowercase "shall") at write time.
- EARS guidance is advisory, so adoption is non-hostile.

### Negative

- More requirement-quality rules to keep deterministic and false-positive-free.
- The 29148/EARS encodings are a *subset*; users may expect full conformance the
  checks deliberately do not attempt.

### Neutral

- The existing ambiguous-verb warning is subsumed/extended, not removed.

## Alternatives Considered

- **LLM-scored requirement quality.** Rejected: violates ADR-002 (no AI in the
  validation core) — the product's entire premise.
- **Make EARS an error.** Rejected: legacy requirements will not comply; warning
  severity plus override (ADR-053) keeps adoption non-hostile.
- **Skip requirements standards.** Rejected: requirements have the strongest
  standards backing; this is the highest-value per-type enforcement.

## Related Decisions

- adr-049
- adr-002
- adr-007
- adr-053

## Related Requirements

- rac-cross-artifact-enforcement

## Related Roadmaps

- v0.17.1-per-type-standards-enforcement

## Related Designs

- per-type-standards-checks
