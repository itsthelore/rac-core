---
schema_version: 1
id: RAC-KTW0M81HX5C6
type: decision
---
# ADR-033: Guide Response Budget

## Status

Accepted

## Category

Technical

## Context

Guide tool responses land directly in an agent's context window. That window
is the scarcest resource in the session: whatever Guide spends on one
response is unavailable for the agent's actual task.

An unbounded `search_artifacts` over a large corpus, or a `get_artifact` on a
long document, can flood the context with more text than the agent needed —
degrading exactly the grounding behaviour Guide exists to produce. A server
that helps the agent by drowning it has failed.

The failure must also be legible to the agent. A silently truncated response
is worse than a smaller complete one: the agent cannot know what it is
missing. Truncation that breaks structure mid-element is worst of all — a
response that stops mid-JSON is unparseable noise.

Budgets must be deterministic (ADR-032 pins byte-stable output), which rules
out token counting: token counts vary by model and tokenizer version, while
character counts are stable everywhere.

## Decision

Every Guide tool response is subject to a per-response character budget.

- The default budget is 10,000 characters, configurable at server startup.
- Oversized responses are truncated deterministically at whole-item
  boundaries — whole match entries, whole relationship entries, whole
  content blocks — never mid-element and never mid-JSON.
- A truncated response carries an explicit truncation marker field stating
  that truncation occurred, what was omitted (count where known), and how to
  narrow the query.
- The marker field and truncation behaviour are part of the pinned tool
  output contract, covered by contract tests.

The budget counts characters of the serialized JSON; the UTF-8 byte length on
the wire may exceed it for non-ASCII content — accepted to keep the unit
deterministic across models.

## Consequences

### Positive

- A single tool call cannot flood the agent's context window.
- The agent always knows when a response is partial and how to get the rest.
- Responses remain structurally valid at every budget.
- Character budgets keep truncation deterministic across models and
  versions.

### Negative

- Large artifacts are not retrievable in one call once they exceed the
  budget.
- Whole-item truncation can undershoot the budget noticeably when items are
  large.

### Risks

- 10,000 characters proves wrong in practice — too small for real artifacts
  or too large for small contexts. Mitigation: the default is configurable
  and the number is a contract detail, not an architecture.
- Truncation logic drifts between tools. Mitigation: one shared budget
  implementation, one contract test battery.

## Alternatives Considered

### No cap

Return whatever the query produces.

#### Advantages

- Simplest implementation; never withholds data.

#### Disadvantages

- One broad search can consume the agent's entire working context — the
  failure mode this decision exists to prevent.

### Cursor pagination

Return a page plus a cursor for the next call.

#### Advantages

- Complete data is reachable across calls.

#### Disadvantages

- Cursors are session state, contradicting the stateless server (ADR-032).
- Agents handle "narrow your query" hints well; paging through a flood is
  rarely what the grounding moment needs.

### Token-based budget

Cap responses by model token count.

#### Advantages

- Matches the resource actually being protected.

#### Disadvantages

- Token counts vary by model and tokenizer version, breaking deterministic,
  byte-stable output.
- Requires a tokenizer dependency for no contract benefit.

A deterministic character budget with explicit markers is selected.

## Relationship to Other Decisions

- ADR-007 (JSON contract stability): the truncation marker is an explicit,
  pinned field of the tool output contract, not incidental behaviour.
- ADR-032 (stateless reads): whole-item deterministic truncation preserves
  the byte-stability that statelessness promises; cursors were rejected
  partly to protect it.
- ADR-030: the budget is part of what makes a four-tool surface safe to
  expose to autonomous callers.

## Success Measures

- Contract tests pin truncation behaviour byte-for-byte at the boundary.
- No demo or dogfood session shows an agent derailed by an oversized
  response.
- Truncated responses observed in practice carry actionable narrowing
  hints.

## Review Date

Review if real usage shows the default budget materially mis-sized, or if a
client gains protocol-level response streaming that changes the trade-off.

## Related Requirements

- rac-agent-context-guide

## Related Designs

- guide-tool-surface

## Related Roadmaps

- v0.10.0-guide-foundation

## Applies To

- src/rac/mcp/
