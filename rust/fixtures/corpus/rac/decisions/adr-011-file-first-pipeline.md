---
schema_version: 1
id: RAC-KTQ63DQ3A5FQ
type: decision
---
# ADR-011: File-First Pipelines

## Status

Accepted

## Context

RAC is a CLI-first tool intended to operate within existing developer and product workflows.

Users should be able to combine RAC commands with standard shell tooling and automation systems.

Many future workflows may involve:

* CI/CD pipelines
* AI agents
* MCP servers
* Shell automation
* Batch processing

Supporting file-based and stream-based workflows increases flexibility and interoperability.

## Decision

RAC commands should support files and standard streams where practical.

Commands should be composable through shell pipelines.

When appropriate:

* Commands should accept file paths.
* Commands should support stdin.
* Commands should support stdout.
* Commands should support machine-readable output formats.

RAC should avoid introducing proprietary workspace formats or hidden state where unnecessary.

## Consequences

### Positive

* Encourages Unix-style composability.
* Simplifies automation.
* Simplifies AI integration.
* Simplifies future MCP integration.
* Keeps Git as the source of truth.

### Negative

* Additional CLI complexity.
* Requires consistent handling of streams and files.

## Examples

Convert a document:

```bash
rac ingest prd.docx
```

Preview a conversion:

```bash
rac ingest prd.docx --stdout
```

Future pipeline workflow:

```bash
rac ingest prd.docx --stdout | rac inspect -
```

Potential future workflow:

```bash
rac ingest prd.docx --stdout | rac normalize -
```

## Notes

RAC should remain file-first.

Artifacts should remain portable, human-readable, and version-controlled.

Git repositories should remain the primary storage and collaboration mechanism.
