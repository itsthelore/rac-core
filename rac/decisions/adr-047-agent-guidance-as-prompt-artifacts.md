---
schema_version: 1
id: RAC-KV2J0GYNCAJF
type: decision
---
# ADR-047: Agent Operating-Guidance Documents Are Prompt Artifacts

## Status

Accepted

## Category

Process

## Context

RAC's agent operating guidance lives under `rac/prompts/` —
`rac-agent-session-start`, `rac-agent-commit-guidelines`,
`rac-agent-pr-guidelines`, `rac-agent-release-gate-minor`,
`rac-agent-release-gate-major`, `rac-agent-simplification-guidelines`, and
`rac-agent-compression`. `CLAUDE.md` routes to them and asserts that
"canonical agent guidance lives in `rac/prompts/`, where the RAC corpus
gates validate it."

That assertion is currently false. All seven files classify as Unknown:
RAC classification is structural, scoring a document by its `##` section
headings against each artifact spec's required sections (ADR-004, and the
Prompt requirement's REQ-005). These files use prose labels rather than
headings, are sometimes wrapped whole in a code fence, or have headings
that match no spec — so they score zero, fall to Unknown, and are skipped
by `rac validate`. The corpus therefore contains zero Prompt artifacts even
though Prompt is a first-class family (REQ — v0.6.2 Prompt Artifacts), and
the guidance that governs how agents work on RAC is the one body of product
knowledge the gates do not actually check.

The Prompt family was introduced precisely for "prompts to review
requirements, summarize roadmaps, analyze decisions, prepare briefs ... and
guide AI-assisted workflows" (v0.6.2). Agent operating guidance is exactly
that: instructions an AI agent reads to produce work. The mismatch is not
conceptual; it is that the files were never written to the schema.

## Decision

Agent operating-guidance documents under `rac/prompts/` are Prompt
artifacts and conform to the Prompt schema: a single title and the required
sections `Objective`, `Input`, `Instructions`, `Output`, with
`Constraints`, `Examples`, and `Evaluation` used where they apply.

The required sections map onto operating guidance as follows, and this
mapping is the canonical reading for any future guidance prompt:

- **Objective** — the outcome adhering to the guidance produces (the goal
  the prompt serves).
- **Input** — the situation in which the guidance applies and the material
  the agent should already have: the roadmap item, ADRs, the corpus, the
  diff, repository state, available MCP tools.
- **Instructions** — the substance: the rules, steps, gates, and checklists
  the agent follows. The bulk of each document lands here.
- **Output** — the expected agent behavior or deliverable: a release-gate
  review in the given format, a pull-request body, a compact handoff, an
  approved and gate-passing change.
- **Constraints / Examples / Evaluation** — hard boundaries, concrete
  illustrations, and how to tell adherence succeeded, where the document
  carries them.

Each guidance prompt declares `Related Decisions: ADR-047` so the link
between the convention and the artifacts is traceable. Relationship
sections must contain resolvable artifact references only; prose
"requirements" or "decisions" are folded into the body rather than left in
relationship sections (they would otherwise fail
`rac relationships --validate`).

This decision governs operating-guidance prompts. It does not require every
Markdown file in the repository (READMEs, changelogs, `CLAUDE.md` itself)
to become an artifact; those remain recognized-as-Unknown documents
(ADR-010).

## Consequences

### Positive

- `CLAUDE.md`'s claim becomes true: the guidance that steers agent work is
  validated by the same gates as the rest of the corpus, and drift (a
  dropped required section, a malformed file) is caught by
  `rac validate rac/`.
- The Prompt family stops being a schema with no instances in the corpus;
  the artifact vocabulary RAC documents is one RAC itself uses.
- The mapping gives a repeatable shape for future guidance, so new
  operating prompts are written to the schema rather than as free prose.

### Negative

- Each file gains YAML frontmatter, which is included verbatim when
  `CLAUDE.md` imports the prompt. The noise is small and the trade for
  validation is accepted.
- Reorganizing prose under fixed headings is a one-time content edit per
  file; the substance is preserved, but the diff is large.
- The `Objective/Input/Instructions/Output` frame is a slightly loose fit
  for the most context-like document (`rac-agent-session-start`), where
  "Output" is an end-state rather than a single artifact. Accepted: the
  mapping above names that reading explicitly.

### Risks

- Future guidance is added as prose again, recreating Unknown files.
  Mitigation: this ADR records the convention, and `rac validate rac/`
  now reports a regression because the corpus expects these to be valid
  Prompt artifacts.

## Alternatives Considered

### Leave the files as Unknown prose and soften the CLAUDE.md claim

Keep the guidance unstructured and reword `CLAUDE.md` so it no longer says
the gates validate it.

#### Advantages

- No content churn; the files stay maximally free-form.

#### Disadvantages

- Forfeits validation on the highest-leverage documents in the corpus, and
  leaves the Prompt family with zero real instances. RAC would not eat its
  own dog food on the one artifact type built for exactly this content.

### Invent a new "guidance" artifact type

Add a bespoke spec for agent guidance instead of reusing Prompt.

#### Advantages

- A frame tailored to operating guidance.

#### Disadvantages

- A new artifact-specific type cuts against the spec-driven, minimal-type
  posture; Prompt already models objective/input/instructions/output for
  AI-assisted workflows. A second, near-identical type is duplication.

## Relationship to Other Decisions

- ADR-004 (artifact model): classification is structural and schema-driven;
  this decision brings the guidance files under that model rather than
  changing it.
- ADR-010 (unrecognized documents): non-artifact Markdown stays Unknown;
  this decision narrows that set by classifying the guidance files, not by
  requiring every file to be an artifact.

## Success Measures

- All seven `rac/prompts/rac-agent-*` files classify as Prompt and pass
  `rac validate rac/`.
- `rac relationships rac/ --validate` and `rac review rac/` stay clean (no
  priority 1-2 findings) with the converted files present.
- A future guidance prompt is authored against the Objective/Input/
  Instructions/Output mapping rather than as free prose.

## Review Date

Review if a guidance document genuinely cannot be expressed in the Prompt
schema, at which point the mapping or the alternative type is revisited.

## Related Requirements

- rac-trust-transparency
- v0.6.2-prompt-artifact
