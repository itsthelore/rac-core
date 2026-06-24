---
schema_version: 1
id: RAC-KVW63N804ZER
type: decision
---
# ADR-084: Verification Links Are External-Target Relationships

## Context

ADR-083 introduced Proofkeeper, which proposes `## Verified By` links from a
product capability to the tests and traces that verify it. The
`proofkeeper-autonomous-verification` roadmap requires those links to be *typed
edges in the graph export* (ADR-074) so a coverage consumer can read which
capabilities are verified.

Every relationship section in RAC today resolves its references against the
corpus index: a reference that matches no artifact is reported as
`relationship-target-not-found`, an error that fails `rac validate` and `rac
gate` (`relationships.py:_resolve_references`). That is correct for the
`related_*` and `supersedes` edges, whose targets are other corpus artifacts.

But Proofkeeper's `## Verified By` targets are **external**: Playwright test
files and replayable trace artifacts that live in the product's own repository,
not in the corpus. They are not RAC artifacts (ADR-010 — documents, and a
fortiori tests, are not artifacts). Modeling verification as an ordinary
resolving relationship would flag every real link as a broken reference.

This is the first relationship kind whose targets are external rather than
corpus artifacts. ADR-055 records that new relationship-type semantics are
captured in their own decision; this is that record.

## Decision

Introduce **external-target relationships** in the relationship-type registry
(ADR-055), and register `verified_by` as the first one.

An external-target edge is declared by an `external_target` property on its
registry entry, and the relationship engine treats it as follows:

- It is a recognized, typed relationship: it appears in `rac relationships` and
  as a typed edge in `rac export --graph` (ADR-074), carrying its registry kind
  and direction.
- It is **exempt from referential-integrity resolution**. An unresolved target
  is the expected case, never `relationship-target-not-found`. The edge is always
  emitted with `resolved: false` and the literal reference text as its target.
- It is exempt from range and status-consistency checks — it has no corpus
  target type, and even a reference that incidentally matches an artifact
  identifier is never resolved to it.
- It never creates an incoming edge and never contributes to corpus resolution.

`verified_by` is directional (capability → verifier), its inverse label is
`verifies`, it is declared by a `## Verified By` section, and it is legal on
**requirements** — the long-lived product capabilities (ADR-020). Designs or
other types may gain it in a later, separately recorded change; requirements are
the minimal, faithful source today.

The engine neither runs nor parses the referenced tests. It records the link as
Proofkeeper proposes it through a human-reviewed pull request (ADR-065).
Proofkeeper owns producing and running the evidence (ADR-083); RAC records and
reports it.

## Consequences

### Positive

- The `## Verified By` write-back validates cleanly with external targets, and a
  coverage consumer can read verification edges straight from the typed graph
  (ADR-074), with no test runtime in the engine (ADR-002).
- The `external_target` property generalizes: a future external link kind (for
  example a source-of-record URL) reuses the same exemption instead of carving a
  new special case.
- The boundary stays where ADR-083 put it — RAC records the link; it does not
  execute or verify the test.

### Negative

- A new contract surface — the `verified_by` edge kind and the `external_target`
  schema property — that is append-only and must stay stable (ADR-007).
- External targets are not checked for existence: a typo in a test path is not
  caught by RAC. It is caught downstream by the test runner and PR review, which
  is where ADR-065 already locates the trust boundary.

### Risks

- The exemption could be misused to smuggle unvalidated links of other kinds.
  Mitigation: `external_target` is set per edge kind in the code-defined registry
  (custom, repo-declared types remain deferred, ADR-055), and only `verified_by`
  carries it today.

## Status

Proposed

## Category

Technical

## Alternatives Considered

### Model `verified_by` as an ordinary resolving relationship

Treat it like `related_*` and resolve its targets against the corpus.

#### Disadvantages

- External test references resolve to nothing and are all flagged
  `relationship-target-not-found`, failing validation on every real link.
  Rejected — it defeats the feature.

### Represent each test as a corpus artifact

Author a Design (or a new artifact type) per verified test so the edge resolves.

#### Disadvantages

- Tests are not artifacts (ADR-010), and authoring a corpus artifact per test
  contradicts ADR-083's product model, where tests and traces live in the
  product repository. Rejected.

### Use an asset reference (ADR-019) instead of a relationship

Carry the link as embedded asset content rather than a typed edge.

#### Disadvantages

- Asset references are embedded-content references, not typed cross-artifact
  edges; the coverage graph needs a typed edge in `rac export --graph` (ADR-074).
  Rejected.

### Keep `## Verified By` as untyped prose (status quo)

Let the section stay ordinary text the engine ignores.

#### Disadvantages

- It is then invisible to the graph, so verification coverage cannot be computed
  — the roadmap's whole point. Rejected.

## Related Decisions

- adr-083
- adr-055
- adr-074
- adr-065
- adr-020
- adr-010
- adr-007

## Related Roadmaps

- proofkeeper-autonomous-verification
