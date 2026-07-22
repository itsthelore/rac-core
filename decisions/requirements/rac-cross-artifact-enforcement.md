---
schema_version: 1
id: RAC-KV3G0KY6Y4NM
type: requirement
---
# REQ-Cross-Artifact-Enforcement

> The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY in this document are
> to be interpreted as described in BCP 14 (RFC 2119, RFC 8174) when, and only
> when, they appear in all capitals.

## Status

Accepted

## Problem

The markdown carrier (OKF) and per-type schemas (MADR, dotprompt) are being
commoditised. The capability that stays RAC's alone — and that nothing in that
landscape provides — is deterministic, CI-enforced validation of the corpus as a
graph (ADR-049). Today RAC enforces only part of it: references must resolve
(`rac relationships --validate`), but two graph-level guarantees a reader expects
from "the decision is consistent" are missing:

- **Status-consistency.** A live artifact can reference a decision the team has
  marked `Superseded` or `Deprecated`, and nothing flags it — the corpus silently
  points at retired knowledge.
- **Edge-legality.** A `## Related <Type>` section that the source type's schema
  does not consume is silently dropped: it renders as prose, passes validation,
  and produces zero edges with no warning (the same silent-failure class recorded
  in `rac-traceability-self-relationships` REQ-003).

This requirement makes cross-artifact enforcement an explicit, named product
surface and closes those two gaps.

## Requirements

- [REQ-001] RAC MUST treat cross-artifact validation as a first-class, deterministic, CI-gated product surface: every rule yields the same findings for the same corpus state, runs in RAC Core, and influences `rac validate` / `rac relationships --validate` / `rac watchkeeper` exit codes and verdicts.

- [REQ-002] Referential integrity MUST remain enforced: a relationship reference that resolves to no artifact, to more than one artifact, to itself, or that collides on a duplicate identifier is a validation issue (already shipped; retained as the foundation).

- [REQ-003] Status-consistency MUST be enforced for decisions: a relationship whose resolved target is a decision with status `Superseded` or `Deprecated` is a validation issue, EXCEPT the `supersedes` relationship by which the replacing decision points at the one it replaces. The check MUST be deterministic and reuse the existing status canonicalisation.

- [REQ-004] Edge-legality MUST be surfaced, not silent: a `## Related <Type>` section present on an artifact whose type does not declare that relationship (so it produces no edge) MUST be reported as a finding rather than dropped silently. This satisfies `rac-traceability-self-relationships` REQ-003.

- [REQ-005] New enforcement findings MUST distinguish themselves with stable issue codes and MUST NOT loosen or rename existing relationship issue codes (ADR-007 contract stability).

## Acceptance Criteria

- `rac relationships rac/ --validate` exits `0` on the clean corpus and `1` on a fixture that references a `Superseded` decision from a non-`supersedes` edge.
- The `supersedes` edge from a replacing decision to the decision it supersedes does NOT raise the status-consistency issue.
- A fixture artifact carrying a `## Related <Type>` section its type does not declare produces an edge-legality finding (not a silent drop) and is visible in `rac relationships`/`rac validate` output.
- Every new issue has a stable, documented code; existing codes
  (`relationship-target-not-found`, `relationship-target-ambiguous`,
  `relationship-self-reference`, `duplicate-artifact-identifier`) are unchanged.
- `rac validate rac/`, `rac relationships rac/ --validate`, and `rac review rac/`
  stay green on the corpus after the rules ship.

## Success Metrics

- A corpus that points at a superseded decision fails CI deterministically rather
  than drifting unnoticed.
- The count of silently-dropped relationship sections across the corpus reaches
  zero (each is either a real edge or a surfaced finding).

## Risks

- Over-strict status-consistency could flag legitimate historical references.
  Mitigated by the explicit `supersedes` exception and by scoping to decisions
  first (where lifecycle status exists), generalising only if warranted.
- Edge-legality could fire on intentional prose headings that merely resemble a
  relationship section. Mitigated by matching only the canonical
  `## Related <Type>` section names already used by the parser.

## Assumptions

- The relationship model stays "structural references in Markdown sections"
  (ADR-016); this requirement adds graph-level checks, not a new mechanism.
- Lifecycle status remains decision-only for now (a later, separately scoped
  decision may generalise it).

## Related Decisions

- ADR-049
- ADR-016
- ADR-007
- ADR-024

## Related Requirements

- rac-repository-review-mode
- rac-traceability-self-relationships

## Related Roadmaps

- v0.14.0-enforcement-foundation
- v0.14.1-status-consistency
