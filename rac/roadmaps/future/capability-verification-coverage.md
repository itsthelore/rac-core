---
schema_version: 1
id: RAC-KVW05PP7B00K
type: roadmap
---
# RAC — Capability Verification Coverage (Future)

## Status

Planned

Unscheduled — captured for future consideration. It delivers the open-source
half of the autonomous-QA direction recorded in ADR-083: a deterministic,
git-native record of which product capabilities carry verifying evidence, and an
advisory coverage signal over it. It graduates out of `future/` into a versioned
series when prioritised. The execution/runtime half (browsers, terminals, VMs,
video, faithful session-to-test conversion) is deliberately **not** in this
roadmap and not in RAC — it is a separate consuming product (ADR-083).

## Context

`rac-capability-verification-evidence` records the capability: a requirement (a
long-lived product capability, ADR-020) should be able to declare a
*verifying-evidence reference* to external test or trace evidence, and RAC should
report — deterministically and advisorily — which live capabilities have such
evidence and which do not. This is the in-domain, open-core piece of the QA
direction (ADR-012): it improves the understanding and governance of product
knowledge and adds no execution, inference, or content storage.

It extends, rather than duplicates, work the corpus already records: the
traceability coverage report (`rac-traceability-coverage-report`) for the gap
machinery, asset references (ADR-019) for the external-evidence link, the graph
export (`rac export --graph`, ADR-074) for surfacing the reference to consumers,
and the suggested-edges discipline (ADR-082) for keeping every link
human-declared.

## Outcomes

- A capability can carry a human-declared, reviewable reference to the external
  evidence that verifies it, recorded as an asset reference (ADR-019) — never an
  auto-wired or model-inferred link (ADR-082, ADR-065, ADR-074).
- `rac coverage` gains an advisory `unverified-capability` class so a maintainer
  or a consuming agent can list, in one deterministic command, every live
  capability with no verifying evidence — distinct from orphan and
  unscheduled-requirement gaps.
- `rac export --graph` surfaces verifying-evidence references so an external
  consumer (a QA agent or runner) can read which capabilities to test and write
  proposed evidence links back through a PR.
- The boundary stays intact: RAC records and reports the link; it never runs,
  stores, or judges the evidence (ADR-017, ADR-024, ADR-002).

## Initiatives

### Initiative 1 — Verifying-evidence references on capabilities

Extend the asset-reference mechanism (ADR-019) so a requirement can declare a
verifying-evidence reference to an external target — a test file path, a
suite/case identifier, or a CI trace URL. The target is external and untyped, so
the range check exempts it (ADR-055); referential integrity treats it as a
preserved external reference, never a phantom artifact node. No new artifact type
is introduced.

### Initiative 2 — `unverified-capability` advisory coverage class

Add a new gap class to the deterministic coverage report
(`rac-traceability-coverage-report`): a live requirement carrying no
verifying-evidence reference. Deterministic and offline (ADR-002, ADR-066),
advisory and out of the enforcement gate (ADR-075, ADR-049, ADR-082), with human
and JSON output as a stable additive contract (ADR-007). The expectation derives
from the artifact specs / registry, not a hand-maintained table.

### Initiative 3 — Surface evidence references on the graph export

Emit verifying-evidence references on `rac export --graph` (ADR-074) so an
external consumer can act on them: read the capabilities that need verifying,
and propose evidence links back into the corpus for human review (ADR-063,
ADR-067). The default `rac export` payload is unchanged; the addition is
additive.

## Success Measures

- `rac coverage` lists every live capability with no verifying-evidence
  reference, deterministically and byte-identically across runs, exiting `0`.
- Adding a verifying-evidence reference to a capability clears its
  `unverified-capability` gap, and the reference appears on `rac export --graph`.
- `rac gate`, `rac validate`, and `rac relationships --validate` are unaffected
  by the presence of unverified capabilities (advisory only).
- No network access and no model invocation occur on any path added here.

## Assumptions

- A human-declared asset reference is sufficient to compute verification
  coverage; no test execution belongs in the core (ADR-017, ADR-024).
- The evidence producer — the QA agent/runner that drives browsers and terminals
  and converts a session into a durable test — is an external consumer of the
  contract (ADR-083, ADR-063), scheduled separately if at all.
- ADR-083 is accepted before this work ships; it is Proposed until then.

## Risks

- Scope creep toward executing or scheduling tests inside `rac`. Mitigation: the
  boundary is recorded in `rac-capability-verification-evidence` REQ-007 and
  ADR-083; this roadmap delivers references and coverage only.
- Evidence references rot as external tests move. Mitigation: out of scope here;
  staleness of external targets is the concern of `freshness-and-drift-detection`,
  and the reference is advisory.
- The coverage class is read as a mandate and drives busywork tests. Mitigation:
  advisory severity and gate exclusion (Initiative 2).

## Related Decisions

- adr-083
- adr-012
- adr-019
- adr-020
- adr-074
- adr-082
- adr-065
- adr-002
- adr-007
- adr-017
- adr-024

## Related Requirements

- rac-capability-verification-evidence
- rac-traceability-coverage-report

## Related Designs

- capability-verification-evidence

## Related Roadmaps

- freshness-and-drift-detection
