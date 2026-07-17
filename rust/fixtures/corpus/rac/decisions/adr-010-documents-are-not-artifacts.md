---
schema_version: 1
id: RAC-KTQ63DQ2AEJZ
type: decision
---
# ADR-010: Documents Are Not Artifacts

## Status

Accepted

## Context

Many product teams store knowledge in large documents such as:

* PRDs
* Design documents
* Strategy documents
* Meeting notes
* Planning documents

These documents often contain multiple types of information simultaneously.

For example, a single PRD may contain:

* Requirements
* Decisions
* Risks
* Success metrics
* Roadmap information

Treating an entire document as a single artifact limits future analysis and extraction capabilities.

## Decision

RAC treats documents as containers of knowledge.

Artifacts are structured representations of specific knowledge types extracted from those documents.

A document is not necessarily an artifact.

A document may contain:

* One artifact
* Multiple artifacts
* Partial artifacts
* Supporting information

RAC should separate document ingestion from artifact understanding.

## Consequences

### Positive

* Supports real-world documentation.
* Enables future artifact extraction workflows.
* Separates ingestion from analysis.
* Allows multiple artifact types to coexist within a document.

### Negative

* Introduces an additional conceptual layer.
* Artifact detection becomes a separate capability.

## Examples

A PRD may contain:

```text
Problem
Requirements
Success Metrics
```

which could map to a Requirement artifact.

The same document may also contain:

```text
Decision
Alternatives Considered
Consequences
```

which could map to a Decision artifact.

Future RAC capabilities may extract these independently.

## Notes

This ADR establishes a clear separation between:

* Documents
* Artifacts

and enables future ingestion, inspection, normalization, and extraction workflows.
