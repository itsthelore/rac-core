---
schema_version: 1
id: RAC-KWJ8S74MXFG0
type: requirement
---
# Requirement: Federated Resolution and Provenance

## Status

Proposed

Classification: `[internal]` — inherited artifacts resolve read-only,
collide loudly, and stay attributable everywhere. The resolution half of
the `corpus-federation` programme, within ADR-089's non-negotiables.

## Problem

Once a parent corpus materialises, its artifacts must participate in
resolution without a parallel resolver, without silent precedence in
either direction, and without losing source attribution anywhere it
matters — resolution results, MCP responses, validation findings, or
exports. ADR-089's constraints say what must hold; this requirement makes
each one testable at the engine's existing seams.

## Requirements

- [REQ-001] Inherited artifacts MUST enter resolution as a read-only overlay through the engine's existing seams — the corpus walk feeding the entry stream, the resolution and identifier indexes, the repository index, and the MCP identity map — with no second resolver introduced.
- [REQ-002] A parent/child identifier collision MUST surface as an explicit deterministic finding at the engine's existing duplicate-identity detection point — never silent precedence in either direction (ADR-089).
- [REQ-003] Overrides MUST be explicit: a child masks a parent artifact only via a declared override section naming the parent source and identifier, shaped by the `corpus-federation-mechanism` design; an undeclared duplicate remains a finding.
- [REQ-004] Provenance MUST be preserved end to end: resolution results, MCP tool responses, and validation findings all attribute inherited artifacts to their source corpus (ADR-089).
- [REQ-005] Export composition MUST reuse the corpus-sync derivation: federated exports stamp parent-origin records with the parent's own source identity per `rac-export-source-identity`, keeping `(source, id)` aggregation collision-free (ADR-026) and shared parents deduplicable downstream.
- [REQ-006] Determinism MUST hold: identical child and parent materialised bytes produce byte-identical resolution, validation, and export output across runs, machines, and clones (ADR-002).
- [REQ-007] Single-corpus behaviour MUST be unchanged: with no `## inherits` present, all outputs are byte-identical to the pre-federation engine, asserted by golden regression.
- [REQ-008] Child validation MUST never demand changes to parent bytes: no finding's remediation can require editing the read-only layer (ADR-065).

## Acceptance Criteria

- A child artifact's related-decisions entry naming a parent ADR
  resolves; relationship validation is clean; MCP responses carry the
  parent's source.
- A same-identifier fixture yields the collision finding naming both
  sources, and a declared override clears it with override provenance
  recorded.
- A documents export over the federated fixture stamps parent and child
  records with their own sources, with zero `(source, id)` collisions.
- Corpora without `## inherits` produce output byte-identical to the
  released engine.
- Two clones of the same pinned state produce byte-identical outputs.

## Success Metrics

- A child repository cites a firm-wide ADR the way it cites its own, and
  every downstream consumer — agent, export, auditor — can tell where the
  knowledge came from without extra tooling.

## Risks

- Resolution-order accidents introduce de facto precedence. Mitigation:
  REQ-002 pins collision semantics at the single detection point, and
  REQ-006's determinism assertion makes any ordering drift a test
  failure.
- Provenance is dropped at one surface (for example findings but not
  exports). Mitigation: REQ-004 and REQ-005 enumerate the surfaces, and
  the acceptance criteria exercise each.

## Assumptions

- `rac-parent-corpus-inheritance` lands first; this requirement consumes
  a verified, materialised parent and adds no materialisation machinery.
- The corpus-sync source-identity derivation is available as the single
  identity mechanism exports compose with.

## Related Decisions

- adr-002
- adr-026
- adr-055
- adr-065
- adr-080
- adr-085
- adr-089

## Related Designs

- corpus-federation-mechanism

## Related Roadmaps

- corpus-federation
- corpus-sync

## Related Requirements

- rac-parent-corpus-inheritance
- rac-export-source-identity
