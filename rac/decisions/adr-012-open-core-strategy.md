---
schema_version: 1
id: RAC-KTQ63DQ7QZJ7
type: decision
---
# ADR-012: Open Core and Knowledge Infrastructure Strategy

## Status

Proposed

## Context

RAC is being developed as an open-source CLI and specification for managing product knowledge as structured artifacts.

Current capabilities include:

- Validation
- Statistics
- Document ingestion
- Artifact inspection

Future capabilities may include:

- Improvement guidance
- Portfolio analysis
- Relationship mapping
- Knowledge graph generation
- AI-assisted workflows

As adoption grows, there is a risk that commercial considerations could influence roadmap decisions, leading to artificial restrictions in the open-source tooling or fragmentation between the RAC specification and RAC implementations.

The project requires a clear principle regarding which capabilities belong in the open-source ecosystem and which capabilities may justify future commercial offerings.

## Decision

RAC will adopt an Open Core strategy.

The following will remain open-source and freely available:

- RAC CLI
- RAC artifact schemas
- RAC validation rules
- RAC artifact formats
- RAC import and export capabilities
- RAC inspection capabilities
- RAC machine-readable outputs
- RAC reference implementations

The RAC specification is the primary asset of the project and should remain openly available.

Future commercial offerings, if developed, should be built around repository-level intelligence and organisational capabilities rather than restricting core artifact functionality.

Examples may include:

- Hosted knowledge repositories
- Repository indexing
- Search and discovery
- Cross-file relationship analysis
- Knowledge graphs
- Governance and audit capabilities
- Enterprise reporting
- AI context services
- MCP-compatible knowledge services
- Multi-repository aggregation

## Rationale

The long-term success of RAC depends on adoption of the artifact model rather than adoption of a specific implementation.

A requirement artifact should remain a requirement artifact regardless of whether it is created, validated, or consumed using the RAC CLI, an IDE plugin, an AI assistant, or a future hosted service.

The project should optimise for becoming a widely adopted standard for structured product knowledge.

Open artifact formats encourage:

- Community contribution
- Ecosystem development
- Third-party tooling
- Long-term portability
- AI interoperability

Commercial value, if it emerges, is expected to derive primarily from repository-scale understanding rather than individual artifact manipulation.

This follows a pattern seen in other successful open ecosystems:

- Git → GitHub
- Terraform → Terraform Cloud
- OpenAPI → SwaggerHub
- Kubernetes → Managed Kubernetes Platforms

In each case, the specification and local tooling remain broadly available while hosted and organisational capabilities provide commercial value.

## Consequences

### Positive

- Encourages adoption of RAC as a standard.
- Reduces vendor lock-in concerns.
- Supports long-term ecosystem growth.
- Aligns with AI-first workflows through open machine-readable formats.
- Allows commercial opportunities without weakening the open-source project.

### Negative

- Some potentially valuable functionality may remain open-source.
- Commercial differentiation may require more sophisticated repository-level capabilities.
- Monetisation opportunities may take longer to emerge.

### Risks

The project could drift toward:

- Project management tooling
- Documentation tooling
- Generic AI workflow tooling

rather than remaining focused on structured product knowledge.

Future roadmap decisions should be evaluated against the question:

> Does this capability improve the creation, understanding, or governance of product knowledge?

If the answer is no, the capability may fall outside the intended scope of RAC.

## Alternatives Considered

### Fully Open Source

Keep all capabilities open-source indefinitely.

Pros:

- Maximum community trust.
- Simplest governance model.

Cons:

- No clear commercial path.
- Increased sustainability risk.

### Closed Commercial Product

Develop RAC primarily as a proprietary platform.

Pros:

- Direct monetisation path.

Cons:

- Reduced adoption.
- Reduced ecosystem participation.
- Increased vendor lock-in concerns.

### Open Core (Selected)

Keep artifact standards and local tooling open while reserving organisational and repository-scale capabilities for potential future commercial offerings.

This balances ecosystem growth with long-term sustainability.

## Success Measures

Evidence that this decision is succeeding may include:

- Adoption of RAC artifact formats outside the RAC CLI.
- Third-party tooling built around RAC artifacts.
- AI workflows consuming RAC-compatible outputs.
- Community contributions to schemas and tooling.
- Repository-scale capabilities emerging as a distinct layer above the core specification.

## Review Date

Review when RAC reaches v1.0.0 or when a commercial offering is first actively considered.