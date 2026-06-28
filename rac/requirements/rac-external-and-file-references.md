---
schema_version: 1
id: RAC-KW7VKD2AANC5
type: requirement
---
# RAC Traceability — External and Repo-File References

## Status

Proposed

## Problem

Artifacts routinely depend on targets that are not peer artifacts: a requirement
is satisfied by a README section, a `SKILL.md`, or a CI workflow file; a
positioning claim rests on an external source URL. RAC can express references to
peer artifacts (`## Related <Type>`) and to tickets (`## Related Tickets`,
ADR-087), but a reference to a **repository file** or an **external URL** has no
home. Authors either omit the link or bury it in prose, so a rename breaks the
connection silently and the link is invisible to validation, `rac relationships`,
and the Lore MCP server. (ADR-019 covers assets/images only.)

This is gaps 1 and 2 of the traceability audit, consolidated: both are references
to a non-artifact target, format/existence-checked, never resolved to a peer
artifact and never fetched.

## Evidence

- **artifact → repo-file (≥3):** `rac-growth-positioning` (satisfied by a README
  section it cannot reference), `rac-growth-agent-skill` (satisfied by
  `.claude/skills/rac-artifacts/SKILL.md`), `rac-documentation-structure` (places
  testable requirements on doc files by bare path), `adr-027` (governs CI
  workflow files the same way).
- **external URL (≥3):** `rac-growth-positioning` comparison sources,
  `growth-essay-mapping` external article rows, `rac-grounding-eval-benchmark`
  external references.

## Requirements

- [REQ-001] The relationship vocabulary can express a reference from an artifact to a repository file by repo-relative path (for example a `## Satisfied By` / `## Related Files` section), recognised and extracted like the existing relationship sections.

- [REQ-002] A declared repo-file reference is existence-checked by `rac relationships --validate` against the repository, so a missing or renamed target is reported rather than failing silently.

- [REQ-003] The relationship vocabulary can express an external source reference as a URL (for example a `## Sources` section), format-validated and surfaced via `get_artifact`, never fetched or resolved by the engine (ADR-002, ADR-066).

- [REQ-004] Both additions are additive (ADR-007): new optional sections, `schema_version` unchanged, existing relationship sections and their JSON shape untouched; they reuse the non-artifact-reference mechanism established for `## Related Tickets` (ADR-087) rather than a parallel one.

## Success Metrics

- A renamed file referenced by `## Satisfied By` produces a `rac relationships
  --validate` finding instead of a silent break.
- The audit's evidence instances become declared, checkable references.
- Re-running validation on an unchanged corpus is byte-stable; no network call is
  on the path.

## Risks

- Path references can drift during repository moves (the topology re-org);
  mitigated by deferring the repo-file half until target paths settle.
- A new section shifts the classification surface; mitigated by additive-only
  changes and the adjacent-type misclassification tests.

## Assumptions

- The relationship model stays "structural references in Markdown" (ADR-016).
- Determinism holds: existence/format checks only, never fetching (ADR-002, ADR-066).

## Related Decisions

- adr-016
- adr-087
- adr-019
- adr-007
- adr-002
- adr-066

## Related Roadmaps

- relationship-vocabulary
