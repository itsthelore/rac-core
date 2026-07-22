---
schema_version: 1
id: RAC-KWGMTD67NRZW
type: roadmap
---
# Artifact Spec Extraction to a Language-Neutral Data File

## Status

Planned

Unscheduled member of the `agnostic-surfaces` programme, Track 2
(contract hardening). This is the first of ADR-063's two native-port
preconditions: "the artifact specs (`ARTIFACT_SPECS`) are first
extracted to a shared, language-neutral data file both engines read."
Starting it now is deliberate — the precondition is paid down before
any concrete native-port need arrives.

## Outcomes

- The five artifact type specs (requirement, decision, roadmap, prompt,
  design) — sections, metadata enums, synonyms, descriptions, guidance
  — live in one language-neutral data file, and the Python engine reads
  them from it.
- Any future engine or tool in any language can read the same file and
  agree with the Python engine about what an artifact type is, by
  construction rather than by transcription.
- Behaviour is unchanged: classification, validation, templates, and
  every golden output are byte-identical before and after.

## Initiatives

- Record an ADR fixing the file format and location before
  implementation (the format decision is the load-bearing part: it must
  represent the current spec shape — section tuples, metadata enums,
  synonyms, descriptions, guidance, retired-status — with a stable,
  append-only field order per ADR-007, and stay trivially parseable
  outside Python).
- Extract the `ARTIFACT_SPECS` literals from the artifacts module into
  that data file; the module loads it at import and rebuilds the same
  frozen dataclasses, so every existing consumer keeps its current API.
- Extend the schema-agreement test battery to assert data-file/engine
  parity the same way it already asserts parity across the Python
  consumers — failing loudly and naming the diverging field.
- Ship the file inside the package distribution so installed engines
  are self-contained, and document it as a read-only contract surface
  for external consumers.

## Constraints

- Behaviour-neutral refactor (ADR-023 governs the internal seam): no
  validation semantics, ordering, or template output may change; the
  golden suite is the referee.
- The dataclass API stays: consumers import the same names and shapes;
  only the source of truth moves.
- The data file is a contract artifact once published: additive
  evolution only, per ADR-007.
- No plugin or third-party spec loading in this item — dynamic
  discovery is ADR-083 territory and out of scope here.

## Success Measures

- The full test battery, including the byte-pinned goldens and the
  schema-agreement gate, passes with the specs loaded from the data
  file.
- Deleting the extracted literals from the Python module is total — no
  duplicated spec fragments survive in code.
- The conformance-fixtures item can point an external reader at the
  file and get the same type definitions the engine uses.

## Assumptions

- The current spec shape (tuples of section names, string-enum
  metadata, synonym maps — no regexes or code) is fully representable
  in a static data format; exploration confirms nothing in the specs is
  executable.
- Import-time loading of a packaged data file costs nothing observable
  on CLI startup.

## Risks

- A subtly lossy extraction (ordering, casing, synonym normalization)
  changes classification on edge-case corpora; mitigated by the golden
  suite plus the extended schema-agreement gate running both sources
  during the transition.
- The file invites hand-editing as if it were configuration; mitigated
  by documenting it as a versioned contract owned by the engine, not a
  user config surface (ADR-021's spirit: templates and specs are
  creation contracts).

## Related Decisions

- ADR-007
- ADR-021
- ADR-023
- ADR-060
- ADR-063

## Related Roadmaps

- agnostic-surfaces
- conformance-fixtures
