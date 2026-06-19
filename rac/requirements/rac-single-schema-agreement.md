---
schema_version: 1
id: RAC-KV6KFM5484B9
type: requirement
tags: [internal, schema, contract, mcp, tui]
---
# Requirement: Single-Schema Cross-Consumer Agreement

## Status

Accepted

Classification: `[internal]`. Scoped to the v0.23.0 hardening release (WS6).
Delivered as a single pure-Python agreement test (`tests/test_schema_agreement.py`)
in the core battery; the consumers (validator `spec_for`, the classifier
`score_artifacts`, the portfolio type tally, the relationship vocabulary, and the
TUI `schema_reference`/`available_schemas`) were already deriving from the single
sources, so no ad-hoc schema logic needed folding back (REQ-005 satisfied with no
source change).

## Problem

The artifact schema is consumed by four code paths: the validator
(`services/validate.py`, via `spec_for`), the MCP tool serializers
(`mcp/server.py` — `get_artifact`, `search_artifacts`, `get_related`,
`get_summary`), and the TUI adapter (`explorer/adapter.py`, via
`schema_reference` and `load_repository`). If those consumers could drift apart,
a field, type, status, or relationship kind valid in one surface might be
mis-served, dropped, or invented in another.

RAC already defines the schema once, in code, in two code-owned sources (ADR-052,
ADR-049): the front-matter *envelope* — `_SUPPORTED_FIELDS` in
`core/frontmatter.py` and `ArtifactMetadata` in `core/metadata.py` — and the
per-type *structure* — `ARTIFACT_SPECS` in `core/artifacts.py` (types, required /
recommended / optional sections, status enums, `retired_status`), with the
relationship-kind vocabulary in `RELATIONSHIP_SECTIONS`
(`services/relationships.py`). The gap is that no test *asserts* the consumers
still agree with these sources, so drift would be silent. WS6 closes that gap
with one cross-consumer agreement test and nothing else: no Pydantic, no
JSON-Schema source of truth, no rewrite of the envelope or the specs.

## Requirements

- [REQ-001] The schema MUST remain defined once in code — the front-matter envelope (`core/frontmatter.py`, `core/metadata.py`) and the per-type specs (`core/artifacts.py`, `services/relationships.py`). This release MUST NOT introduce a parallel schema framework: no new Pydantic model layer, no JSON-Schema source of truth, no rewrite of the envelope or the specs, and no new runtime dependency (ADR-052, ADR-049).
- [REQ-002] The release MUST add one cross-consumer agreement test asserting that the validator, the four MCP serializers (`get_artifact`, `search_artifacts`, `get_related`, `get_summary`), and the TUI adapter all derive their schema knowledge from the single sources for: artifact types, status enums, relationship kinds, and required / recommended / optional sections.
- [REQ-003] The agreement test MUST assert that every field and section name each consumer serializes or validates traces back to the single sources — no consumer invents a field, type, status, or relationship kind not in the sources, and no consumer silently drops one the sources declare. Membership, not value formatting, is what is asserted.
- [REQ-004] The agreement test MUST fail loudly and deterministically when a consumer drifts: adding, removing, or renaming a type, status, relationship kind, envelope field, or required section in one place without the others MUST break the test with a diagnostic naming the consumer and the field that diverged. It is a pure-Python unit test in the standard battery, with no network, no AI, and no fixture corpus dependency.
- [REQ-005] Any residual ad-hoc schema logic found on those consumer paths SHOULD be folded back into the single sources rather than special-cased in the test.

## Acceptance Criteria

- The envelope and the per-type specs remain the only schema sources; no new schema framework or runtime dependency is added.
- One agreement test asserts the validator, the four MCP serializers, and the TUI adapter agree with those sources on types, statuses, relationship kinds, and section sets.
- Adding or removing a type, status, relationship kind, or required section in the source without updating a consumer fails the agreement test with a consumer-named diagnostic.
- No consumer serializes a field absent from the sources, and none drops a declared one.

## Success Metrics

- A schema change cannot ship green without the agreement test reflecting it
  across all named consumers; a deliberately drifted consumer fails the test.

## Risks

- The TUI could lag the schema. Mitigation: the TUI already consumes Core via
  `load_repository` and `schema_reference`, so the agreement test covers it
  without a migration.
- A fifth read tool (`find_decisions`) now exists in `mcp/server.py`. Mitigation:
  the test scope stays the four contract tools named in REQ-002; whether to
  extend coverage to `find_decisions` is an open maintainer decision, not a scope
  expansion for this release.

## Assumptions

- The code-defined envelope and the per-type specs are, and remain, the
  authoritative schema (ADR-052); this release guards them, it does not replace
  them.

## Out of Scope

- No Pydantic model layer, JSON-Schema source of truth, or any schema rewrite —
  the agreement test is additive (ADR-052, ADR-049).
- `schema_version` migration is out (T3-B): `schema_version: 1` already exists;
  no migration framework, no v1→v2 path, is built or assumed here.
- The test asserts membership agreement only; it does not normalize the wire
  representation (for example the serializers' `schema_version: "1"` string is
  left as-is, an additive contract detail under ADR-007, not a drift this test
  polices).

## Related Decisions

- adr-052
- adr-049
- adr-025

## Related Requirements

- rac-grounding-eval-benchmark

## Related Roadmaps

- v0.23.0-hardening
