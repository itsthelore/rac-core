---
schema_version: 1
id: RAC-KWJ8S53D06CH
type: requirement
---
# Requirement: Parent Corpus Inheritance

## Status

Proposed

Classification: `[internal]` — declare and materialise a firm-wide parent
corpus, offline and pinned. The declaration-and-materialisation half of
the `corpus-federation` programme, within ADR-089's non-negotiables.

## Problem

The corpus is single-tree (ADR-018, ADR-080): cross-repository references
do not resolve, and `## inherits` is deliberately unrecognised until
ADR-089's implementing design lands. The design-partner scenario ADR-089
anticipated is now real — an organisation holding firm-wide standards in
one corpus that every repository must resolve against. The declaration,
pinning, and materialisation contract needs recording so the mechanism
work has a testable boundary before the implementing ADR is authored.

## Requirements

- [REQ-001] A child corpus MUST declare inheritance in a Markdown `## inherits` section plus a pinned source reference — a git submodule (pinned by gitlink commit), a vendored bundle (pinned by content hash), or a path (pinned by commit or content hash) — human-readable and git-native, with no hidden index as truth (ADR-089); the carrying artifact and fixed path are set by the `corpus-federation-mechanism` design.
- [REQ-002] Parent resolution MUST read only materialised bytes already on disk: no network I/O in the validate, resolve, or serve paths (ADR-002, ADR-089); refreshing a materialisation is a user git operation outside the engine.
- [REQ-003] The parent MUST be a read-only inherited layer: no rac command writes under the parent materialisation, and the child's `main` remains the sole canonical state for child artifacts (ADR-018, ADR-065, ADR-080).
- [REQ-004] Validation MUST emit a deterministic, stable-coded finding when a declared parent is absent, and a distinct finding when the declared pin and the materialised bytes disagree — fail loud, never resolve silently against unverified state.
- [REQ-005] The declaration MUST stay backward-compatible: engines predating the capability treat `## inherits` as an unrecognised section with no hard failure, per ADR-089's compatibility clause.
- [REQ-006] Any optional `federation` configuration stanza MUST follow the established config section-loader pattern and MAY hold materialisation defaults only — the Markdown declaration remains the truth (ADR-089).
- [REQ-007] The capability MUST NOT be enterprise-gated (ADR-085, ADR-089) and MUST ship under the federation implementing ADR authored with the design partner; this requirement does not pre-decide that ADR.
- [REQ-008] On shipping, the ADR-088 profile scaffold MUST gain the reserved parent-corpus declaration line, emitted only when a parent is configured; unconfigured profile output stays byte-identical.

## Acceptance Criteria

- A fixture child corpus with a vendored, pinned parent validates fully
  offline — identical results with networking disabled.
- Removing the materialisation yields the missing-parent finding and a
  non-zero exit; changing parent bytes without re-pinning yields the
  stale-pin finding.
- The currently released engine, run over a corpus containing
  `## inherits`, behaves exactly as today's unrecognised-section handling.
- A test asserts the parent tree is byte-unchanged after every rac
  command.
- Enterprise profile output without a configured parent is byte-identical
  to today.

## Success Metrics

- An organisation's repositories each declare one pinned standards parent
  and validate against it offline, with pin updates arriving as ordinary
  reviewable diffs.

## Risks

- Pin verification is skipped for speed and staleness resolves silently.
  Mitigation: REQ-004 makes both failure modes named, stable-coded
  findings; the mechanism design pins verify-before-overlay.
- The config stanza quietly becomes the declaration. Mitigation: REQ-006
  bounds config to materialisation defaults; the Markdown section is the
  truth per ADR-089's constraint.

## Assumptions

- Submodule, vendored bundle, and path cover the partner's real
  materialisation topologies; the design's Open Questions cover multiple
  and transitive parents.
- The implementing ADR is authored with the design partner before the
  mechanism ships; the roadmap schedules it.

## Related Decisions

- adr-002
- adr-016
- adr-018
- adr-055
- adr-065
- adr-080
- adr-085
- adr-088
- adr-089

## Related Designs

- corpus-federation-mechanism

## Related Roadmaps

- corpus-federation

## Related Requirements

- rac-federated-resolution-provenance
