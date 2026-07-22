---
schema_version: 1
id: RAC-KW47GGS85CKG
type: decision
---
# ADR-087: External-Reference Relationships (Jira and Beyond)

## Status

Accepted

## Category

Technical

## Context

Change traceability in many organisations runs through a ticketing system —
Jira, GitHub Issues, Linear, Azure DevOps, ServiceNow. Without a typed way to
link an artifact to its ticket, teams jam ticket IDs into prose and the link
goes stale; with one, the corpus gains regulator-grade traceability — "this ADR
implements this ticket" becomes a typed edge.

The relationship registry (ADR-055) is code-defined and enforces each edge's
range to in-corpus artifact types; resolution is deterministic and Git-native
(ADR-016). A ticket is not an artifact, so it cannot be a normal edge target.
ADR-052 defers fully custom, repo-declared edge kinds. ADR-010 already
recognises that untyped targets exist and are legitimate. The need is a typed,
lintable link to an *external* system that deliberately does not resolve to a
local artifact.

A key observation shapes the design: **an organisation standardises on one
ticketing system.** It is rare for a corpus to reference Jira *and* GitHub *and*
Linear at once. So the system is a per-repository choice, not a set of always-on
edges the author must pick between — and that choice belongs in repository
configuration set at `rac init` (ADR-088), the same place the repository key
lives.

## Decision

Introduce a single **external-reference relationship edge**, `related_tickets`
(declared via `## Related Tickets`), whose target is an external ticket rather
than an in-corpus artifact — explicitly exempt from artifact-range resolution
(the ADR-010 untyped-target shape, generalised). The ticketing **provider is
per-repository configuration**, not a per-provider edge.

- **One section, one edge.** `## Related Tickets` is recognised on all five
  artifact types. There is no `## Related Jira` / `## Related GitHub` /
  `## Related Linear` proliferation: the heading is stable across every repo, and
  the system it points at is named once, centrally, in config.
- **Provider is config (ADR-088).** `.rac/config.yaml` carries
  `ticketing.provider`, one of `jira`, `github`, `linear`, `azure-devops`,
  `servicenow`, or `none`, written by `rac init --ticketing <provider>`. Adding a
  provider is a code change (a format validator), not a new ADR each time.
- **Syntax:** one item per line — a provider-specific key or a full URL (e.g.
  Jira `PROJ-1234`, GitHub `owner/repo#123`, Linear `ENG-123`, Azure DevOps
  `1234`/`AB#1234`, ServiceNow `INC0010023`).
- **Engine scope is format-lint only.** `rac validate` checks each entry against
  the configured provider's key/URL format, deterministically and offline, and
  flags malformed entries (`malformed-ticket-reference`, overridable per
  ADR-053). With no provider configured the section still works, simply
  unvalidated. The engine never contacts the ticketing system.
- **Config disambiguates colliding key shapes.** Linear keys (`ENG-123`) are
  shape-identical to Jira keys (`PROJ-1234`); because the provider is named in
  config, the engine validates against exactly one format — there is nothing to
  guess. This is a direct argument for config-over-format-guessing.
- **Existence and state checks** (does the ticket exist; is it in an allowed
  state) require a token and a network call and therefore live in a satellite
  (`lore-atlassian` for Jira, ADR-090), never in the engine (ADR-002, ADR-073).
  Enforcement is at write time, not agent time (ADR-067).
- **Graph export** surfaces the edge as typed, marked `external: true` and
  `resolved: false`, carrying the configured `provider` (ADR-074), so graph
  backends see the relationship and its system without the engine pretending to
  resolve it.

## Consequences

### Positive

- Typed, lintable change traceability the corpus can carry and the graph export
  can surface, without a database and without a network dependency in the engine.
- One stable section across all repositories: authors and agents never choose
  among per-system headings, and the corpus does not grow an optional section per
  provider.
- The provider lives in committed config, so the ticketing system is a one-line
  repository decision (ADR-088) and the key-shape collision dissolves.

### Negative

- An external edge is only as fresh as the satellite's optional state check; the
  engine alone cannot tell a stale ticket from a live one.
- A second class of edge (external-target) adds nuance to the registry and the
  graph export contract.
- A repository that genuinely uses two ticketing systems is not supported; this
  is an accepted trade-off given the one-system-per-org reality.

### Risks

- Pressure to make the engine call the ticketing system "just to validate the
  ticket". Mitigation: the engine is format-lint only by decision; state checks
  are satellite-only (ADR-002).
- The exemption is read as the door to arbitrary custom edge kinds (ADR-052).
  Mitigation: the edge is code-defined here, not repo-declared; the provider set
  grows by code change, not by repo configuration of new edge kinds.

## Alternatives Considered

### A named edge per ticketing system

One always-on edge per provider — `## Related Jira`, `## Related GitHub`,
`## Related Linear`, … — each with its own registry entry.

#### Disadvantages

- Section proliferation across all five artifact types; the author must choose a
  heading per reference. It does not match the one-system-per-org reality, and it
  reintroduces the Linear/Jira key-shape collision (format alone cannot tell
  `ENG-123` from a Jira key) that a configured provider removes outright.

### Keep ticket IDs in prose

No typed edge; mention the ticket in the body.

#### Disadvantages

- Untyped, unlinted, and invisible to the graph export; the link rots and
  traceability is unverifiable.

### Force a ticket edge into the existing artifact-range registry

Add the edge with a normal artifact range.

#### Disadvantages

- A ticket is not an artifact; range resolution would always fail. The
  external-target exemption is the correct mechanism, not a workaround.

### A full custom-relationship-type system

Let repos declare arbitrary edge kinds in config.

#### Disadvantages

- Deferred by ADR-052; far more surface than the need. A single code-defined
  external edge with a configured provider covers the real requirement now.

A single configured external-ticket edge (`related_tickets`, provider in
`.rac/config.yaml`) is selected.

## Relationship to Other Decisions

- ADR-055, ADR-016: extends the code-defined registry with an external-target
  edge class; resolution stays deterministic and Git-native for in-corpus edges.
- ADR-010: generalises the untyped-target exemption to typed external references.
- ADR-052: custom repo-declared kinds remain deferred; this edge is code-defined,
  and the provider — not the edge kind — is the configured value.
- ADR-074: the external edge surfaces in the typed graph export, marked
  unresolved/external and carrying the provider.
- ADR-088: the ticketing provider is a `rac init` / repository-config knob, set
  alongside the repository key.
- ADR-053: the format-lint severity is overridable like any validation rule.
- ADR-067, ADR-073, ADR-090: write-time format-lint in the engine; token-gated
  state checks in the per-provider satellite.
- ADR-085: an instance of the rule — the network half is a satellite, the
  deterministic half is the engine, decided for everyone.
