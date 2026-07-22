---
schema_version: 1
id: RAC-KV3FZJNRVNPE
type: decision
---
# ADR-049: Write-Time Cross-Artifact Enforcement Is RAC's Core

## Status

Proposed

## Category

Product

## Context

Google Cloud published the Open Knowledge Format (OKF) — a Git tree of Markdown
with YAML front matter, backed by a hyperscaler and reference implementations.
Per-type schemas are being standardised too: MADR for decisions, dotprompt for
prompts. Between them, two layers RAC once looked distinctive for are being
commoditised in front of us:

- the **carrier** (a markdown-and-front-matter bundle) — now OKF, with
  zero-tooling adoption;
- the **per-artifact schema** (what fields a decision or prompt should carry) —
  now MADR/dotprompt and similar.

This sharpens, rather than answers, the platform-absorption objection: "a model
that eats the markdown" now has a Google-blessed, zero-tooling format to eat, and
the per-file shapes are converging on community standards. If RAC's pitch rests
on the file format or the per-type schema, it is defending ground that is being
levelled.

What none of those layers do — and what RAC already does — is validate the corpus
*as a graph*, deterministically, at write time, in CI: that every reference
resolves, that nothing points at a decision the team has superseded, that a
declared relationship is actually a legal edge rather than silently inert prose.
OKF is explicitly permissive (consumers MUST NOT reject on broken links or
unknown types); MADR/dotprompt validate a single file in isolation. Cross-artifact
referential integrity, status-consistency, and illegal-edge detection are RAC's
alone.

This decision interprets the relationship model (ADR-016) and the
intelligence-not-content-store boundary (ADR-024), and follows the OKF carrier
profile (ADR-048) by stating what RAC keeps when the carrier is shared.

## Decision

RAC's core product is **deterministic, CI-enforced, cross-artifact validation** —
write-time enforcement of the corpus as a graph. The carrier (now OKF) and the
per-type schemas (now MADR/dotprompt and peers) are **table stakes**: RAC stays
compatible with them and treats them as interchange, not as the differentiator.

Concretely, the product is the enforcement surface, in priority order:

1. **Referential integrity** — every relationship resolves to exactly one
   existing artifact (already shipped: broken, ambiguous, self-reference, and
   duplicate-identifier detection).
2. **Status-consistency** — no live artifact may point at a superseded or
   deprecated target (beginning decision-only, where lifecycle status exists).
3. **Edge-legality** — a declared relationship that is not a legal edge for the
   source type is surfaced as a finding, never silently dropped.

These checks are deterministic (same corpus state, same result; ADR-002), live in
RAC Core, and gate CI through `rac validate` / `rac relationships --validate` /
`rac watchkeeper`. Roadmap priority follows this decision: enforcement
capabilities lead; carrier and schema work are sequenced as interop, not as the
headline.

The positioning line, to be reflected on public surfaces: OKF says "if you can
`cat` it, you can read it"; RAC says "and CI guarantees the file is well-formed,
the decision is consistent, and nothing points at a superseded artifact." OKF is
read-time interchange; RAC is write-time enforcement.

## Consequences

### Positive

- A defensible, single-sentence differentiator that does not depend on owning the
  file format or the per-file schema.
- Clear roadmap prioritisation: cross-artifact enforcement rules are first-class
  product work, not validation housekeeping.
- Aligns with where RAC already invests (ADR-016, the review/watchkeeper model).

### Negative

- RAC must actually deliver the enforcement rules it now claims as the product
  (status-consistency and edge-legality are not yet implemented).
- Leaning into graph enforcement raises the bar for determinism and false-positive
  discipline on every new rule.

### Neutral

- Schema and carrier compatibility (OKF, and any future MADR/dotprompt alignment)
  remain supported and tested — as table stakes, deliberately not as the pitch.

## Alternatives Considered

- **Compete on the carrier or the per-type schema.** Rejected: both are being
  commoditised by a hyperscaler and community standards; defending them is a
  losing position and is not where RAC's value lives.
- **Leave enforcement as an unstated capability.** Rejected: without naming it as
  the product, roadmap priority and public positioning keep drifting toward
  format/schema parity, the exact ground being levelled.

## Related Decisions

- ADR-016
- ADR-024
- ADR-048

## Related Requirements

- rac-cross-artifact-enforcement
- rac-growth-positioning
- rac-repository-review-mode
