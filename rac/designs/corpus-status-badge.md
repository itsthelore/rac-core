---
schema_version: 1
id: RAC-KWQAZW678TP3
type: design
---
# Corpus Status Badge

## Status

Proposed

Exploratory — Opportunity 2 of `adoption-opportunity-survey`, split out for
independent consideration. The cheapest net-new distribution lever. Not an
accepted build.

## Context

Open-source developer tools spread partly through the README badge loop: a
coverage or build badge in one project's README is passive social proof and a
link back, seen by everyone who visits. Lore produces the numbers such a badge
would show — artifact counts, validation state, health — via `rac portfolio`
and `rac review`, but exposes no badge an *adopting* repository can render for
its own corpus. This is distinct from RAC's own CI and coverage badges
(`rac-trust-transparency` FR-6/FR-7), which sign this repository's build, not a
feature an adopter displays.

## User Need

- An **adopting team** wants a small, credible signal in their README that they
  keep decisions as code and that the corpus validates — a trust marker for
  their own readers.
- **Lore** wants each adopter's README to become a passive link back — the
  distribution loop the CLI has no equivalent of today.

## Design

A shields.io-compatible endpoint shape emitted from the corpus — a minimal JSON
(`{ schemaVersion, label, message, color }`) that renders as
`Lore · 42 decisions · validated`. Two delivery options:

1. **Static** — `rac badge --json` (or a documented projection of
   `rac portfolio --json`) that a repo writes to a file its README references,
   refreshed in CI. Zero hosted infrastructure.
2. **Endpoint** — a small `lore-*` service that reads a public corpus and serves
   the shields JSON live, so the badge is always current without a commit.

Both derive the message live from the corpus (counts, valid/invalid, health)
and never store a value (the ADR-045 derive-not-store posture). The message is
data, not a verdict (ADR-034): it reports "42 decisions, validated," not "good."

## Constraints

- **Thin client over the contract (ADR-063), additive (ADR-007).** The badge
  reads `rac portfolio` / `rac review` output; a `rac badge` mode is an additive
  projection, `schema_version` unchanged.
- **Derive, never store (ADR-045 posture).** A stale badge is worse than none;
  the value is computed from the current corpus each time, and CI (static
  option) or the endpoint (hosted option) keeps it fresh.
- **Facts, not verdicts (ADR-034).** The badge states counts and validation
  state; it makes no quality claim.
- **Brand/topology (ADR-068).** `rac badge` is an engine affordance; a hosted
  endpoint is a `lore-*` product.

## Rationale

Near-zero build over output that already exists, and the highest-reach-per-effort
option in the survey: every adopter's README becomes a passive advertisement and
a trust marker at once. It reinforces the recorded identity (a corpus that
validates deterministically) rather than adding a new category.

## Alternatives

- **A dashboard instead of a badge.** Higher effort, lower reach; a badge is the
  proven, glanceable distribution unit. A richer view already exists as
  `rac-localview` / the Explorer.
- **Reuse RAC's own CI badge pattern.** Rejected: those sign this repo's build,
  not an adopter's corpus; conflating them would misrepresent what the badge
  attests.
- **A hosted-only endpoint.** Rejected as the sole path: it forces
  infrastructure for what a static CI-refreshed file already delivers; offer the
  static shape first, the endpoint as an option.

## Accessibility

Badges must not encode meaning in colour alone: the message text
("42 decisions · validated") carries the information; colour is redundant
reinforcement, and a non-colour reading is complete.

## Style Guidance

Match the shields.io convention (label · message · colour). Keep the message
factual and short; no promotional adjectives. Use the `lore` mark consistent
with ADR-036 naming.

## Open Questions

- Is the static `rac badge --json` shape sufficient, or is a hosted endpoint
  warranted for always-current badges without a commit?
- What exactly does the message show — decision count, total artifacts,
  validation state, health score — and how is "validated" defined for a corpus
  with advisory-only findings?
- How is staleness communicated in the static option if a repo forgets to
  refresh the badge in CI?

## Related Decisions

- adr-007
- adr-034
- adr-036
- adr-045
- adr-063
- adr-068

## Related Roadmaps

- growth-programme

## Related Requirements

- rac-growth-adoption
