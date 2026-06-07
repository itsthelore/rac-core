# ADR-015: Consumers before Interfaces

## Status

Proposed

## Context

RAC is evolving as a product knowledge infrastructure platform.

Core functionality is exposed through:

- CLI commands
- Service-layer APIs
- Structured artifact schemas
- JSON outputs

Future roadmap items include:

- Relationships
- Portfolio Health
- Explorer (Terminal User Interface)

Explorer is intended to provide a terminal-native experience for navigating RAC repositories.

A common risk in projects that evolve from command-line tooling into interactive interfaces is that business logic gradually migrates into the user interface.

Examples include:

- Repository analysis only available through the UI
- Relationship calculations performed exclusively by the UI
- Health metrics available only in visual dashboards
- Features inaccessible to automation or scripting

This creates duplicated implementations, inconsistent behavior, and limits future integrations.

The project requires a clear architectural boundary between RAC capabilities and RAC Explorer.

---

## Decision

Explorer shall be treated as a consumer of RAC capabilities rather than a source of RAC capabilities.

All repository intelligence, artifact intelligence, and knowledge analysis shall exist within:

- Service-layer APIs
- Core RAC modules
- Standard CLI commands

Explorer shall consume these capabilities through stable interfaces.

No business logic shall exist exclusively within Explorer.

If information is visible in Explorer, it should be obtainable through:

```bash
rac <command>
```

or through an equivalent service-layer API.

---

## Principles

### Principle 1 — Logic Belongs in Core RAC

Repository intelligence shall be implemented within RAC itself.

Examples:

- Artifact inspection
- Artifact improvement
- Relationship detection
- Portfolio analysis
- Repository health metrics

Explorer may display these results but shall not calculate them independently.

### Principle 2 — Explorer is a Presentation Layer

Explorer shall focus on:

- Navigation
- Visualization
- Interaction
- Workflow efficiency

Explorer shall not become a second implementation of RAC capabilities.

### Principle 3 — CLI Remains First-Class

Every capability exposed through Explorer should remain accessible through CLI workflows.

Examples:

```bash
rac inspect
rac improve
rac relationships
rac portfolio
```

Users should not be required to launch Explorer to access RAC functionality.

### Principle 4 — Automation Must Remain Possible

Capabilities shall remain consumable by:

- Shell scripts
- CI/CD pipelines
- IDE integrations
- AI assistants
- Future RAC extensions

Explorer shall not become the exclusive interface to repository intelligence.

### Principle 5 — JSON Before UI

Where new repository intelligence is introduced, the preferred implementation order shall be:

```text
Service Layer
    ↓
CLI Command
    ↓
JSON Output
    ↓
Explorer Integration
```

This ensures that Explorer consumes capabilities rather than defining them.

---

## Rationale

The value of RAC lies in understanding structured product knowledge.

Explorer improves usability and discoverability but is not the primary source of knowledge intelligence.

For example:

Instead of:

```text
Explorer
 └── Calculates Portfolio Health
```

RAC should implement:

```text
rac portfolio
 └── Calculates Portfolio Health

Explorer
 └── Displays Portfolio Health
```

This ensures:

- Consistency
- Reusability
- Testability
- Automation support

The same intelligence becomes available to:

- Terminal users
- CI systems
- Obsidian integrations
- Future plugins
- AI systems
- Explorer

without duplication.

---

## Consequences

### Positive

- Single source of truth for business logic.
- Reduced duplication.
- Easier testing.
- Improved automation support.
- Better long-term maintainability.
- Consistent outputs across interfaces.
- Explorer can evolve independently from repository intelligence.
- Alternative viewers can be built in the future.
- Future integrations become simpler.

### Negative

- Some Explorer features may require additional CLI or API work before implementation.
- User-interface development may initially move more slowly.

---

## Risks

There is a risk that Explorer becomes the primary development target.

This may encourage implementation patterns such as:

- UI-only metrics
- UI-only calculations
- UI-only navigation metadata

These should be considered architectural violations.

Before implementing new Explorer functionality, contributors should ask:

> Could this capability be exposed through a CLI command or service-layer API?

If the answer is no, the implementation likely belongs in RAC Core rather than Explorer.

---

## Alternatives Considered

### Explorer-Centric Architecture

Implement repository intelligence directly within Explorer.

#### Pros

- Faster short-term development.
- Fewer intermediate abstractions.

#### Cons

- Duplicate logic.
- Difficult automation.
- Increased maintenance burden.
- Tighter coupling between UI and functionality.

### Separate Explorer Backend

Create an independent Explorer service responsible for repository analysis.

#### Pros

- Strong separation of concerns.

#### Cons

- Significant complexity.
- Creates multiple sources of truth.

### Explorer as Consumer (Selected)

Implement intelligence once within RAC Core and expose it through multiple interfaces.

#### Pros

- Clear ownership boundaries.
- Maximum reusability.
- Strong alignment with ADR-012, ADR-013, and ADR-014.

---

## Relationship to Other ADRs

### ADR-012 — Repository Intelligence as the Value Layer

ADR-012 establishes that RAC's value lies in understanding repositories.

ADR-015 ensures that repository intelligence remains within RAC Core rather than being embedded in Explorer.

### ADR-013 — Leverage Existing Source Control Systems

ADR-013 defines Git as the storage layer.

ADR-015 defines Explorer as a presentation layer.

### ADR-014 — Viewer-Agnostic Knowledge Artifacts

ADR-014 establishes viewer independence.

ADR-015 ensures Explorer remains one consumer among many rather than becoming the canonical interface.

---

## Success Measures

Evidence that this decision is succeeding may include:

- Explorer contains minimal business logic.
- New RAC capabilities appear first as CLI commands.
- JSON outputs remain comprehensive and stable.
- Automation workflows can access the same intelligence as Explorer.
- Alternative consumers can be built without modifying RAC Core.

---

## Review Date

Review at v1.0.0 or if Explorer begins implementing repository intelligence that cannot be accessed through existing RAC commands or service-layer APIs.