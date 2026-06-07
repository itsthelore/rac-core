# ADR-014: Viewer-Agnostic Knowledge Artifacts

## Status

Proposed

## Context

RAC artifacts are authored as Markdown and stored in source-control repositories.

As adoption grows, users may wish to visualize and navigate RAC artifacts through a variety of tools, including:

- GitHub
- GitLab
- Obsidian
- VS Code
- Cursor
- Claude
- Codex
- Future AI assistants
- Future RAC services

A natural temptation is to build a dedicated RAC user interface for browsing and navigating artifacts.

However, Markdown-based knowledge ecosystems already provide mature viewing, editing, search, navigation, graphing, and collaboration experiences.

The project requires a clear position regarding whether RAC should provide its own dedicated knowledge viewer.

## Decision

RAC will remain viewer-agnostic.

RAC artifacts must remain useful and understandable when viewed through:

- Plain text editors
- GitHub and GitLab
- Obsidian
- IDEs
- AI assistants
- Future tooling

RAC will focus on creating, validating, transforming, and understanding structured product knowledge.

RAC will not require a dedicated viewer in order to be useful.

Where possible, RAC should produce outputs that can enhance existing tools rather than replace them.

Examples include:

- Markdown-first artifacts
- Machine-readable JSON exports
- Link-aware relationship data
- Metadata suitable for external visualization tools
- AI-consumable representations

## Rationale

The primary value of RAC is not document rendering.

The primary value of RAC is semantic understanding of product knowledge.

Existing tools already provide strong capabilities for:

- Markdown rendering
- Repository browsing
- Search
- Navigation
- Collaboration
- Graph visualization

Competing directly with these tools would significantly increase project scope while providing limited differentiation.

Instead, RAC should focus on capabilities that existing viewers do not provide, including:

- Artifact validation
- Artifact inspection
- Knowledge health analysis
- Relationship detection
- Portfolio analysis
- Knowledge evolution tracking

This allows RAC to act as infrastructure rather than presentation.

## Consequences

### Positive

- Reduces maintenance burden.
- Leverages mature existing ecosystems.
- Allows users to adopt RAC within existing workflows.
- Enables multiple viewing experiences without fragmentation.
- Keeps development effort focused on knowledge intelligence.

### Negative

- User experience depends partly on external tools.
- Some visualization experiences may be inconsistent across viewers.
- RAC cannot fully control artifact presentation.

### Risks

There is a risk that feature requests gradually evolve toward:

- Repository browsers
- Documentation portals
- Dashboard frameworks
- Visual editors

These requests should be evaluated against the principle:

> Does this capability improve understanding of product knowledge, or does it primarily improve document presentation?

If the primary purpose is presentation, the capability may belong in a viewer rather than RAC itself.

## Alternatives Considered

### Dedicated RAC Viewer

Create and maintain a bespoke interface for viewing RAC artifacts.

Pros:

- Complete control over user experience.
- Ability to design artifact-native workflows.

Cons:

- Significant engineering effort.
- Competes with established tools.
- Expands project scope considerably.

### Obsidian-Specific Experience

Optimize RAC primarily for Obsidian.

Pros:

- Rich navigation and graph capabilities.
- Existing Markdown ecosystem.

Cons:

- Creates dependency on a specific platform.
- Limits future flexibility.

### Viewer-Agnostic Approach (Selected)

Treat viewers as interchangeable consumers of RAC artifacts.

Pros:

- Maximum portability.
- Broad ecosystem compatibility.
- Strong separation of concerns.

## Future Implications

Future RAC capabilities may generate data consumed by external viewers, including:

- Relationship graphs
- Knowledge maps
- Portfolio health metrics
- Artifact lineage
- Repository intelligence

These outputs should remain portable and viewer-independent.

Future hosted RAC services may provide visualizations, but such visualizations should consume RAC artifacts rather than redefine them.

## Success Measures

Evidence that this decision is succeeding may include:

- RAC artifacts are successfully used within multiple tools and platforms.
- Users can switch viewers without changing artifact formats.
- Third-party tooling emerges around RAC artifacts.
- AI systems consume RAC outputs without requiring RAC-specific interfaces.

## Review Date

Review at v1.0.0 or if a proposal is made to introduce a dedicated RAC viewer or editor.