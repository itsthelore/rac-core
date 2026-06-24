---
schema_version: 1
id: RAC-KVW5PYBN4A2G
type: decision
tags: [export, graph, asset-references, contract, verification]
---
# ADR-084: Asset-Reference Edges Are a Separate `asset_edges` List in the Graph Export

## Context

The capability-verification work (`rac-capability-verification-evidence`, design
`capability-verification-evidence`, ADR-083) introduces a *verifying-evidence
reference*: a human-declared link from a capability artifact to **external** test
or trace evidence (a file path or a CI/trace URL), recorded as an asset reference
(ADR-019). For the out-of-core consumer (`lore-verify`) to read its worklist, that
reference must appear on `rac export --graph`.

A first draft of the verification design surfaced it as an entry in the existing
`edges[]` array with a one-off shape (`{source, target, type:"verified-by",
external:true, resolved:true}`). That is **wrong** — it contradicts the Accepted,
shipped (`v0.25.0`) `--graph` contract:

- `rac-corpus-graph-export` REQ-002 and the `corpus-export-shape-contract` design
  fix every `edges[]` entry as `{source, target(canonical id), type(from the
  ADR-055 relationship registry), directed(from the registry)}`.
- `corpus-export-shape-contract` states plainly that **asset references (ADR-019)
  are out of scope** for that projection.
- A `verified-by` link has no registry type and no registry `directed` flag; its
  target is an external path/URL, not a canonical artifact id, so it must create
  no node (ADR-074, REQ-004); and `resolved` already has a fixed meaning —
  *"a reference that resolved to a corpus artifact"* — not *"a path exists on
  disk."*

Putting an asset edge into `edges[]` would mutate the meaning of a locked array,
drop a required field, and overload `resolved` — breaking the additive promise of
ADR-007. The `corpus-export-shape-contract` design anticipated this exact moment:
"this projection carries **its own short ADR** when it is scheduled." This is that
ADR, extended to cover the asset-reference case the typed-edge work surfaced.

## Decision

Asset-reference edges are surfaced on `rac export --graph` as a **separate,
additive top-level `asset_edges` list**, distinct from the registry `edges[]`
array, which is left exactly as the Accepted contract defines it.

```json
{"schema_version":"2","source":"rac",
 "nodes":[ ... unchanged ... ],
 "edges":[ ... unchanged: registry edges only, with type + directed ... ],
 "asset_edges":[
   {"source":"RAC-KVW05N861478","target":"tests/e2e/checkout.spec.ts",
    "kind":"verified-by","target_kind":"path","present":true},
   {"source":"RAC-KVW05N861478","target":"https://ci.example.com/runs/8842/trace",
    "kind":"verified-by","target_kind":"url","present":null}
 ]}
```

- **`source`** is always a canonical artifact id (a node in `nodes[]`).
- **`target`** is the literal asset reference, preserved verbatim, and is **never**
  a node — it is external to the corpus (ADR-010, ADR-024).
- **`kind`** is the asset-reference category from a small, code-defined
  asset-kind set (initially just `verified-by`), **not** the ADR-055 relationship
  registry. The registry is for artifact↔artifact edges and is **not** extended by
  this decision; asset edges are a parallel category.
- **`target_kind`** is `"path"` (in-repo) or `"url"` (external), discriminated
  deterministically by the literal target.
- **`present`** is `true`/`false` for an in-repo `path` (does the file exist on
  disk), and **`null`** for a `url` (never network-checked — the core is offline,
  ADR-002). It deliberately replaces the registry `resolved` flag, whose meaning
  ("matched a corpus artifact") does not apply to an external target.
- Asset edges carry **no `directed` field**: direction is intrinsic (always
  capability → evidence), and omitting it keeps the asset shape visibly distinct
  from a registry edge rather than masquerading as one.

**Versioning.** Adding `asset_edges` is additive (a new optional top-level key);
existing readers of `edges[]`/`nodes[]` are unaffected. The `--graph` projection's
`schema_version` bumps `"1" → "2"` so a consumer can detect support. A consumer
MUST treat the *absence* of `asset_edges` on a `schema_version:"1"` payload as
"asset-edge data not provided by this producer," **not** as "this capability has no
evidence" — the two are different, and conflating them would invent false coverage.
The viewer JSON's `relates-to` contract and the `--documents` projection are
unchanged (ADR-007, ADR-074).

## Consequences

The verification read seam has a real, contract-clean shape that both the producer
(`rac export --graph`) and the consumer (`lore-verify`) build against, without
touching the locked registry-edge array. The cost is a second edge list in the
graph payload; it is the honest representation, because an asset edge genuinely is
a different kind of thing from a typed relationship edge. Determinism holds: like
`edges[]`, `asset_edges` is sorted (by `source`, then `target`) with no
timestamps (ADR-002, ADR-066), and gains its own golden-output and viewer
byte-stability test, as ADR-074 required for the typed edges.

## Status

Proposed

## Category

Technical

## Alternatives Considered

- **Put asset edges in the existing `edges[]` array** (the rejected first draft).
  Rejected: mutates a locked, Accepted contract — a non-registry `type`, a dropped
  `directed`, an overloaded `resolved`, and a non-node target — breaking ADR-007's
  additive promise and `corpus-export-shape-contract`'s explicit asset-out-of-scope
  rule.
- **Extend the ADR-055 relationship registry with a `verified-by` edge type.**
  Rejected: the registry governs artifact↔artifact edges with range and direction;
  an asset reference targets a non-artifact, fails range, and has no registry
  direction. Asset edges are a parallel category, not a registry edge (this is the
  same conclusion the verification design reached for the declaration site).
- **Do not surface asset edges on the graph at all; expose a dedicated
  `rac coverage --json` worklist only.** Rejected as the sole mechanism: the graph
  export is the established machine seam graph consumers already read (ADR-074,
  ADR-063); `rac coverage` remains the human/advisory surface, but the consumer
  reads the graph. (They are complementary, not exclusive.)
- **Keep `schema_version:"1"` and rely purely on additivity.** Rejected: without a
  version signal a consumer cannot distinguish a producer that omits `asset_edges`
  from a corpus with no evidence; the bump makes capability detection explicit.

## Related Decisions

- adr-074
- adr-019
- adr-055
- adr-007
- adr-083
- adr-066
- adr-002
- adr-010
- adr-024

## Related Requirements

- rac-capability-verification-evidence
- rac-corpus-graph-export

## Related Designs

- capability-verification-evidence
- corpus-export-shape-contract

## Related Roadmaps

- capability-verification-coverage
