# ADR-016: Relationships as Explicit Structural References

## Status

Proposed

## Context

RAC is evolving from a tool that validates individual product knowledge artifacts into a system that can understand product knowledge across a repository.

Earlier releases established support for first-class artifacts such as:

* Requirements
* Decisions
* Roadmaps
* Prompts

As the number of artifact types grows, the value of RAC increasingly depends on understanding how those artifacts relate to one another.

Examples include:

* A requirement may be informed by a decision.
* A decision may resolve a requirement.
* A roadmap may reference related requirements.
* A prompt may support the creation or review of a requirement.
* A later decision may supersede an earlier decision.
* A roadmap initiative may depend on a requirement being accepted.
* A requirement may be blocked by an unresolved decision.

Without relationship support, RAC can inspect individual artifacts but cannot explain how product knowledge fits together.

However, relationship support introduces architectural risks.

If relationships are inferred automatically, hidden in a database, or stored outside the Markdown artifacts, RAC may lose some of its core properties:

* Human readability
* Git-native storage
* Reviewability through pull requests
* Portability across tools
* Compatibility with simple text editors
* Deterministic CLI behavior
* Low implementation complexity

The project therefore needs a clear decision about how relationships should be represented, discovered, validated, and exposed.

## Decision

RAC relationships shall be represented as explicit structural references inside Markdown artifacts.

Relationships shall be human-readable, Git-native, and stored in the source files themselves.

RAC may parse, inspect, validate, count, and report relationships, but it shall not require a hidden database, external graph store, or non-Markdown metadata layer to understand them.

A relationship exists when an artifact contains an explicit reference to another artifact using a supported relationship section or supported reference syntax.

Examples may include sections such as:

* `## Related Requirements`
* `## Related Decisions`
* `## Related Roadmaps`
* `## Related Prompts`
* `## Supersedes`
* `## Blocked By`
* `## Depends On`

The exact supported relationship sections and relationship types may evolve over time, but the architectural rule remains:

> Relationships are authored explicitly in the artifact text and interpreted by RAC.

## Relationship Model

RAC should treat relationships as structured edges between artifacts.

A relationship has:

* Source artifact
* Target artifact
* Relationship type
* Reference text
* Resolution status

For example:

```
Source: docs/roadmaps/q3-roadmap.md
Type: related_requirement
Target: docs/requirements/checkout-speed.md
Status: resolved
```

A relationship may be resolved or unresolved.

A resolved relationship points to an artifact RAC can find.

An unresolved relationship contains a reference RAC cannot currently match to a known artifact.

Unresolved relationships are not necessarily invalid in all contexts, but RAC should be able to report them clearly.

## Relationship References

RAC should support references that remain understandable in plain Markdown.

Supported reference forms may include:

* Relative file paths
* Artifact IDs where present
* Markdown links to local files
* Plain text references that can be reported as unresolved

Examples:

```
- [Checkout Speed Requirement](../requirements/checkout-speed.md)

- REQ-001

- docs/decisions/adr-004-parser-strategy.md

- ADR-004
```

RAC should prefer deterministic resolution.

Where multiple artifacts could match the same reference, RAC should report ambiguity rather than guessing.

## Principles

### Principle 1 — Relationships Must Be Explicit

RAC should not treat inferred semantic similarity as a source of truth for relationships.

For example, if a Roadmap and Requirement discuss similar topics, RAC may eventually suggest a possible relationship, but that should not be treated as an actual relationship unless it is explicitly recorded.

In v0.7.x, relationship support should be based on explicit references only.

### Principle 2 — Markdown Remains the Source of Truth

Relationship information should live inside Markdown artifacts.

RAC should not require:

* A database
* A separate graph file
* A hidden metadata directory
* A proprietary project file
* A hosted service

This preserves RAC’s Git-native and human-readable model.

### Principle 3 — Relationship Parsing Should Be Deterministic

Given the same repository state, RAC should produce the same relationship output every time.

Relationship resolution should avoid fuzzy matching as a source of truth.

Fuzzy matching may be introduced later as advisory improvement guidance, but not as canonical relationship resolution.

### Principle 4 — Relationships Should Be Inspectable From the CLI

Relationships should be available through CLI and JSON outputs.

Explorer, dashboards, IDE integrations, and AI tools may consume relationship data, but relationship intelligence belongs in RAC Core.

If relationship information is visible in a future UI, it should also be obtainable through a command such as:

```
rac relationships
```

or through an equivalent service-layer API.

### Principle 5 — Broken Relationships Should Be Visible

RAC should help users identify:

