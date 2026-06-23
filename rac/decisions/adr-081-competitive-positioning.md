---
schema_version: 1
id: RAC-KVTSP3P97GVE
type: decision
---
# ADR-081: Competitive Positioning — The Source of Truth for Product Decisions

## Context

ADR-036 records Lore's product *identity*, and the `rac-growth-positioning`
requirement records a narrow README relationship to spec-driven-development tools
and OKF. Neither records where Lore sits against the broader competitive field, so
evaluators have no recorded answer to "what is this versus the tools I already
know," and the team has no shared positioning stance to derive a README, growth
artifacts, or a pitch from.

The team-scale (20+) market research (archived at
`docs/research/team-scale-landscape.md`, a reference document, not an artifact —
ADR-010/ADR-024) mapped four adjacent categories and produced the findings that
shape positioning:

- **Capture is solved and identical everywhere** (Markdown-in-git); survival at 20+
  is decided by **staleness, discovery, and workflow-fit**, not capture.
- **Every AI agent-context tool stores coding rules or indexed code — none governs
  product decisions.** That is open whitespace. (Cursor, Amp, Cody, Augment, Glean,
  Dust, Onyx.)
- **Enterprise requirements management (Jama/DOORS/Polarion) has the governance but
  crushing friction** — per-seat pricing that throttles collaboration, heavyweight
  admin, scale bottlenecks, and lock-in.
- **Sourcegraph publicly reversed out of embeddings** for enterprise context,
  validating the no-embeddings stance (ADR-066); **DORA 2025 names "decision logs"**
  as an AI-effectiveness lever; **staleness leading to trust collapse is the #1
  abandonment driver**, and git + PR review alone is empirically insufficient to
  prevent it.

## Decision

Position Lore as **the shared, git-native, deterministic source of truth for
product *decisions*** — requirements, decisions, roadmaps, designs — served to
coding agents. The stance has four pillars:

- **The whitespace it owns.** Governed *product decisions* are the knowledge class
  no agent-context tool manages (they hold coding rules or indexed code), and the
  durable layer above spec-driven tools (which treat requirements as ephemeral
  inputs). This extends `rac-growth-positioning`'s "layer above SDD" thesis to the
  whole field.
- **What it competes on.** The **freshness/drift problem** (a deterministic,
  git-native equivalent of enterprise "suspect links" — the capability DOORS/Jama
  charge six figures for) and **trust** ("verification you can't fake": PR review
  plus immutable git history plus machine-checkable validation), at **zero per-seat
  collaboration tax and zero lock-in** (it is just Markdown in the team's repo).
- **What it deliberately does *not* compete on.** Embeddings / vector-RAG (ADR-066;
  the lane a major incumbent reversed out of, and precision-poor for decisions);
  agent runtime and code generation (ADR-069 split routing out; Lore is not an
  SDD/codegen tool); and being a general content store (ADR-024).
- **The wedge and the complement.** The wedge is the governance and traceability of
  enterprise RM, git-native and friction-free, for teams priced out of or crushed by
  it. The complement is that Lore *composes with* — does not compete against —
  agent-context rules (`AGENTS.md`/`.cursor/rules`), SDD tools, and OKF, sitting at
  the durable-decisions layer above them.

All positioning claims must be verifiable and stated as complementary, never "better
than," consistent with `rac-growth-positioning`'s constraints.

## Consequences

There is now a recorded positioning the README, growth artifacts, and any pitch can
derive from, and a shared answer to "what is this versus X." The differentiators
become claims the product must *back*: the freshness/drift capability (recorded as
future intent), and the deterministic grounding benchmark (ADR-066) as the proof
that curated decision context helps — the one number competitors cannot show.

Trade-offs and honest limits, recorded so positioning does not outrun reality:

- There is **no published proof that curated decision context lifts agent task
  success**; the benchmark is how Lore earns the claim rather than asserts it.
- The **freshness gap is real** until the drift-detection work ships — it is the
  softest spot *and* the differentiator, so it is load-bearing.
- Positioning **only wins if Lore replaces a silo, not adds one** beside
  Confluence/Slack; "the source of truth" is the claim, "another store" is the
  failure.

## Status

Proposed

## Category

Product

## Alternatives Considered

- **Position as a spec-driven-development / spec tool.** Rejected: SDD treats
  requirements as ephemeral inputs and owns the spec→code path (with its openly
  unsolved drift problem); Lore is the durable-decisions layer *above* it, not a
  competitor (the existing `rac-growth-positioning` thesis).
- **Position as an agent-memory / RAG tool.** Rejected: that is the embeddings /
  vector lane ADR-066 excludes and a major incumbent (Sourcegraph) publicly reversed
  out of — and it is precision-poor exactly where decisions live.
- **Position as enterprise requirements management.** Rejected: matching DOORS/Jama
  on governance by adopting their cost, lock-in, and heavyweight footprint reproduces
  the friction that kills adoption; Lore's wedge is the opposite — friction-free and
  git-native.
- **Record no positioning (status quo).** Rejected: evaluators misfile Lore against
  whichever category they arrived from, and the team has no shared stance to build
  its README, growth work, or pitch on.

## Related Decisions

- adr-036
- adr-066
- adr-024
- adr-069
- adr-018

## Related Requirements

- rac-growth-positioning
