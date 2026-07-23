---
schema_version: 1
id: RAC-KWK8HQ19S0AA
type: design
---
# Design: Lean Context Delivery Measurement

## Status

Accepted

The concrete accounting method behind `lean-context-delivery` Initiative 1 —
input to the implementation, not a substitute for the acceptance criteria in
`rac-mcp-surface-budget`. Implemented in `rac/mcp/surface.py` and checked by
`tests/test_mcp_surface_budget.py`; the Open Questions below are now resolved and
recorded there.

## Context

The `lean-context-delivery` roadmap makes leanness a measured property: the
agent-facing footprint must be counted and held to a budget, so Lore does not
become the context tax it warns against. ADR-033 already asserts a response
budget, but assertion is not measurement — nothing today produces a number for
the tool surface, so description and schema growth is invisible until an agent
feels the tax. This design records *how* the number is produced: what is
counted, over what fixed input, and how the result becomes a regression check.
It deliberately adds no served behaviour — it measures the existing five-tool
`lore` surface.

## User Need

A maintainer needs a reproducible signal that the agent-facing surface has not
bloated. An agent integrator needs confidence that connecting the `lore`
server spends a bounded, known amount of context before any answer is
returned. Both need a single number they can trust across releases and diff in
review, computed the same way every time.

## Design

Three counted components, one fixed fixture, one offline reducer:

- **What is counted.** The token cost of (1) the MCP tool *descriptions* for
  the five-tool surface, (2) their JSON *schemas* as advertised to a client,
  and (3) a *typical response* — a representative `search_artifacts` result
  page and a representative `get_artifact` payload — taken over a pinned
  fixture corpus. Descriptions plus schemas are the standing cost paid on
  every session; the typical response is the per-call cost.
- **The fixed fixture.** A small, version-controlled corpus and a fixed set of
  representative queries, pinned alongside the check so the input never drifts
  silently. The same fixture drives the `rac-selective-retrieval-default`
  assertion, so one corpus serves both.
- **The reducer.** A deterministic, offline token count (ADR-066): no model
  call, no network. A fixed tokenisation rule maps the serialized surface and
  the fixture responses to an integer. The rule is stated so the number is
  reproducible from the inputs alone.
- **The check.** The integer is compared against a stated budget. Exceeding it
  is a regression failure surfaced in the test suite; a change within budget
  passes silently. The budget and its rationale live beside the check, so a
  deliberate increase is a reviewed edit, not silent drift.
- **Relationship to ADR-033.** This measures the *standing* surface cost; the
  response budget bounds *individual* response size at serve time. They are
  consistent and complementary — the measurement never changes the response
  budget's truncation behaviour.

## Constraints

- Deterministic and offline (ADR-066): a fixed input yields a fixed number,
  with no model or network dependency.
- Measurement only: it counts the existing five-tool surface (ADR-030) and its
  responses; it adds no tool, removes none, and compresses nothing.
- Consistent with the response budget (ADR-033); the CLI-first posture (ADR-005)
  is unaffected — this measures the MCP surface, not the CLI path.
- No semantic compression or summarisation is introduced to hit a budget; the
  surface stays lean by being small, not by being lossily shrunk.

## Rationale

A single deterministic integer over a pinned fixture is the cheapest signal
that catches the failure mode the roadmap fears — silent surface growth. It is
reviewable (a number in a diff), regression-checkable (a threshold in a test),
and honest (offline, reproducible, no model in the loop). Modelling "real"
agent context more richly would trade determinism for fidelity Lore does not
need for a small, structured corpus.

## Alternatives

- **Assert the budget in prose only (no measurement).** Rejected: it leaves the
  drift invisible, which is the exact gap this initiative closes.
- **Measure against a live model's tokeniser over network.** Rejected: breaks
  the offline/deterministic constraint (ADR-066) and makes the number
  irreproducible across environments.
- **Semantic compression to shrink payloads under budget.** Rejected as a
  Non-Goal of the roadmap: it would make responses lossy and non-deterministic.

## Accessibility

Not applicable — this is a measurement method for an agent-facing surface, not
a human interface. The maintainer-facing artifact is a plain integer and a
pass/fail check, readable in ordinary test output.

## Style Guidance

The reported number is a bare integer with its budget and the fixture it was
measured over, presented as data beside its threshold — never a score or a
verdict about quality (ADR-034 posture). Keep the budget and its rationale
adjacent, so a change to either is reviewed together.

## Open Questions

All four are now resolved and encoded in `rac/mcp/surface.py`:

- **Tokenisation rule** → a dependency-free deterministic count: word runs
  (alphanumeric) and each standalone punctuation character count as one token
  (regex `[A-Za-z0-9]+|[^\sA-Za-z0-9]`). A real model tokenizer would tie the
  number to a model vocabulary and add a dependency, against the offline/lean
  posture (ADR-066); the design's own Rationale accepts a faithful-enough proxy,
  and this is it. Stable across serialization changes because it counts the
  serialized bytes as advertised, not a model's view of them.
- **Initial budget + headroom** → the standing surface measures ~915 tokens
  today; the enforced budget is **1000**. It may be raised only with explicit
  approval and written justification, up to a hard cap of **1250** (a test pins
  that the budget constant itself stays within the cap, so a bump is never
  silent).
- **Typical response** → a small fixed basket — a representative
  `search_artifacts` page and a `get_artifact` payload — measured over the pinned
  `examples/guide` corpus, each held under a per-call ceiling.
- **Separate vs combined budgets** → **separate**: a corpus-independent standing
  budget (descriptions + schemas, the headline context-tax number) and a per-call
  budget over the fixture basket. They catch different regressions — surface bloat
  versus response-serialization bloat.

## Related Requirements

- rac-mcp-surface-budget
- rac-selective-retrieval-default
- rac-cli-first-delivery

## Related Decisions

- adr-005
- adr-030
- adr-033
- adr-034
- adr-066

## Related Roadmaps

- lean-context-delivery
