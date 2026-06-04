# ADR-013: Leverage Existing Source Control Systems

## Status

Proposed

## Context

RAC treats product knowledge as structured artifacts that can be validated, inspected, transformed, and analyzed.

These artifacts are stored as files and are expected to evolve over time through standard software development workflows.

As RAC capabilities expand, it becomes possible to imagine features traditionally associated with version control systems, including:

- History tracking
- Change management
- Branching
- Collaboration
- Review workflows
- Synchronization
- Hosting

This creates a strategic question:

> Should RAC develop its own version-control and storage mechanisms, or should it build upon existing systems such as Git?

The project requires a clear decision regarding the boundary between product knowledge management and source-control infrastructure.

## Decision

RAC will build upon existing source-control systems rather than replacing them.

Git (or equivalent systems) will remain responsible for:

- Storage
- Version history
- Branching
- Merging
- Synchronization
- Distribution
- Authentication
- Access control

RAC will focus on semantic understanding of product knowledge.

RAC capabilities should operate on top of source-control systems rather than attempting to reimplement them.

Examples include:

- Artifact-aware validation
- Artifact-aware inspection
- Artifact-aware statistics
- Artifact-aware diffing
- Artifact-aware history
- Artifact-aware review
- Repository-level knowledge analysis

Where version-control functionality is required, RAC should integrate with existing tooling rather than introduce alternative implementations.

## Rationale

Version-control systems represent decades of engineering effort and ecosystem development.

Reimplementing source-control functionality would introduce significant complexity without advancing RAC's core mission.

The primary value of RAC is not file storage.

The primary value of RAC is understanding the meaning, structure, quality, and relationships of product knowledge artifacts.

For example:

Git can answer:

> Which lines changed?

RAC can answer:

> Which requirements changed?

Git can answer:

> Which file was modified?

RAC can answer:

> Which business decision was affected?

Git can answer:

> What is the commit history?

RAC can answer:

> How has this requirement evolved over time?

These capabilities are complementary rather than competitive.

By building on top of existing source-control systems, RAC can focus development effort on product knowledge infrastructure rather than generic file-management concerns.

## Consequences

### Positive

- Avoids duplicating mature infrastructure.
- Leverages existing developer workflows.
- Remains compatible with GitHub, GitLab, Bitbucket, and local Git repositories.
- Keeps project scope focused.
- Accelerates delivery of knowledge-focused capabilities.

### Negative

- RAC becomes dependent on external version-control systems.
- Some advanced knowledge workflows may be constrained by Git's file-based model.
- Repository metadata may need to be inferred from Git history rather than being natively stored.

### Risks

There is a risk that future feature requests gradually introduce:

- Branch management
- Remote synchronization
- User management
- Repository hosting

under the guise of knowledge-management functionality.

These requests should be evaluated against the principle:

> Does this capability improve understanding of product knowledge, or does it primarily replicate source-control infrastructure?

If the primary purpose is source-control infrastructure, it likely falls outside the scope of RAC.

## Alternatives Considered

### Build a RAC-Native Version Control System

Create a dedicated version-control system optimized for product knowledge artifacts.

Pros:

- Complete control over storage model.
- Artifact-native history and relationships.
- Potentially richer knowledge workflows.

Cons:

- Extremely large engineering effort.
- Recreates existing version-control capabilities.
- Fragments adoption.
- Requires building an ecosystem from scratch.

### Hybrid Storage Layer

Maintain Git compatibility while introducing RAC-specific storage and metadata systems.

Pros:

- Enables richer artifact semantics.

Cons:

- Increased complexity.
- Potential confusion regarding the system of record.

### Existing Source-Control Systems (Selected)

Use Git and equivalent systems for persistence and collaboration while focusing RAC on semantic understanding of knowledge.

Pros:

- Clear separation of responsibilities.
- Maximum interoperability.
- Allows RAC to remain focused on product knowledge.

## Future Implications

This decision does not prevent RAC from introducing knowledge-aware capabilities built on top of source control.

Examples may include:

- rac diff
- rac history
- rac review
- rac relationships
- Knowledge evolution analysis
- Artifact lineage tracking

These capabilities should consume version-control data rather than replace version-control systems.

## Success Measures

Evidence that this decision is succeeding may include:

- RAC operates effectively within standard Git repositories.
- RAC artifacts are versioned using existing workflows.
- New RAC capabilities build upon Git history rather than replacing it.
- Users adopt RAC without changing their source-control practices.

## Review Date

Review at v1.0.0 or if a proposal is made to introduce RAC-managed storage, synchronization, or version-control functionality.