* Missing targets
* Ambiguous references
* Unsupported relationship types
* Cycles where relevant
* Orphaned artifacts
* Artifacts with no inbound or outbound relationships

This should be done through inspection and reporting before any deeper scoring or workflow behavior is introduced.

### Principle 6 — Relationships Are Not Workflow State

A relationship between artifacts is not the same as task tracking.

RAC relationships should not imply:

* Ownership
* Delivery state
* Priority
* Assignment
* Approval status
* Dependency management workflow
* Project management behavior

Those concepts may be considered separately in future ADRs, but they are not part of the relationship model itself.

## Rationale

The primary value of RAC is that product knowledge can be represented in a form that is both human-readable and machine-readable.

Relationships are a natural extension of that idea.

If Requirements, Decisions, Roadmaps, and Prompts remain isolated documents, RAC can only answer local questions such as:

* Is this requirement structurally valid?
* Does this decision contain required sections?
* Does this roadmap include outcomes and initiatives?

With relationships, RAC can begin answering repository-level questions such as:

* Which requirements are linked to decisions?
* Which decisions are not connected to any requirement?
* Which roadmap initiatives reference requirements?
* Which artifacts depend on unresolved decisions?
* Which artifacts are orphaned?
* Which references are broken after a file move?

Representing relationships explicitly in Markdown keeps RAC aligned with its core philosophy:

* Product knowledge should be visible.
* Product knowledge should be reviewable.
* Product knowledge should be portable.
* Product knowledge should work without a platform.

A hidden graph would make RAC more powerful in the short term but weaker as infrastructure. Explicit structural references provide a better long-term foundation.

## Consequences

### Positive

* Relationships remain human-readable.
* Relationships can be reviewed in pull requests.
* RAC remains Git-native.
* Relationship behavior is deterministic.
* JSON output can support automation and future UIs.
* Explorer can consume relationships without owning relationship logic.
* Relationship support can be added incrementally.
* Broken or ambiguous links can be reported clearly.
* RAC can evolve toward repository intelligence without becoming a project-management system.

### Negative

* Users must author or maintain relationship references manually.
* File moves may break path-based relationships unless tooling helps update them.
* Plain text references may be ambiguous.
* Relationship discovery may initially feel less magical than AI-inferred linking.
* Some useful relationships may remain absent unless explicitly recorded.

### Neutral

* RAC may later suggest relationships through `rac improve`, but suggestions should not become canonical unless written back into artifacts by the user.
* RAC may later support richer relationship types, but the base model should remain explicit source-to-target references.

## Risks

### Risk 1 — Relationship Scope Creep

Relationships may tempt RAC toward workflow management, dependency planning, or delivery tracking.

This should be avoided.

Mitigation:

* Keep v0.7.x focused on structural relationship parsing, validation, and reporting.
* Do not add owners, priorities, statuses, due dates, or workflow states as part of relationship support.

### Risk 2 — Hidden Graph Emergence

A future implementation may introduce a generated graph and accidentally make it the source of truth.

Mitigation:

* Generated graphs may exist as derived outputs only.
* The Markdown artifacts remain canonical.
* RAC should be able to rebuild relationship data from source files.

### Risk 3 — Ambiguous References

References such as `ADR-004` or `REQ-001` may match more than one artifact.

Mitigation:

* Report ambiguous references explicitly.
* Prefer relative paths or stable artifact identifiers where available.
* Do not guess silently.

### Risk 4 — Overly Strict Validation

If unresolved relationships immediately cause validation failure, users may avoid adopting relationship sections.

Mitigation:

* Start with reporting and inspection.
* Treat unresolved relationships as warnings or relationship-report findings before making them hard validation errors.
* Reserve strict relationship validation for explicit commands or future release phases.

### Risk 5 — Relationship Type Explosion

Too many relationship types could make RAC hard to understand.

Mitigation:

* Start with a small set of relationship sections.
* Prefer generic relationship types before introducing specialised ones.
* Require future relationship types to be justified by clear user value.

## Alternatives Considered

### Alternative 1 — Hidden Graph Store

Store relationships in a separate graph database or generated project index.

#### Pros

* Powerful querying.
* Easier graph traversal.
* Could support complex relationship analysis.

#### Cons

* Not Git-native as the source of truth.
* Harder to review.
* Harder to edit manually.
* Introduces synchronization problems.
* Conflicts with RAC’s human-readable artifact model.

Rejected.

### Alternative 2 — Separate Relationship Manifest

Store relationships in a dedicated file, such as:

```
relationships.yaml
relationships.json
rac-graph.md
```

#### Pros

* Centralized relationship management.
* Easier to parse.
* Avoids editing individual artifacts.

