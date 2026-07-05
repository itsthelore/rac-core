---
schema_version: 1
id: RAC-KWRSFWSF7R4T
type: roadmap
---
# Corpus Setup and Structuring Guidance (Future)

## Status

Planned

Unscheduled — recorded as future intent, not yet on a release. It must not
displace scheduled engine work; each initiative graduates with its own scope
and an ADR-093 execution issue when picked up.

## Context

RAC validates artifacts once they exist, but records no opinionated guidance
on how a team should set up and structure a corpus in the first place.
Observed at large-organisation scale (a ~2,500-person org): teams set up
their decision records differently and inconsistently, and default to a
single "mega-doc" of decisions rather than discrete, individually
addressable artifacts. A mega-doc defeats the properties the engine is built
on — per-artifact identity, typed relationships, per-decision lifecycle
status, and retrieval that can serve one decision to an agent instead of a
whole file.

The pieces that would fix this exist but are not connected as guidance:
`rac init` scaffolds configuration (and profiles, ADR-088) but not
structuring conventions; `rac ingest` can split an existing document into
discrete artifacts (ADR-006, ingestion over rewrite); the onboarding
scaffold writes one starter artifact (ADR-044). Nothing tells a team "one
decision per artifact", how to lay out `rac/`, or how to get from an
existing mega-doc to a well-formed corpus.

## Outcomes

- A team adopting RAC lands on a consistent, conventional corpus structure
  without needing a human expert in the loop — the same shape whichever team
  in the organisation sets it up.
- The mega-doc anti-pattern has a documented, low-effort exit: an existing
  decisions document becomes discrete validated artifacts through a
  recorded path rather than a manual rewrite.

## Initiatives

### Initiative 1 — Opinionated setup and structuring guide

An authored guide (docs-site + README doorway) recording the conventions the
dogfood corpus already practises: directory layout under `rac/`, granularity
(one decision or requirement per artifact, and why), naming, when to record
an ADR versus a requirement versus a design, and how the corpus composes
with `rac init` / profiles (ADR-088).

### Initiative 2 — Mega-doc split path

A documented recipe for converting a single decisions document into
discrete artifacts via `rac ingest` (ADR-006): what the tool does, what the
human reviews, and how the result is promoted through pull-request review
(ADR-065). Documentation-first; any tooling change needs its own scope.

An advisory structural finding (for example, doctor flagging a single
artifact that contains many decision-shaped sections) is a candidate
follow-on, deliberately not committed here — it needs its own decision
before any gate-adjacent behaviour is added.

## Success Measures

- A new team following the guide alone produces a corpus that passes
  `rac validate` and `rac relationships --validate` with the conventional
  layout, without expert help.
- A real mega-doc has been split into discrete artifacts by following the
  recorded recipe end to end.

## Assumptions

- ADR-017 and ADR-024 hold: the guidance covers knowledge structure, never
  work tracking or content storage.
- `rac ingest` remains the sanctioned conversion path (ADR-006, ADR-072);
  the recipe documents it rather than adding a parallel mechanism.

## Risks

- Guidance that reads as policy could conflict with how existing corpora
  are already laid out; the guide records conventions and defaults, not
  validation rules — anything enforceable needs its own decision first.
- Over-specifying granularity could push teams into artificial splitting;
  the guide should state the principle (one addressable decision per
  artifact) and leave judgement to the author.

## Related Decisions

- adr-006-ingest-over-rewrite
- adr-044-onboarding-scaffold
- adr-065-artifact-content-untrusted
- adr-088-enterprise-profile-scaffold
