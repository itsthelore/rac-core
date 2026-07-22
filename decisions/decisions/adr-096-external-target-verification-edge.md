---
schema_version: 1
id: RAC-KWBJJRZR84PT
type: decision
---
# ADR-096: External-Target Verification Edge (`verified_by`)

## Context

The graph export surfaces the corpus as typed nodes and edges (ADR-074) for
graph backends and external consumers. The relationship registry (ADR-055) is
code-defined and resolves each edge's target to an in-corpus artifact, except
for the external-reference family (ADR-087), where the target is an external
identifier — today a ticket — that is exempt from resolution, range, and
status checks and is marked `external`/unresolved in the export.

A sibling product, Proofkeeper, is a contract consumer of the graph export
(ADR-063): it reads `rac export --graph` to learn which product capabilities
(requirements, ADR-020) have a verifying test, and proposes linking a capability
to the test that verifies it through a human-reviewed pull request (the trust
boundary, ADR-065). For that to work the corpus needs a typed way to record
"this capability is verified by this test/trace" — a link whose target is a
**file path outside the corpus** (a `.spec.ts`, a trace artifact), not a peer
artifact and not a ticket.

The external-reference machinery added for tickets (ADR-087) already models an
edge whose target deliberately does not resolve to a local artifact. A
verification link is the same shape with one difference: its target is a file
reference, which has no ticketing provider. Without a typed edge, verification
links would sit in prose and go stale, and the graph export — the published
contract — could not carry the signal a verification consumer needs.

## Decision

Introduce a single **external-target verification edge**, `verified_by`,
declared via a `## Verified By` section, legal **only on requirements**
(capabilities, ADR-020).

- **External target, no provider.** Like `related_tickets` it is `external`:
  exempt from referential-integrity resolution, range, and status-consistency
  checks, and emitted in the graph export with `resolved: false` and the literal
  reference text as `target`. Unlike `related_tickets` it is **not**
  provider-tagged — its targets are test/trace file paths, so the export's
  `provider` is `null`. The registry distinguishes the two with an
  `external_provider` flag; only ticket edges carry the configured ticketing
  provider (ADR-088).
- **Directional capability→verifier.** The edge is directional with the declared
  inverse `verifies` (display only, not enforced, per ADR-055).
- **Requirement-only.** `## Verified By` is added to the requirement artifact
  spec's optional sections; declared on any other type it is an unsupported edge
  (`relationship-edge-unsupported`, ADR-049), exactly as for any mis-placed
  relationship section.
- **Engine scope is the edge only.** RAC emits and validates the edge; it does
  not run tests or compute verification coverage. Deriving "which capabilities
  are unverified" from the edge is the consumer's concern (Proofkeeper), keeping
  RAC a knowledge engine, not a test runner (ADR-017).

The graph `schema_version` is unchanged: this is an additive edge kind, and the
export shape (`type`, `external`, `resolved`, `provider`) is the existing one
(ADR-007, ADR-074).

## Consequences

- A capability can carry a typed, durable link to the evidence that verifies it,
  surfaced in the published graph contract for any consumer — verification
  coverage becomes derivable without RAC owning test execution.
- The external family now has two members (ticket, verification); the
  `external_provider` flag keeps provider tagging correct for each, so a
  verification edge is never mislabelled with a ticketing provider.
- `## Verified By` on a non-requirement is reported as an unsupported edge, so
  the section stays where capabilities live (ADR-020).
- A new relationship kind is one more thing the registry carries; it is additive
  and rides the existing external-edge code paths, so the blast radius is small.

## Status

Accepted

## Category

Technical

## Alternatives Considered

- **Reuse `related_tickets` for verification links.** Rejected: a test path is
  not a ticket; it would be linted against the ticketing provider's key format
  and mislabelled with that provider in the export.
- **A general in-corpus edge to a "test" artifact type.** Rejected: tests are
  external files, not corpus artifacts (ADR-010); inventing a test artifact type
  would pull execution evidence into the knowledge corpus, against ADR-017/ADR-024.
- **Let the consumer infer verification from prose or naming conventions.**
  Rejected: undurable and unvalidated; the point of a typed edge is a stable,
  machine-readable contract (ADR-074).
- **Compute verification coverage inside RAC.** Rejected: RAC manages knowledge,
  not work or test execution (ADR-017); coverage derivation belongs to the
  consumer over the published contract (ADR-063).

## Related Decisions

- ADR-074
- ADR-087
- ADR-063
