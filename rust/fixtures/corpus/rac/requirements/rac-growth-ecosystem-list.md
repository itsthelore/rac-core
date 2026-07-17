---
schema_version: 1
id: RAC-KTYBK7FSW6HS
type: requirement
---
# RAC Growth — Ecosystem List

## Status

Accepted

## Problem

ADR-012's open-core strategy measures success partly by third-party
tooling and adoption of RAC artifact formats outside the RAC CLI, but
the repository gives a would-be builder no evidence that anything
already consumes the engine. The consumers that do exist — the dogfood
corpus, the agent skill, the runnable MCP grounding example — are
scattered across `rac/`, `.claude/skills/`, and `examples/`, with no
single page naming them. Without a visible, honest list, derivatives
look unprecedented rather than normal.

The failure mode to avoid is the aspirational ecosystem page: a long
list padded with planned or hypothetical integrations. A short list of
verified entries is more credible than a long list of intentions.

## Requirements

- [REQ-001] An ecosystem list shall exist at `docs/ecosystem.md` (the user documentation layer per ADR-022), naming things that consume RAC artifacts or the RAC engine.
- [REQ-002] Every entry shall be real and verified at the time of listing: the thing it names exists, on disk in this repository or at a stated external location, and works against a released engine version. Planned, in-progress, or placeholder entries shall not be listed.
- [REQ-003] At seed time the list shall contain exactly three entries — the dogfood corpus (`rac/`), the Claude Code skill (`.claude/skills/rac-artifacts/`), and the MCP grounding example (`examples/guide/`) — and shall not be padded beyond what is verifiable.
- [REQ-004] The list shall be structured so that adding one entry is a one-line change (one table row per entry), keeping a third-party addition reviewable in isolation.
- [REQ-005] The page shall state the entry criteria and shall describe how an entry is added in neutral terms; it shall contain no solicitation language while the contribution policy remains pending (GATE-2).

## Success Metrics

- `docs/ecosystem.md` exists with exactly three entries, each of whose
  cited paths resolves on disk in this repository.
- A test addition of a fourth entry is a single-row diff.
- The page contains the entry criteria and no solicitation phrasing.

## Risks

- A three-entry list, all first-party, could read as thin; that is the
  honest current state and padding it would be worse.
- Entries can rot — a listed path moves or an external repository
  disappears — and nothing currently re-verifies them; the list needs
  the same review discipline as any other documentation.

## Assumptions

- `docs/` remains the correct layer for user-facing pages (ADR-022) and
  the README links rather than duplicates this content.
- The contribution policy (GATE-2) will eventually define how external
  authors propose entries; until then the page describes the mechanism
  without inviting use of it.

## Related Decisions

- adr-012
- adr-022

## Related Requirements

- rac-growth-extensibility
