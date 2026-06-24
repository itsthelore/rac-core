---
schema_version: 1
id: RAC-KVW0JBS1AE6P
type: design
---
# Capability Verification Evidence and Coverage

## Status

Proposed

Exploratory — the implementation contract for the
`rac-capability-verification-evidence` requirement and the open-core half of
ADR-083. Gated on ADR-083 being accepted; the runtime/commercial halves it
references are out of scope here and out of `rac-core`.

## Context

This design is the *how* for one question: which live product capabilities carry
external evidence that verifies them, and which do not — answered
deterministically, offline, and without RAC ever running a test.

The machinery already exists and is reused, not reinvented:

- **Asset references (ADR-019)** already connect an artifact to external
  supporting material via standard Markdown links, treated as a relationship to a
  non-artifact target and viewer-agnostic. A verifying-evidence reference is an
  asset reference whose target happens to be a test or a trace.
- **The coverage report (`rac-traceability-coverage-report`)** already computes
  typed, advisory, deterministic gap classes over the corpus. This adds one more
  class; it does not build a new report.
- **The graph export (`rac export --graph`, ADR-074) and the export-shape
  contract** already preserve external/unresolved references literally without
  inventing phantom nodes. The verifying-evidence reference rides the same rail.
- **The suggested-edges discipline (ADR-082, ADR-065, ADR-074)** already settled
  that links are human-declared and advisory, never auto-wired. Evidence
  references inherit that discipline exactly.

The one genuinely new thing is the *declaration site* — where a capability names
its evidence — and one new coverage class. Everything else is plumbing already in
the engine.

## User Need

- A **maintainer** wants to ask "what have we decided must stay true that nothing
  proves still works?" and get a deterministic list — coverage *of intent*, not
  coverage of files.
- A **consuming QA product** (out-of-core, ADR-083) needs to read which
  capabilities lack evidence (`rac export --graph`), generate tests against them,
  and *propose* evidence references back into the corpus through a PR — never
  writing the corpus directly.
- A **reviewer** wants to verify an agent's verification work by reading the
  declared evidence reference and the test it points at, with no local run.

The check must never run a test, never block CI, and never need a model or
network — it runs in the same offline, deterministic pass as the rest of `rac`.

## Design

### The declaration site — `## Verified By`

A capability artifact (initially a requirement) may carry a `## Verified By`
section whose entries are asset references (ADR-019) — standard Markdown links to
external evidence:

```markdown
## Verified By

- [checkout-flow e2e](../../tests/e2e/checkout.spec.ts)
- [cart total assertion](../../tests/e2e/cart.spec.ts#L42)
- [prod smoke trace](https://ci.example.com/runs/8842/trace)
```

- The **link text** is a human-readable evidence label (a suite/case name); the
  **target** is the evidence — an in-repo test file/path, a path with a line or
  case anchor, or an external CI/trace URL.
- `## Verified By` is deliberately **distinct from `## Related <Type>`**. The
  `## Related` sections carry artifact↔artifact edges that the relationship
  registry range-checks (ADR-055); `## Verified By` carries artifact↔external
  links whose target is not a RAC artifact (ADR-010, ADR-024) and is therefore
  range-exempt, parsed on the asset-reference rail, not the edge rail.
- The section is **optional and additive** (ADR-007): an artifact without it is
  valid, and its absence is exactly what the coverage class reports.

### The coverage class — `unverified-capability`

`rac coverage` gains one advisory gap class: a **live** requirement (Accepted /
non-retired) carrying no `## Verified By` reference.

- It is **distinct from** the `unscheduled-requirement` and orphan classes — a
  capability can be scheduled, non-orphaned, and richly linked yet still carry no
  verifying evidence. The discriminator is the presence of an evidence reference,
  nothing else.
- It is **advisory and exits zero** (ADR-082, ADR-075, ADR-049): it never fails
  `rac validate`, `rac relationships --validate`, or `rac gate`. A capability may
  legitimately precede the test that verifies it.
- Output carries human and JSON form (ADR-007); each entry names the capability
  path/id and its evidence reference(s) where present. JSON is a stable additive
  contract that does not alter existing coverage payloads.
- The rule reads which types are expected to carry evidence from the artifact
  specs/registry, not a hand-maintained table (mirrors
  `rac-traceability-coverage-report` REQ-006).

### Reference integrity — what RAC checks, and what it deliberately does not

- **In-repo evidence targets** (a test file path) are checkable offline: the
  existing asset-reference validation (ADR-019's "referenced asset exists" future
  consideration) reports a broken in-repo evidence path the same advisory way it
  reports any broken asset. A missing test file is a stale reference, surfaced for
  human review.
- **External evidence targets** (a CI/trace URL) are **not** network-checked —
  the core is offline (ADR-002). They are recorded and surfaced, never fetched.
- RAC **never** runs the test, parses its result, stores its video/trace, or
  judges whether the test is adequate (ADR-017, ADR-024). "Is the capability
  *actually* verified right now?" is a runtime question owned by the consuming
  product; RAC answers only "does a human-declared evidence reference exist, and
  does an in-repo target resolve?"

### The export seam — handing the work to the consuming product

`rac export --graph` surfaces each `## Verified By` reference in a **separate
`asset_edges` list**, distinct from the registry `edges[]` array — the full wire
contract is fixed in **ADR-084**, which this design defers to (the
`corpus-export-shape-contract` design reserved "its own short ADR" for exactly this
extension):

