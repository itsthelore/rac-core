---
schema_version: 1
id: RAC-KWJ2Z2GSNV9Y
type: roadmap
tags: [engine, refactor, quality, architecture]
---
# Engine Rebuild

## Status

Planned

## Context

A full-codebase review of rac-core (every subsystem plus cross-cutting
architecture, developer-experience, performance, and safety lenses) fed a
from-scratch rebuild of `src/rac` in which the existing test suite — 1747
tests, including byte-exact golden output pins — served as the acceptance
spec. The rebuild preserves every test-visible contract (module paths,
public names and signatures, CLI output, JSON shapes, exit codes,
determinism guarantees) while re-deriving the internals for clarity,
layering, and performance. The review findings that could not be absorbed
into a contract-preserving rewrite are the seed backlog for the follow-on
capability work this item fences.

## Outcomes

- The engine's internals are re-derived from reviewed briefs rather than
  accreted history: each module carries constraint-explaining documentation,
  duplication identified by the review is collapsed, and known algorithmic
  hotspots (repeated classification, quadratic identifier dedup) are gone.
- The external contract is untouched: the full test suite passes unchanged,
  golden outputs are byte-identical, and the JSON contract (ADR-007) and
  SDK surface (ADR-062) are stable through the swap.
- The review's cross-cutting findings are recorded as a prioritised
  development plan whose items can be scheduled as their own roadmap
  entries without re-deriving the analysis.

## Initiatives

- Subsystem rebuild briefs: extract the test-visible contract and internal
  design recommendations for every subsystem, adversarially audited against
  the test suite before any code is written.
- Contract-preserving rewrite: rebuild the core, services, output, CLI,
  MCP, and Explorer layers from the audited briefs, holding the full test
  suite, lint, format, and type gates green.
- Ten-x development plan: synthesise the review and rebuild learnings into
  a staged plan covering the capability, performance, and
  developer-experience investments that a contract-preserving rewrite
  cannot deliver alone.

## Success Measures

- Full pytest suite green (1747/1747) on the rebuilt tree, with two
  consecutive clean runs.
- `ruff check`, `ruff format --check`, and `mypy src/` all clean, matching
  the merge-gated CI batteries (ADR-027, ADR-075).
- Corpus gates pass with the rebuilt binary: `rac validate rac/`,
  `rac relationships rac/ --validate`, and `rac review rac/` with no
  priority 1–2 findings.
- The development plan exists as corpus artifacts that themselves pass the
  gates.

## Assumptions

- The existing test suite is a faithful specification of intended
  behaviour; where tests pin an output byte-for-byte, that output is
  treated as contract regardless of internal restructuring.
- Settled ADRs remain binding on the rebuilt internals (notably ADR-059
  single parser instance, ADR-060 shared structural validation, ADR-062
  SDK surface, ADR-007 JSON stability).

## Risks

- Contract surface wider than the tests: behaviour consumers rely on that
  no test pins could drift silently; the adversarial brief audits mitigate
  but cannot eliminate this.
- Mixed-tree integration: modules rebuilt in parallel against preserved
  interfaces may interact in ways only the full suite exposes; the
  integration loop must stay green between waves.
- Review findings that require cross-module changes (shared helpers, new
  spec fields) are deliberately deferred to follow-on items; losing that
  backlog would forfeit the review's main value.
