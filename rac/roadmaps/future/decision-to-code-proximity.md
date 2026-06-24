---
schema_version: 1
id: RAC-KVTRP9G4CN2N
type: roadmap
---
# RAC — Decision-to-Code Proximity (Future)

## Status

Planned

Unscheduled — captured for future consideration from the team-scale (20+) market
research. It graduates out of `future/` into a versioned series when prioritised.

## Context

A consistent finding across the research: at 20+ engineers, **discovery and
proximity-to-code — not capture — decide whether a decision corpus survives.**
Capture is solved and identical everywhere (Markdown-in-git). What separates the
tools that get read from the ones that rot is whether the record surfaces *where
the work happens*. ADRs "rot when stored away from the code, where engineers do
not look"; ThoughtWorks' rule is to keep decisions "in source control… in sync
with the code"; Backstage's ADR plugin attaches records to the service they affect
via a `backstage.io/adr-location` annotation so they "sit next to the services
they affect."

Lore's artifacts live in `rac/`, validated and linked to *each other*, but they
are not linked to the **code or components they govern**. So an agent (or a human)
working in `src/auth/` has no deterministic way to ask "which recorded decisions
govern this code?" This item closes that gap — the discovery differentiator — and
it is also the precondition for the drift gate in
`freshness-and-drift-detection` (you cannot flag a decision "suspect" when its code
changes until the decision knows which code it governs).

## Outcomes

- An artifact can declare the code paths or components it governs, validated like
  any other reference.
- Given a file or directory, a deterministic lookup returns the artifacts that
  govern it — so the right decision surfaces at the point of work, for an agent or
  a developer.

## Initiatives

### Initiative 1 — Code-scope references on artifacts

An optional, declared reference on an artifact naming the code it governs — path
globs or a component identifier — validated deterministically in the
asset-reference style (ADR-019). Declared and human-reviewed, never inferred from
code content.

### Initiative 2 — "Decisions affecting this path" lookup

A deterministic CLI and MCP lookup: given a file or directory, return the
governing artifacts (and their status), so an agent editing code is grounded in
the decisions that constrain it without searching. Read-only, additive (ADR-007).

### Initiative 3 — Feeds proximity-aware surfacing and drift

The code-scope reference becomes the join that lets the Explorer show "decisions
for this area" and lets the drift gate flag an artifact when its governed code
changes (the `freshness-and-drift-detection` tie-in).

## Constraints

- Declared and validated, never inferred (ADR-074, ADR-065): code scope is an
  authored reference a human reviews, not a guess from parsing code.
- Deterministic and offline (ADR-066): the path↔artifact lookup is a pure function
  of declared references and the file tree.
- No database: associations are declared references resolved at read time.

## Non-Goals

- Parsing or understanding code semantics; this maps declared paths, not meaning.
- Auto-associating decisions to code by similarity or embeddings.

## Success Measures

- An artifact can name the code it governs and the reference validates.
- Querying a path returns its governing artifacts deterministically and
  reproducibly.
- The association is reusable by both discovery (Explorer/CLI/MCP) and the drift
  gate.

## Assumptions

- Proximity-to-code is the discovery mechanism that most affects whether a 20+
  team's decision corpus is actually consulted, per the research.
- Declared path scopes are precise enough to be useful without code analysis, the
  same way `## Related` references are useful without semantic linking.

## Risks

- Path globs drift as the codebase is refactored, leaving stale scopes. Mitigation:
  this is exactly the drift the freshness gate is meant to surface — a moved path
  becomes a "suspect" signal, not a silent rot.

## Related Decisions

- adr-019
- adr-074
- adr-028
- adr-065

## Related Roadmaps

- freshness-and-drift-detection
