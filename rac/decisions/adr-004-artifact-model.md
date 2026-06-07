# ADR-004 Artifact Model

## Status

Accepted

## Context

Not all documents are the same kind of knowledge. RAC needs a model that can grow beyond requirements.

## Decision

RAC analyzes typed artifacts rather than generic documents. Planned artifact types include Requirement, Decision, Roadmap, Prompt, and Meeting.

## Consequences

### Positive

- Provides the bridge to v0.5+ artifact types
- Each artifact type can have its own structure and validation

### Negative

- More modeling work as new artifact types are added
