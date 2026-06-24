---
schema_version: 1
id: RAC-KVW05N861478
type: requirement
tags: [user-facing, traceability, verification, coverage, determinism]
---
# Requirement: Capability Verification Evidence

## Status

Proposed

Classification: `[user-facing]` — see which product capabilities have
verifying evidence and which do not. Stays in the open-source core (ADR-012):
it improves the *understanding and governance* of product knowledge, the open
side of the open-core line, and adds no execution, inference, or content
storage. A deterministic, advisory coverage signal over a human-declared
evidence reference; no new runtime, no AI, additive output (ADR-007).

## Problem

A requirement is a long-lived product capability — "what must remain true over
time?" (ADR-020). An end-to-end test asserts exactly that: it is the executable
evidence that a capability still holds. But RAC carries no link between a
capability and the external evidence that verifies it, so it cannot answer the
one question a verification workflow exists to ask: *which capabilities are
provably verified, and which are not?*

The existing traceability coverage report (`rac-traceability-coverage-report`)
reports typed gaps in the corpus-internal graph — requirements no roadmap
schedules, decisions nothing applies, roadmaps that scope no requirement. It
does not — and by itself cannot — report the gap between a capability and its
*verifying evidence*, because that evidence is an external artifact (a test
file, a CI trace) and not a RAC artifact (ADR-010, ADR-024). Teams and agents
increasingly generate e2e tests, but there is no deterministic, git-native,
reviewable record of capability → evidence, so coverage-of-intent — "14 of 19
live capabilities have a verifying test; these 5 do not" — is unanswerable
short of reading the corpus and the test suite by hand.

This capability supplies the missing link as a *declared, human-reviewed*
reference, and surfaces its completeness as advisory coverage — keeping every
property that makes RAC's graph trustworthy: deterministic, offline, and
human-declared (ADR-074, ADR-065, ADR-082).

## Requirements

- [REQ-001] A capability artifact (a requirement) MUST be able to declare a *verifying-evidence reference* to external test or trace evidence — a test file path, a suite/case identifier, or a CI trace URL — recorded as an asset reference (ADR-019), not as an edge to a RAC artifact. The target is external and untyped; RAC records and surfaces the reference and never requires the target to be a classified artifact (ADR-010, ADR-055 untyped-target exemption).
- [REQ-002] Verifying-evidence references MUST be human-declared and MUST NOT be auto-wired from prose or inferred by a model. An external tool or agent may *propose* a reference, but it becomes part of the corpus only through normal human PR review (ADR-065, ADR-074, ADR-082). RAC writes no evidence reference on its own.
- [REQ-003] RAC MUST extend the deterministic coverage report with an advisory `unverified-capability` gap class: a live requirement carrying no verifying-evidence reference. This gap MUST be distinct from orphan detection and from the unscheduled-requirement gap — a capability may be scheduled and non-orphaned yet still carry no verifying evidence (consistent with `rac-traceability-coverage-report` REQ-002).
- [REQ-004] The report MUST be deterministic and offline: identical corpus bytes produce an identical, ordered result across runs, with no AI/LLM/embeddings and no network (ADR-002, ADR-066).
- [REQ-005] Verification coverage MUST be advisory, never blocking: an unverified capability is a completeness signal for human judgement, not a validation error, and MUST NOT fail `rac validate`, `rac relationships --validate`, or `rac gate` on its own (ADR-075, ADR-082, ADR-049). A capability may legitimately precede the test that verifies it.
- [REQ-006] The capability → evidence reference and the coverage result MUST be exposed with human and JSON output (ADR-007); each entry MUST name the capability artifact and, where present, its verifying-evidence reference(s), and the JSON MUST be a stable, additive contract that does not alter existing payloads.
- [REQ-007] RAC MUST NOT execute, run, schedule, store, or judge the evidence it references. It records the human-declared link and reports completeness over it; running the test, capturing the video/trace, and deciding whether the test is *good* stay outside the engine (ADR-017 knowledge-not-work, ADR-024 not-a-content-store, ADR-002 AI-optional). The verifying-evidence reference is exported on the graph projection so an external consumer can act on it (ADR-074, ADR-063).
- [REQ-008] The coverage rule SHOULD derive its expectation (which artifact types are expected to carry verifying evidence) from the artifact specs and the relationship/asset registry rather than a hand-maintained per-type table, so adding an artifact type does not silently leave the rule stale (consistent with `rac-traceability-coverage-report` REQ-006).

## Acceptance Criteria

- A fixture corpus with a requirement that declares a verifying-evidence
  reference and another that declares none reports exactly the second as an
  `unverified-capability` gap; adding a reference to it clears the gap.
- A requirement that is scheduled by a roadmap and has inbound edges (not an
  orphan, not unscheduled) but carries no verifying-evidence reference is still
  reported as an `unverified-capability` gap — proving verification coverage is
  neither orphan detection nor schedule coverage.
- The report exits `0` when unverified capabilities are present (advisory), and
  `rac gate` does not fail on them.
- A verifying-evidence reference appears on `rac export --graph` as a reference
  from the capability to its external evidence target, with the target preserved
  literally and flagged external; it creates no phantom artifact node.
- Output is byte-identical across repeated runs on an unchanged corpus; no
  network access occurs.

## Success Metrics

- A maintainer (or a consuming agent) can list every live capability that lacks
  verifying evidence in one deterministic command, without reading the corpus or
  the test suite by hand.

## Risks

- Verifying-evidence references rot as tests move or are renamed, so a capability
  reads as verified when its evidence no longer exists. Mitigation: references
  are surfaced for human review like any reference; staleness of external evidence
  is a freshness concern (`freshness-and-drift-detection`), not solved here, and
  the reference is advisory.
- Teams treat an `unverified-capability` gap as an error and manufacture
  low-value tests to clear it. Mitigation: REQ-005 keeps the gap advisory and out
  of the enforcement gate; it is a signal, not a quota.
- The evidence reference is mistaken for a mandate that RAC run the test.
  Mitigation: REQ-007 fixes the boundary — RAC records and reports, never
  executes.

## Assumptions

- A human-declared asset reference (ADR-019) from a capability to external
  evidence is sufficient to compute verification coverage; no new artifact type
  and no test execution are required in the core.
- Verification coverage is advisory: teams decide which capabilities must be
  verified; RAC surfaces the gap, it does not enforce it.
- Producing the evidence (running browsers/terminals, capturing video/traces,
  converting a session into a durable test) is the job of an external consumer of
  the contract, not of `rac` (ADR-063, ADR-067).

## Related Decisions

- adr-012
- adr-019
- adr-020
- adr-074
- adr-084
- adr-065
- adr-082
- adr-055
- adr-066
- adr-002
- adr-007
- adr-017
- adr-024
- adr-010

## Related Requirements

- rac-traceability-coverage-report
- rac-traceability-self-relationships

## Related Designs

- capability-verification-evidence

## Related Roadmaps

- capability-verification-coverage