#### Cons

* Relationships are separated from the context they describe.
* Merge conflicts may become more common.
* Users must maintain another artifact.
* Local readability is reduced.
* It creates a second source of truth.

Rejected for the default model.

A generated relationship manifest may be acceptable as an output, but not as the canonical source.

### Alternative 3 — Fully Inferred Relationships

Use AI or semantic matching to infer relationships automatically.

#### Pros

* Low manual effort.
* Can discover hidden connections.
* Useful for recommendations.

#### Cons

* Non-deterministic.
* Hard to review.
* May produce false positives.
* Not suitable as a canonical source of truth.
* Can undermine user trust.

Rejected as the base model.

AI-assisted relationship suggestions may be considered later as improvement guidance.

### Alternative 4 — Explicit Markdown Relationships

Represent relationships inside artifacts using human-readable Markdown references.

#### Pros

* Human-readable.
* Git-native.
* Reviewable.
* Deterministic.
* Easy to adopt incrementally.
* Compatible with existing editors and repositories.
* Aligns with RAC’s artifact-first model.

#### Cons

* Requires author discipline.
* May need tooling support for file moves and broken links.
* Less automatic than inferred linking.

Selected.

## Implementation Guidance

The first implementation of relationship support should be conservative.

It should focus on:

* Detecting relationship sections.
* Extracting references.
* Resolving references where deterministic.
* Reporting unresolved references.
* Reporting ambiguous references.
* Returning relationship data in JSON.
* Preserving existing validation behavior for Requirements, Decisions, Roadmaps, and Prompts.

Initial CLI support may include:

```
rac relationships <path>
```

Possible JSON shape:

```
{
  "relationships": [
    {
      "source": "docs/roadmaps/q3-roadmap.md",
      "source_type": "roadmap",
      "relationship_type": "related_requirement",
      "target": "docs/requirements/checkout-speed.md",
      "target_type": "requirement",
      "reference": "../requirements/checkout-speed.md",
      "status": "resolved"
    }
  ],
  "summary": {
    "resolved": 1,
    "unresolved": 0,
    "ambiguous": 0
  }
}
```

The exact JSON contract should be defined in the relevant release RFC.

## Relationship to Other ADRs

### ADR-012 — Repository Intelligence as the Value Layer

ADR-012 establishes that RAC’s value increases as it understands repositories, not just individual files.

ADR-016 extends that direction by defining relationships as a core part of repository intelligence.

### ADR-013 — Leverage Existing Source Control Systems

ADR-013 defines Git as the storage and collaboration layer.

ADR-016 supports this by keeping relationships inside Markdown artifacts that can be versioned, reviewed, and diffed in Git.

### ADR-014 — Viewer-Agnostic Knowledge Artifacts

ADR-014 establishes that RAC artifacts should not depend on a specific viewer.

ADR-016 preserves viewer independence by representing relationships in plain Markdown rather than in a viewer-specific graph.

### ADR-015 — Explorer as a Consumer

ADR-015 establishes that Explorer should consume RAC Core capabilities rather than own business logic.

ADR-016 follows that principle by placing relationship parsing and resolution in RAC Core, with any future Explorer relationship view acting only as a consumer.

### ADR-017

ADR-017 already exists and should remain separate.

ADR-016 should define the foundational relationship model only.

If ADR-017 covers a related concern, ADR-016 should be treated as the lower-level architectural decision that relationship intelligence must be explicit, Markdown-native, and core-owned.

## Success Measures

This decision is succeeding if:

* Relationships are visible in Markdown artifacts.
* RAC can report relationships from CLI commands.
* RAC can emit relationship data as JSON.
* Broken references can be detected.
* Ambiguous references can be reported.
* Relationship data can be consumed by future Explorer views without duplicating logic.
* Relationship behavior is deterministic across runs.
* Users can understand and edit relationships without a specialised tool.
* RAC does not become a workflow or project-management system as a side effect of relationship support.

## Review Date

Review after the first v0.7.x relationship implementation, or before introducing any of the following:

* AI-inferred relationship suggestions
* strict relationship validation
* automatic relationship repair
* generated graph outputs
* Explorer relationship visualisation
* workflow-like dependency management
* relationship scoring

**v0.7.3 note:** `rac portfolio` introduces a health score that includes relationship integrity as one of four weighted factors (0.25 weight). This is the first instance of relationship scoring in RAC Core. The formula is fully deterministic, documented in `src/rac/portfolio.py`, and uses only counts already produced by `summarize_relationships`. This ADR was reviewed before v0.7.3 implementation; no architectural objections were raised.