```json
{"source":"RAC-KVW05N861478","target":"tests/e2e/checkout.spec.ts",
 "kind":"verified-by","target_kind":"path","present":true}
```

- The target is preserved **literally** and is **never a node** (ADR-074,
  `rac-corpus-graph-export` REQ-004); it is external to the corpus (ADR-010,
  ADR-024).
- It rides `asset_edges`, **not** `edges[]` — the registry-edge array keeps its
  Accepted `{source, target(canonical id), type, directed}` shape untouched
  (ADR-084). `present` is `true`/`false` for an in-repo path and `null` for a URL
  (offline, ADR-002), replacing the registry `resolved` flag whose meaning does not
  apply to an external target.
- The default `rac export` payload and the viewer `relates-to` contract are
  **unchanged**; the `--graph` `schema_version` bumps `"1" → "2"` to advertise
  `asset_edges` (ADR-007, ADR-074, ADR-084).
- This is the seam the out-of-core QA product consumes: read the graph, find
  capabilities with no `verified-by` edge, generate tests, open a PR adding
  `## Verified By` lines — which a human reviews and merges (ADR-065, ADR-067,
  ADR-063). RAC supplies context and records the result; it never executes.

### Determinism

Coverage and export are pure over corpus bytes: same corpus → byte-identical
output, sorted (by source path, then target), proven by golden tests. No model,
embedding, or network call is on the path (ADR-002, ADR-066).

## Constraints

- Offline, AI-optional (ADR-002), deterministic with no embeddings or LLM judge
  (ADR-066): pure function of corpus bytes.
- Knowledge, not work (ADR-017); not a content store (ADR-024): RAC records and
  reports the evidence reference; it never runs, schedules, stores, or judges the
  evidence.
- Declared, not inferred (ADR-074, ADR-065, ADR-082): evidence references are
  human-authored and human-reviewed; RAC writes none on its own.
- Advisory severity (ADR-075, ADR-049): the coverage class and any broken-target
  finding exit zero and never change the validate/gate contract.
- Additive contract (ADR-007): a new optional section, a new coverage class, a new
  export edge type; no existing payload changes.
- Reuse, don't reinvent: asset-reference parsing/validation, the coverage service,
  the graph export, and the shared Markdown parser are reused, not duplicated.

## Rationale

Modelling evidence as an asset reference (ADR-019) rather than a new relationship
edge type is the load-bearing choice: a test is not a RAC artifact (ADR-010), so
an artifact↔artifact edge is the wrong primitive — it would fail range checks and
imply a node that should not exist. Asset references already mean "a link to
external supporting material," which is exactly what verifying evidence is. That
keeps the whole feature on rails the engine already has, and keeps RAC on the
correct side of every boundary: it makes the *validated* knowledge graph report
coverage of intent, without becoming a test runner, a content store, or an
inference engine.

## Alternatives

- **A new `verified_by` relationship *edge* type in the registry (ADR-055).**
  Rejected: the target is not a RAC artifact, so it is not an artifact edge; it
  would fight range checks and the no-phantom-node rule. Asset references are the
  right primitive.
- **Store test results / videos in RAC and report real pass/fail.** Rejected by
  ADR-024 (not a content store) and ADR-017 (not work); the consuming product owns
  execution and results.
- **Auto-discover tests and wire evidence automatically (scan the test dir, match
  by name).** Rejected by ADR-082/ADR-065: an unreviewed link is not a validated
  one. RAC may *suggest* (the mentioned-but-unlinked detector is the precedent)
  but never auto-wire.
- **Make `unverified-capability` a hard gate failure.** Rejected by ADR-075: it
  would force premature or busywork tests and turn a completeness signal into a
  merge blocker.
- **Network-check external evidence URLs for liveness.** Rejected by ADR-002:
  the core is offline; liveness/freshness of external evidence is the consuming
  product's concern (and a `freshness-and-drift-detection` adjacency).

## Accessibility

Output is plain text, readable and diffable, in the same shape as existing
`rac coverage` gaps: each entry states the capability and its evidence references
in words, no reliance on colour or a graphical display. `--json` carries the same
fields for automation.

## Style Guidance

Each coverage entry leads with the capability and the gap ("no verifying evidence
declared"), matching the tone of the existing coverage gaps. The `## Verified By`
section uses plain Markdown links so it renders identically on GitHub, in IDEs,
and in the Portal (ADR-019 Principle 3). Copy frames an unverified capability as a
*completeness signal to review*, never as a failure.

## Open Questions

- **Which artifact types may declare `## Verified By`.** Requirements are the
  clear first case (capabilities, ADR-020). Whether a roadmap increment or a
  design may also carry evidence is deferred.
- **Anchor grammar for in-repo targets.** Whether to standardise a `#Lnn` /
  `#case-name` anchor convention for pointing at a specific test case, or leave
  the target opaque and let the consuming product interpret it.
- **Suggested evidence.** Whether `rac doctor` should *suggest* a likely test
  file for an unverified capability (the mentioned-but-unlinked precedent),
  strictly as an advisory suggestion a human promotes.
- **Second surface.** Whether `rac doctor` should also surface broken in-repo
  evidence targets, or whether keeping evidence reporting in `rac coverage` is
  clearer.

## Related Decisions

- adr-083
- adr-084
- adr-019
- adr-020
- adr-074
- adr-082
- adr-065
- adr-055
- adr-024
- adr-017
- adr-010
- adr-002
- adr-066
- adr-007

## Related Requirements

- rac-capability-verification-evidence
- rac-traceability-coverage-report

## Related Roadmaps

- capability-verification-coverage
