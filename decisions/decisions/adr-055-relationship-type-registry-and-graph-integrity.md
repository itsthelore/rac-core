---
schema_version: 1
id: RAC-KV3WXTPPWR2G
type: decision
tags: [relationships, enforcement, graph, schema]
---
# ADR-055: A Code-Defined Relationship-Type Registry and Layer-3 Graph Integrity

## Status

Proposed

## Category

Architecture

## Context

ADR-049 names cross-artifact validation as RAC's core, and the relationship
checks shipped so far — referential integrity, edge-legality (v0.14.0, domain
only), and decision-only status-consistency (v0.14.1) — cover most of it. But
the edge rules are *implicit*: legality is derived from each type's
``ArtifactSpec.optional`` (which sections a type may declare), and there is no
declarative statement of an edge's target type, directionality, or whether it
may form a cycle. Three gaps follow: a ``## Related Decisions`` reference that
resolves to a requirement is accepted silently (no **range** check); a
``supersedes`` cycle is undetected (no **acyclicity**); and the supersedes
exemption in the status rule is a hard-coded special case.

This decision interprets the relationship model (ADR-016, which lists "cycles
where relevant" among the things RAC should report), the enforcement posture
(ADR-049), and the generalized lifecycle status (ADR-051). It records how RAC
makes the edge schema declarative and closes the range and acyclicity gaps —
without the custom-type machinery ADR-052 defers.

## Decision

1. **A code-defined relationship-type registry** (``rac.core.relationship_types``)
   declares, per built-in edge kind, its ``range`` (allowed target types),
   ``directional``/``acyclic``/``symmetric`` flags, an ``inverse`` label, a
   ``forbids_target_status`` flag, and ``cardinality``. The ``related_*`` edges
   are undirected links whose target must be of the named type; ``supersedes`` is
   the one directional, acyclic, decision→decision edge.

2. **Domain stays ``ArtifactSpec.optional``** (v0.14.0's recorded source of
   truth). The registry adds only the *graph* properties; it does not move or
   duplicate domain legality.

3. **Range is enforced.** A uniquely-resolved reference whose target is a
   *recognized* artifact of a type outside the edge's ``range`` is reported as
   ``relationship-target-type-mismatch``. An **untyped** target is exempt
   (ADR-010): it is a legitimate document, owned by referential integrity, not a
   range violation.

4. **Acyclicity is enforced** for edge kinds marked ``acyclic`` (today
   ``supersedes``). A strongly-connected component larger than one node is a
   cycle and is reported once as ``relationship-cycle`` with the component's
   paths, deterministically (Tarjan over sorted nodes).

5. **The supersedes exemption becomes data-driven.** The status-consistency rule
   (generalized to all types by ADR-051) fires for any edge whose
   ``forbids_target_status`` is true; ``supersedes`` sets it false, replacing the
   former hard-coded ``section == "supersedes"`` check.

6. **``inverse``/``symmetric``/``cardinality`` are declared but not yet enforced**
   — they document the graph for display and forward compatibility (a viewer can
   label inverse edges). Enforcing cardinality or materializing inverse edges is a
   later, separately recorded decision.

7. **Custom, repo-declared relationship types are deferred** (ADR-052 defers the
   analogous custom artifact types). The registry is code-defined; a repo-local
   ``.rac/relationships.yaml`` is explicitly out of scope until a design partner
   needs it, at which point it is recorded as its own ADR.

## Consequences

### Positive

- The repository is validated *as a graph*: wrong-target-type edges and illegal
  cycles are caught at write time, in CI — checks no single-file validator has.
- The edge schema is one declarative source instead of scattered special cases;
  the supersedes exemption and the new rules all read the registry.
- Additive (ADR-007): existing relationship codes and their shapes are unchanged;
  ``relationship-target-type-mismatch`` and ``relationship-cycle`` are new.

### Negative

- Two more relationship rules to keep deterministic and false-positive-free. The
  untyped-target range exemption is the main judgment call (kept conservative,
  ADR-016 Risk 4).

### Neutral

- The vocabulary is unchanged (``related_*`` + ``supersedes``); new directional
  edge types (``depends-on``, ``refines``) remain reserved (ADR-016 Risk 5).

## Alternatives Considered

- **A repo-local ``.rac/relationships.yaml`` registry enabling custom edges now.**
  Deferred: it is the analog of the custom artifact types ADR-052 deferred;
  built-in graph integrity is the load-bearing work, custom edges are pull-based.
- **Add new directional edge types to exercise the rules.** Rejected for now:
  ADR-016 Risk 5 asks new types be justified by user value; ``supersedes`` and
  ``related_*`` already demonstrate acyclicity, range, and status-consistency.
- **Enforce range against untyped targets too.** Rejected: it would fail
  legitimate references to ADR-010 documents (e.g. loose design notes), an
  over-strict result; referential integrity already owns those edges.
- **Keep the supersedes exemption hard-coded.** Rejected: a registry flag makes
  the exemption declarative and generalizes cleanly with ADR-051.

## Related Decisions

- ADR-049
- ADR-016
- ADR-051
- ADR-052
- ADR-010
- ADR-007
- ADR-002

## Related Requirements

- rac-cross-artifact-enforcement
- rac-traceability-self-relationships
