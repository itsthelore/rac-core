---
schema_version: 1
id: RAC-KTYBHXKBWZGZ
type: requirement
---
# Growth Essay Bridge: Mapping the Product-Knowledge Essay Series to Corpus Capabilities

## Status

Proposed

Blocked: GATE-1 (employer external-communications / IP review)

## Problem

The maintainer is writing a product-knowledge essay series in his own
voice. The series and the product share a thesis — tacit
product-management knowledge is built from unrecorded observable
decisions — but nothing connects the two. Without a recorded bridge,
each article either drifts into product promotion (breaching the
programme's voice constraints and undermining the series) or floats
free of the corpus entirely, so a reader persuaded by an article has
no recorded path from the problem it names to the capability that
answers it. The mapping also cannot live inside the articles
themselves: an article that explains its own marketing intent stops
being an essay.

## Requirements

- [REQ-001] Each published article in the product-knowledge essay series shall map to at least one named RAC capability or corpus artifact that answers the problem the article names.
- [REQ-002] Each article-to-capability mapping shall be recorded in the corpus as an artifact (currently the design `growth-essay-mapping`), not in the article text.
- [REQ-003] No article shall read as product marketing: the product shall appear, if at all, as a worked example in the closing portion of the piece, and never in the title, opening, or thesis statement.
- [REQ-004] No mapped article shall be published before GATE-1 (employer external-communications and personal-project IP review) has been cleared by the maintainer; agents may prepare structure and mappings but not release them.

## Success Metrics

- Every published article has a row in the mapping artifact whose
  capability column names a file or identifier that exists in this
  repository at the time of publication.
- A manual read of each published article finds the product mentioned
  no earlier than the worked-example section, if at all.
- `rac validate rac/` and `rac relationships rac/ --validate` exit 0
  with this artifact and the mapping design present.

## Risks

- The mapping artifact goes stale as articles are drafted and
  reordered; because the mapping is structural, staleness is
  detectable by comparing it against the published series, but it is
  not self-healing.
- The schema has no relationship type for "article satisfies this
  mapping" and no way to reference external or unpublished documents,
  so the article side of every mapping row is prose, not a validated
  reference (recorded as a gap by this programme).
- A capability cited in a mapping row may change or be superseded
  before the article publishes, silently invalidating the row.

## Assumptions

- Article 1's premise — tacit PM knowledge is built from unrecorded
  observable decisions — is stable; no draft exists in this repository
  at the time of writing, so mappings derive from the premise rather
  than from published text.
- The maintainer writes all article prose; agents contribute structure
  only. Nothing in this requirement or its design artifact is intended
  for publication.
- ADR-036 governs naming in any worked example: Lore is the product,
  RAC is the engine, stated once per surface.

## Related Decisions

- adr-036

## Related Requirements

- rac-growth-positioning

## Related Designs

- growth-essay-mapping
