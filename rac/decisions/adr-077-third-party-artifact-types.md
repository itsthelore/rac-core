---
schema_version: 1
id: RAC-KVTSPK4CJHWK
type: decision
tags: [extensibility, plugins, schema, sdk, architecture]
---
# ADR-077: Third-Party Artifact Types via Entry-Point Plugins (Schema Composition Over the Code-Defined Core)

## Status

Proposed

## Category

Architecture

## Context

RAC recognises five artifact types, defined once in a closed in-package registry
(`ARTIFACT_SPECS` in `core/artifacts.py`) and consumed in roughly eight places —
classification, validation, templates, schema, identity, relationships, and the
`inspect`/`portfolio` services. A team needing a sixth, domain-specific type has
no supported path but to fork the engine. The `rac-growth-extensibility`
requirement records the demand and a five-part contract (REQ-001..REQ-005):
discover third-party specs through a Python entry-point group, isolate their
failures, ship their templates as package resources, and let them participate in
every command through the same deterministic, section-heading mechanisms as
built-ins.

ADR-052 §5 deferred custom types post-PMF and named the intended path: "schema
composition over this code-defined core … recorded as its own ADR — never a
silent edit to an accepted decision." This ADR is that record. It does not ship
the engine change; it fixes the design so the decision is gate-validated corpus
knowledge before any code is written, and so the post-PMF / GATE-2 (CLA, ADR-071)
boundary stays intact. The companion Design
(`third-party-artifact-extensibility`) holds the implementation *how*.

Two recorded decisions constrain the shape. ADR-055 deferred custom *relationship*
types on the same boundary, so a custom artifact type must not smuggle in new
edge kinds. ADR-062 fixed the SDK surface as `rac.__all__` and keeps `ArtifactSpec`
internal, so publishing an extension point that hands plugin authors an
`ArtifactSpec` forces an explicit, recorded surface change rather than an implicit
one.

## Decision

1. **Discovery is entry-point based and absent-safe.** RAC discovers third-party
   specs through a declared entry-point group (`rac.artifact_specs`), resolved via
   `importlib.metadata`, loaded once and cached per process. Built-ins are always
   present; with no plugin installed every command's behaviour and output is
   byte-for-byte unchanged (REQ-001). The mechanism adds no mandatory dependency
   and imports nothing from a contributing package beyond its registered entry
   point (REQ-005), mirroring the `explorer` extra's lazy-import boundary.

2. **Built-ins always win; bad specs warn and skip.** A discovered object that is
   not a structurally valid `ArtifactSpec`, whose name collides with a built-in,
   or that duplicates an already-loaded third-party name, is reported as a warning
   and skipped — never crashing a command, never altering built-in behaviour
   (REQ-002). Warnings are emitted through Python's `warnings` machinery (a
   dedicated `ArtifactSpecWarning`), not the pinned stdout/stderr streams, so the
   golden CLI output contract holds when no plugin is installed.

3. **Templates load from the contributing package, deterministically.** A
   third-party type carries an optional reference to its own template resource
   (a `(package, resource)` pair); built-ins leave it unset and keep loading from
   `rac.templates` (ADR-021), unchanged. Loading stays inside RAC's
   `importlib.resources` path so RAC owns error mapping and offline determinism
   (ADR-002). A plugin-supplied loader callable is rejected — it would let
   arbitrary, possibly networked code run at template time and break that
   determinism.

4. **Custom types are first-class for knowledge, not for the graph (v1).** A
   loaded type participates in classification, validation, `rac schema`, and
   template listing through the existing section-heading mechanisms, with no
   artifact-specific branch in core (REQ-004): a registered type with no bespoke
   validator gets generic structural validation (title, required sections,
   status metadata) rather than the requirement fallback. A custom artifact may
   *reference* built-in types, but custom types are **not yet valid relationship
   targets and introduce no new edge kinds**. Auto-derived `related_<type>` edges
   stay deferred under ADR-055's lineage, liftable only by a future ADR if demand
   is proven. The known sharp edge — a built-in `## Related Decisions` reference
   that resolves to a custom-type artifact still flags a target-type mismatch — is
   accepted and tested as deliberate v1 behaviour.

5. **`ArtifactSpec` becomes a published, append-only contract.** Because the entry
   point hands plugin authors `ArtifactSpec`, it must be public: it is added to
   `rac.__all__` and re-exported from the top-level package, with an append-only
   field discipline (new fields are optional and appended; existing fields keep
   their meaning). This **extends ADR-062's surface explicitly** — recorded here
   rather than as a silent edit — and inherits ADR-062's pre-1.0 semantics.

6. **Determinism is preserved, not absolute.** The classifier stays deterministic
   and unchanged; installing a plugin whose section vocabulary overlaps a built-in
   can shift the best-fit type of a genuinely ambiguous document. This is inherent,
   bounded by the built-in-wins collision rules in decision 2, and stays
   explainable through `rac inspect`'s scored breakdown (ADR-002).

This decision is scope and shape only; nothing in `src/rac/` changes until the
work is scheduled, which remains gated post-PMF and behind GATE-2 (CLA) for any
public invitation.

## Consequences

### Positive

- The path ADR-052 promised exists as validated corpus knowledge: the five-part
  requirement now has a recorded mechanism, so the eventual implementation is a
  scoped build, not a fresh design.
- Open-core success measures in ADR-012 (community schemas, third-party tooling)
  gain a concrete, distribution-native mechanism without RAC hosting anything
  (ADR-024).
- The constant-to-registry seam and generic-validation routing are additive and
  reuse existing helpers, so built-in behaviour and the golden output contract are
  provably untouched when no plugin is present.

### Negative

- Publishing the entry-point group and `ArtifactSpec` creates two compatibility
  surfaces that constrain future refactors; the append-only discipline in
  decision 5 is the cost of that commitment.
- Entry-point loading runs third-party code at CLI start-up; failure isolation
  (decision 2) bounds correctness failures but not latency, so a slow plugin still
  taxes every invocation until a future opt-out is considered.

### Neutral

- Per-type JSON that enumerates counts becomes additive: a custom type's key
  appears only when its plugin is installed, consistent with ADR-007.
- Custom relationship types remain deferred (ADR-055); this ADR deliberately does
  not widen the graph layer.

## Alternatives Considered

- **A repo-local config file of custom types (`.rac/types.yaml`).** Rejected:
  duplicates the entry-point discovery the `explorer`/`ingest` extras already model,
  and turns the type set into per-checkout configuration rather than installed,
  versioned capability (ADR-024).
- **An authoritative JSON Schema dialect with `allOf` composition (the original
  hardening brief).** Rejected by ADR-052 already; this ADR keeps the code-defined
  envelope and composes over it.
- **Plugin-supplied template loader callables.** Rejected (decision 3): breaks
  offline determinism and RAC's deterministic error mapping.
- **Auto-deriving a `related_<type>` edge for every registered custom type.**
  Rejected for v1: it would introduce new edge kinds at runtime, make
  graph-integrity checks depend on installed plugins, and contradict ADR-055's
  code-defined relationship registry.

## Related Decisions

- adr-052
- adr-055
- adr-062
- adr-021
- adr-007
- adr-002
- adr-012
- adr-024
- adr-068

## Related Requirements

- rac-growth-extensibility

## Related Designs

- third-party-artifact-extensibility
