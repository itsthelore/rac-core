---
schema_version: 1
id: RAC-KVSNNZ7YRMEZ
type: requirement
---
# Unlinked Reference Detection

## Problem

RAC's relationship graph is built only from edges an author declares in
`## Related <Type>` sections. That is deliberate — the graph is *validated*,
not inferred from prose (ADR-074) — but it leaves a real gap: an artifact's
body routinely names another artifact (an ADR id, a requirement, a design)
without a matching `## Related` edge. The reference is true and intentional,
yet the graph does not carry it, so traversal, coverage, and the export
contract all under-report the corpus's actual connectedness.

Today `rac doctor` finds *orphans* (artifacts nothing links to) but has no way
to find a link the author clearly meant — one they already wrote in prose and
simply did not promote to a declared edge. Authors are left to notice missing
links by eye. The affected users are corpus maintainers and the agents that
consume the graph: both see a sparser graph than the text supports.

## Requirements

- [REQ-001] RAC SHALL detect, for each artifact, references in that artifact's body to other corpus artifacts — matched by canonical id, declared alias, or filename-style reference (for example `adr-074`) — that are absent from the artifact's declared `## Related <Type>` sections.
- [REQ-002] RAC SHALL report each mentioned-but-unlinked reference as an advisory finding that names the source artifact, the matched target, the token that matched, and the `## Related <Type>` section that would capture the edge.
- [REQ-003] Detection SHALL be deterministic and offline: a pure function of corpus bytes with no model, embedding, or network call, such that identical corpora produce byte-identical findings (ADR-002, ADR-066).
- [REQ-004] RAC SHALL NOT create, write, or modify any relationship edge automatically; a finding is a suggestion a human promotes through review (ADR-065, ADR-082).
- [REQ-005] The advisory SHALL NOT change the exit code of `rac validate` or `rac relationships --validate`; a mentioned-but-unlinked reference never blocks a merge on its own.
- [REQ-006] Detection SHALL exclude self-references, targets already declared as edges, fenced code blocks, and the `## Related` sections themselves, and SHALL emit at most one finding per (source artifact, target artifact) pair.

## Success Metrics

- On the dogfood corpus, the detector surfaces only references a maintainer
  agrees should be promoted (high precision); spot-checked false positives are
  near zero because matching is limited to ids, aliases, and filename refs.
- The check adds no new failing exit code: `rac validate` and
  `rac relationships --validate` exit codes are unchanged with the detector
  present.
- Re-running the detector on an unchanged corpus yields byte-identical output.

## Risks

- **Noise.** Loose matching (especially on titles) would flood maintainers with
  spurious suggestions and train them to ignore the channel. Mitigation: ship
  id/alias/filename matching only; treat title matching as a separate, deferred
  question (the design's Open Questions).
- **Edge-meaning drift.** A suggestion could be read as an assertion that an
  edge exists. Mitigation: findings are advisory and never auto-applied
  (REQ-004); the declared `## Related` sections remain the single source of
  truth (ADR-074).

## Assumptions

- A body reference to another artifact, by id or filename ref, is usually a link
  the author intended and would promote if reminded.
- Deterministic matching on ids, aliases, and filename references is
  high-precision enough to be trusted without a model (ADR-002, ADR-066).

## Related Decisions

- adr-082
- adr-074
- adr-065
- adr-066
- adr-002

## Related Designs

- mentioned-but-unlinked-detection

## Related Roadmaps

- link-suggestions

## Related Requirements

- rac-traceability-coverage-report
- rac-doctor-diagnostic-validator
