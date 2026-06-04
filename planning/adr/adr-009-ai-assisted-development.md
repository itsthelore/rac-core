# ADR-009: AI-Assisted Development

## Context

RAC is increasingly being developed with the assistance of AI coding tools such as Claude, Codex, and future AI agents.

As the project grows, architectural decisions must remain consistent regardless of whether code is written by a human contributor or an AI assistant.

Without explicit guidance, AI-generated code may unintentionally violate existing project decisions, introduce inconsistent patterns, or undermine long-term architectural goals.

## Decision

Accepted ADRs are architectural constraints for both human and AI contributors.

When an AI-generated change conflicts with an accepted ADR:

1. The conflict should be identified.
2. The rationale behind the ADR should be explained.
3. An alternative implementation should be proposed where possible.
4. A new ADR may be proposed if the original decision is no longer appropriate.
5. Existing ADRs must not be silently violated.

AI assistants should treat accepted ADRs as project governance rather than optional guidance.

## Consequences

### Positive

* Preserves architectural consistency.
* Reduces accidental design drift.
* Allows AI tools to participate safely in development.
* Creates durable project memory.

### Negative

* May require AI-generated solutions to be revised.
* Introduces additional governance overhead.

## Notes

ADRs are intended to represent the long-term design decisions of the project.

As RAC increasingly incorporates AI-assisted workflows, ADRs become the primary mechanism for preserving project intent across contributors and tools.
