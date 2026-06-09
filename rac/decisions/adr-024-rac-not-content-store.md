# ADR-024: RAC Is Not a Content Store

## Status

Accepted

## Context

RAC manages knowledge artifacts written as Markdown.

The broader software ecosystem is increasingly adopting Markdown as a common format for human and AI collaboration.

Examples include:

- Documentation systems
- Developer tools
- AI coding environments
- Knowledge management tools
- Cloud storage platforms

As Markdown becomes more widely adopted, adjacent products may provide:

- Markdown editing
- File synchronization
- Collaborative commenting
- Version history
- Document sharing
- Workspace management

There is a risk that RAC could expand into these areas and become a general-purpose documentation platform.

This would create overlap with existing mature products such as:

- Document platforms
- Knowledge bases
- Storage providers
- Developer editors

RAC requires a clear boundary between managing where knowledge lives and ensuring knowledge remains correct.

## Decision

RAC shall not become a content storage or document collaboration platform.

RAC shall treat Markdown artifacts as externally owned source files.

RAC Core shall focus on:

- Validation
- Inspection
- Relationships
- Traceability
- Repository intelligence
- Automation

RAC shall not provide:

- File hosting
- File synchronization
- Real-time editing
- Document permissions
- Collaborative comments
- Workspace management
- Proprietary storage

Existing systems such as:

- Git repositories
- Local filesystems
- Cloud drives
- Developer environments

shall remain responsible for storing and editing artifacts.

## Principles

### Principle 1 — Markdown Is the Interface, Not the Product

RAC does not own Markdown documents.

RAC understands Markdown documents.

The value of RAC comes from interpreting structured knowledge, not storing it.

### Principle 2 — Git Remains the System of Record

RAC assumes source control systems provide:

- Storage
- History
- Branching
- Review workflows
- Collaboration primitives

RAC enhances these workflows rather than replacing them.

### Principle 3 — Intelligence Over Editing

RAC should answer questions such as:

- Is this requirement valid?
- What decision caused this change?
- What roadmap item implements this requirement?
- Which artifacts changed?
- What relationships are missing?
- Is repository knowledge becoming unhealthy?

RAC should not answer questions such as:

- Where is this document stored?
- Who can edit this document?
- How do users collaborate on this document?
- How are files synchronized?

### Principle 4 — Integrate Rather Than Replace

RAC should integrate with existing tools rather than compete with them.

Potential consumers include:

- CLI users
- CI/CD pipelines
- Source control systems
- AI coding assistants
- Editors
- Document platforms

RAC should make existing Markdown ecosystems more valuable.

### Principle 5 — Avoid Building a Worse Version of Existing Products

RAC should avoid recreating:

- Google Docs
- Notion
- Confluence
- Cloud drives
- Document editors

These products solve collaboration and storage.

RAC solves correctness and traceability.

## Rationale

The increasing adoption of Markdown creates more structured text artifacts.

More artifacts create new problems:

- Inconsistent structure
- Missing relationships
- Outdated decisions
- Broken traceability
- Poor repository visibility
- AI-generated knowledge drift

These problems exist after documents are created.

RAC operates at this layer.

For example:

Instead of:

```text
User
 ↓
RAC Editor
 ↓
RAC Storage
 ↓
Markdown Files
```

RAC should support:

```text
User
 ↓
Existing Tools
 ↓
Markdown Files
 ↓
RAC Intelligence Layer
 ↓
Validation / Relationships / Automation
```

RAC succeeds by becoming infrastructure underneath knowledge workflows.

## Consequences

### Positive

- Clear product boundaries.
- Reduced scope creep.
- Lower engineering complexity.
- Easier integration with existing ecosystems.
- Stronger alignment with developer workflows.
- Avoids competing with mature platforms.
- Preserves CLI-first architecture.

### Additional Benefits

- Any increase in Markdown adoption increases RAC relevance.
- New editors and storage systems become potential integrations.
- RAC remains tool-agnostic.
- AI-generated artifacts can be validated regardless of origin.

### Negative

- RAC depends on external systems for collaboration workflows.
- Some users may expect editing or document management features.
- Additional integrations may be required for smoother adoption.

## Risks

The primary risk is gradual expansion into document management.

Examples:

- Explorer gains editing capabilities.
- RAC introduces user accounts.
- RAC stores artifact history outside Git.
- RAC creates proprietary workspace concepts.
- RAC implements commenting workflows.

These should be considered warning signs.

Before adding functionality, contributors should ask:

> Does this improve knowledge correctness, or does it manage documents?

If the answer is document management, the feature likely belongs outside RAC.

## Alternatives Considered

### Build a Complete Knowledge Platform

Create a full hosted RAC environment with:

- Storage
- Editing
- Users
- Permissions
- Collaboration

#### Pros

- Complete ownership of user experience.
- Easier onboarding for non-technical users.

#### Cons

- Large increase in product scope.
- Competes directly with mature platforms.
- Moves RAC away from infrastructure.
- Requires solving unrelated problems.

### Build a RAC-Specific Editor

Create a dedicated editor optimized for RAC artifacts.

#### Pros

- Better artifact authoring experience.
- More control over workflows.

#### Cons

- Duplicates existing editor functionality.
- Creates maintenance burden.
- Reduces ecosystem compatibility.

### Intelligence Layer Over Existing Files (Selected)

Keep RAC focused on understanding existing Markdown artifacts.

#### Pros

- Clear differentiation.
- Works with existing tools.
- Supports automation.
- Preserves open standards.
- Aligns with Requirements-as-Code philosophy.

## Relationship to Other ADRs

### ADR-012 — Repository Intelligence as the Value Layer

ADR-012 establishes repository understanding as RAC's primary value.

ADR-016 reinforces that intelligence, not storage, is the product.

### ADR-013 — Leverage Existing Source Control Systems

ADR-013 defines Git as the storage and history layer.

ADR-016 prevents RAC from duplicating those responsibilities.

### ADR-014 — Viewer-Agnostic Knowledge Artifacts

ADR-014 ensures artifacts remain portable.

ADR-016 extends this principle by avoiding platform ownership.

### ADR-015 — Explorer as a Consumer

ADR-015 prevents Explorer becoming the source of RAC capabilities.

ADR-016 prevents Explorer evolving into a document management platform.

## Success Measures

Evidence that this decision is succeeding may include:

- RAC artifacts remain plain Markdown files.
- RAC works equally across multiple editors.
- RAC capabilities are available through CLI and automation.
- Repository intelligence improves without requiring migration.
- Users adopt RAC without changing where their documents live.

## Review Date

Review at v1.0.0 or if RAC begins introducing document editing, hosting, or collaboration features.