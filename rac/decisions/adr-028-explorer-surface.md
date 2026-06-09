---
schema_version: 1
id: RAC-KTQ63DSEK9YG
type: decision
---
# ADR-016 Explorer Delivery Surface

## Status

Accepted

## Context

Explorer provides an interactive environment for understanding and maintaining product knowledge repositories.

Multiple delivery surfaces were considered:

- Terminal User Interface (TUI)

- Web Application

- Desktop Application

- IDE Extension

- Obsidian Plugin

The Explorer requirement defines the capability:

> Discover, understand, assess, and act on repository knowledge.

It does not prescribe how that capability is delivered.

A delivery surface decision is required to guide implementation.

## Decision

Explorer shall initially be implemented as a Terminal User Interface (TUI).

The TUI shall become the primary Explorer experience for the initial implementation.

## Rationale

### Alignment with RAC

RAC is a CLI-first product.

A TUI extends existing workflows while preserving:

- local execution

- Git-native operation

- scriptability

- platform independence

### Low Operational Complexity

A TUI requires:

- no hosted infrastructure

- no browser deployment

- no authentication systems

- no external services

### Accessibility

The target audience already operates within terminal-centric workflows.

Examples include:

- Product Managers

- Engineers

- Technical Founders

- AI-assisted development environments

### Faster Validation

A TUI enables Explorer concepts to be validated before investing in additional presentation surfaces.

## Consequences

### Positive

- Simple deployment.

- Consistent with RAC architecture.

- Works offline.

- Cross-platform.

- Low operational overhead.

### Negative

- More limited visualisation capabilities.

- Less accessible to non-technical users.

- Some graph-based experiences may require compromise.

## Future Evolution

Explorer is a capability rather than a single application.

Future versions may introduce additional delivery surfaces.

Examples:

- VS Code Extension

- Web Application

- Desktop Application

- MCP-based Interfaces

These additions shall not invalidate the Explorer capability model.

## Related Artifacts

### Implements

- Requirement: Product Knowledge Navigator (Explorer)

### Related

- ADR-015 Explorer as a Consumer

### Defines

- Explorer TUI as the initial delivery surface.