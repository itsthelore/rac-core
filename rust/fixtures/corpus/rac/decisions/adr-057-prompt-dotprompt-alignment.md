---
schema_version: 1
id: RAC-KV4134WX85F9
type: decision
tags: [prompts, dotprompt, interop, export]
---
# ADR-057: Align Prompt Artifacts to dotprompt via a Derived Export, Not a Source Change

## Status

Proposed

## Category

Architecture

## Context

RAC's `prompt` artifact is knowledge — an H1 title and `## Objective / Input /
Instructions / Output` sections (ADR-004). dotprompt (Google, used in Firebase
Genkit) is the frontrunner for *executable* prompts: YAML frontmatter with
`model`, `input.schema` (Picoschema or JSON Schema), `output.format`/`output.schema`,
and tools, plus a Handlebars template body. The two share a carrier (frontmatter +
template), so a RAC prompt is close to dotprompt-executable.

The brief's intent is that a RAC prompt be dotprompt-*executable*, not merely
documented. The obvious way — adding `model`/`input`/`output`/`tools` to the
prompt's source frontmatter — collides with recorded decisions:

- **ADR-025** makes frontmatter the uniform machine-operational *identity*
  envelope (`schema_version`/`id`/`type`/`relationships`/`tags`); product reasoning
  lives in the body. Per-type executable frontmatter would fork the envelope.
- **ADR-052** defers JSON-Schema/dialect machinery; Picoschema is exactly that
  kind of machinery.

RAC already has a coherent answer to "expose an artifact in another tool's format
without changing the source": a *derived export*, parallel to the OKF bundle
(ADR-048) and SARIF (ADR-054).

## Decision

RAC aligns to dotprompt through a **derived export**, not a source-frontmatter
change. `rac export … --dotprompt` (the exact surface is fenced to the
implementation) projects each `prompt` artifact into a `.prompt` file: dotprompt
frontmatter (`model`, `input`, `output`, tools) derived from the prompt's
sections plus a small optional projection block, and the `## Instructions` body as
the template. The RAC source stays the uniform ADR-025 envelope; the dotprompt
view is a derived contract, like the OKF and SARIF views.

1. **Source frontmatter is unchanged** — ADR-025's uniform envelope holds; no
   per-type executable fields, no Picoschema in source (ADR-052).
2. **The dotprompt view is derived and deterministic** (ADR-002/ADR-007),
   regenerable from the artifact, never a second source of truth.
3. **Validation aligns the contract, not the prose.** RAC checks that a prompt
   can produce a valid dotprompt projection (the required sections exist); it does
   not judge the prompt text — consistent with the no-AI-in-core premise.
4. **Re-verify before pinning.** dotprompt is young and moving; the projection is
   pinned to a dotprompt version and revisited as it stabilises (as with OKF).

## Consequences

### Positive

- A RAC prompt becomes dotprompt-executable (export the `.prompt`, run it) without
  forking the frontmatter envelope or adding schema machinery to source.
- Consistent with RAC's established derived-contract pattern (OKF, SARIF) — one
  mental model for "executable/interchange views".

### Negative

- Executability is one `rac export` away rather than intrinsic to the source file;
  a user who expected to author dotprompt directly in the artifact must export.
- Another derived contract pinned to a young upstream spec to keep in step.

### Neutral

- If a design partner needs author-time dotprompt fields in source, that is a
  separate, future decision that would extend ADR-025 — recorded then, not now.

## Alternatives Considered

- **Add dotprompt fields to prompt source frontmatter (the brief's literal read).**
  Rejected for now: forks the uniform ADR-025 envelope and pulls Picoschema/JSON-
  Schema machinery into source (ADR-052). Reconsider only on real demand.
- **A `.prompt` sidecar file authored alongside the artifact.** Rejected: a second
  hand-maintained source that drifts; the derived export gives the same output
  without the drift.
- **Do nothing.** Rejected: dotprompt is the prompt-interop frontrunner and the
  derived view is cheap given the OKF/SARIF precedent.

## Related Decisions

- adr-025
- adr-052
- adr-048
- adr-007

## Related Roadmaps

- v0.17.1-per-type-standards-enforcement

## Related Designs

- per-type-standards-checks
