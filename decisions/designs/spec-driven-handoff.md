---
schema_version: 1
id: RAC-KX8EAGMSD98N
type: design
---
# Spec-Driven Handoff — Roadmap Decomposition and Session Context Packets

## Status

Proposed

## Context

Spec-driven development is the dominant community workflow in the July 2026
demand research (`research/2026-07-agentic-tooling-demand.md`): specs and
plans in git-tracked Markdown, decomposed into subtasks with acceptance
criteria, a fresh agent session per subtask. RAC models the upstream half —
roadmaps, designs, decisions, validated and linked — but stops at the
boundary: ADR-093 puts execution tracking in GitHub Issues and ADR-017
keeps RAC out of work management. Nothing today turns a roadmap initiative
into agent-sized work items, and nothing assembles the context a fresh
session needs. The community routes around the gap with hand-rolled
markdown; the boundary itself is untooled.

## User Need

A developer (often solo, agent-equipped) has a scoped roadmap item in the
corpus and wants to execute it as a series of fresh agent sessions. They
need each subtask to carry its acceptance criteria and its slice of
corpus context — governing decisions, the initiative's intent, links back
to the artifacts — without hand-assembling a context file per session, and
without RAC becoming the tracker.

## Design

Two additive, deterministic projections at the corpus/tracker boundary:

- **Decomposition export.** `rac export --issues <roadmap-artifact>` emits
  one issue body per initiative of a roadmap artifact: initiative text,
  acceptance criteria derived from the artifact's success measures and any
  linked requirement statements, plus a footer naming the governing
  artifact ids. Output is files (or `--json`), file-first per ADR-011 —
  a wrapper or the GitHub Action pushes them to the tracker; core never
  calls a tracker API. Round-trip traceability uses the external-reference
  edge vocabulary already ratified (ADR-087, ADR-096): the issue links the
  artifact id, the artifact may carry the ticket reference.
- **Context packet.** `rac export --context <path-or-artifact-id>` emits a
  single bounded Markdown packet for starting a fresh agent session on one
  subtask: the governing decisions for the code scope (the existing
  `decisions_for_path` reader), the initiative text and acceptance
  criteria, linked designs, and pointers (ids, not bodies) to everything
  else — the corpus-backed version of the fresh-session-per-subtask
  pattern the community assembles by hand. Deterministic and byte-stable
  for identical corpus bytes, same discipline as `--agent-rules`
  (agent-decision-enforcement, ADR-067).

## Constraints

- ADR-017 and ADR-093 are not amended: RAC emits projections; issue
  lifecycle, assignment, and status live in the tracker. The export is
  one-way and stateless.
- ADR-011 file-first: outputs are files; tracker delivery is a consumer's
  job (Action, wrapper, or the human).
- ADR-005/ADR-007: both verbs carry human and JSON output under the
  stability contract.
- ADR-002: decomposition is structural (initiative sections, linked
  requirement statements) — no model in core inventing acceptance criteria
  that are not in the artifacts.
- Context packets compete for the agent's attention budget; the packet
  must be distilled with pointers, the same lesson as the ADR-067 rules
  block.

## Rationale

The demand is real but the settled boundary is right: owning execution
state would make RAC a work tracker (rejected in ADR-017 deliberately).
Projections capture the value — the corpus becomes the source both for
what the work is and for what a session needs to know — while the tracker
keeps the state. It also positions orchestrators and verification gates
(demand categories RAC should not compete in) as consumers: they spawn the
sessions; RAC supplies the packets.

## Alternatives

- A task/subtask artifact family inside RAC. Rejected: contradicts ADR-017;
  duplicates tracker state that goes stale immediately.
- Tracker-API integration in core (create issues directly). Rejected:
  breaks ADR-011 file-first and drags provider auth into core; the
  connectors layer (ADR-073) is the home for outbound delivery.
- Leaving decomposition entirely to the agent with the corpus as reference.
  Status quo; forfeits determinism and repeatability at exactly the step
  where drift between spec and work items begins.

## Open Questions

- Does the decomposition unit map 1:1 to roadmap initiatives, or do large
  initiatives need a structured sub-item convention inside the artifact?
- Where does `--context` draw the packet size line, and is the budget
  configurable or fixed like the Guide surface (ADR-033)?
- Should the GitHub Action grow an issue-sync mode, and does that belong
  to this repo or a connector (ADR-073, ADR-092)?

## Related Decisions

- adr-002
- adr-005
- adr-007
- adr-011
- adr-017
- adr-067
- adr-073
- adr-087
- adr-093
- adr-096

## Related Roadmaps

- decisions-on-pr
- agentic-demand-alignment
