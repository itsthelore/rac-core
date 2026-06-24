---
schema_version: 1
id: RAC-KVSV68H019N9
type: roadmap
---
# Lore Capture — Further Exploration (Future)

## Status

Planned

Unscheduled — recorded as a backlog of *exploration and documentation* that the
capture work surfaced but did not resolve. It is intent, not a committed release,
and must not displace nearer-term work. Each initiative is a candidate for its own
design or roadmap once picked up.

## Context

Two designs worked out the capture story so far: `lore-capture-surfaces` (the
skill-is-brain / host-is-interface model and the four host surfaces) and
`lore-slack-capture-flow` (the end-to-end Slack write-and-approve pipeline). The
research behind them repeatedly turned up adjacent questions that are real but out
of scope for those artifacts. This roadmap parks them in the corpus so they are
not lost, with enough framing that a future session can pick one up and scope it
properly. Following ADR-047, durable thinking lives here rather than in a tool's
scratch space.

## Outcomes

- The open threads from the capture work are recorded as trackable intent, so the
  next builder starts from "what's already known and still open" rather than
  re-deriving it.
- Lore has a clear-eyed view of the capture surface area beyond Slack — other
  ingest points, the quality of the structuring step, and how to know any of it is
  working — without committing to build them prematurely.

## Initiatives

### Initiative 1 — Other ingest points

Explore capture surfaces beyond Slack and the harness: email→artifact (forward a
decision to an address), the `/intake` GitHub Action drop-zone for documents
(`rac ingest` self-service), and extraction from trackers/wikis
(Jira / Linear / Confluence). The tracker case is **ADR-017-gated**: it must
extract the durable decision or long-lived requirement, never mirror tickets,
owners, or sprints, and likely needs an explicit ADR before it is built.

### Initiative 2 — Classification-quality evaluation

The freeform→typed structuring step is where capture can quietly go wrong (wrong
type, mis-mapped sections). Define how its quality is measured and how its mistakes
are surfaced for the human-ratify gate rather than hidden — consistent with the
deterministic, no-LLM-judge discipline RAC already holds for grounding (ADR-066).

### Initiative 3 — Corpus-lift measurement

Decide how to tell whether capture actually *works*: does it raise corpus
completeness and recency, and are knowledge owners (not just maintainers) authoring
through it? This is the success signal `rac-capture-skill` names as the trigger to
schedule a host surface out of `future/`.

### Initiative 4 — Inbound-bot security review

A capture bot is an internet-exposed, multi-tenant service that crosses a model
boundary. Scope a security review covering the boundary crossing, prompt injection
(thread content is untrusted, ADR-065), least-privilege scopes (Slack and the
GitHub App), secret handling, and the data-governance disclosures admins expect.

## Constraints

- Each initiative respects the recorded boundaries: knowledge not work (ADR-017),
  human PR review as the trust boundary (ADR-065), user-managed AI credentials and
  no AI in core (ADR-035, ADR-002).
- Nothing here is scheduled; picking up an initiative means scoping it as its own
  design/roadmap first, not expanding an existing release.

## Non-Goals

- Committing to build any ingest point, evaluation harness, or security programme
  in this artifact — it records intent, not a release.
- Re-opening settled decisions; tracker import in particular stays gated behind an
  explicit future ADR.

## Success Measures

- A future session picking up any initiative finds the open questions and
  constraints already framed here, and turns one into a scoped design/roadmap
  without re-deriving the research.
- The corpus-lift initiative yields a concrete, deterministic signal that could
  justify scheduling a capture host out of `future/`.

## Assumptions

- The capture core (`rac-capture-skill`) is the prerequisite; these followups
  presuppose it exists or is in progress.
- The published CLI/export contract stays stable and additive (ADR-007, ADR-063),
  so connectors and evaluators can build on it without engine changes.

## Risks

- **Scope sprawl.** A backlog can invite premature building; mitigated by keeping
  every item explicitly unscheduled and ADR-gated where it touches the work/
  knowledge boundary.
- **Staleness.** Fast-moving externals (Slack AI surfaces, tracker APIs) may date
  the framing; mitigated by treating each item as a starting point to re-verify,
  not a spec.

## Related Decisions

- ADR-002
- ADR-017
- ADR-035
- ADR-065
- ADR-066

## Related Roadmaps

- rac-capture-skill
