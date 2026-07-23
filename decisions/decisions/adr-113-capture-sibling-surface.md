---
schema_version: 1
id: RAC-KX8GEA45HRBM
type: decision
---
# ADR-113: Capture Writes Arrive Through a Sibling Surface, Not Guide

## Status

Accepted

## Category

Architecture

## Context

The `guide-capture-path` design proposes an agent-facing capture path: a
draft-only `propose_artifact` capability that writes untrusted drafts,
preserving both gates of the two-gate capture model (ADR-077) and the
human-review trust boundary (ADR-065). Its open question was where the
capability mounts.

Mounting it inside Guide is not an amendment-free option. Guide's
read-only property is ratified decision text, not an incidental posture:
ADR-031 pins "no file creation, modification, deletion, or Git operation
is importable from the server layer, enforced by an isolation test";
ADR-032 frames every tool call as a stateless read; ADR-030 pins the
tools-only, read-only surface enumeration and its description budget
(ADR-033). Any write tool inside Guide falsifies that text and requires
superseding three decisions at once.

A second force points the same way. RAC's presence is expanding beyond
the CLI and MCP — the editor extension exists (ADR-067, ADR-068), and a
desktop or web application face is a plausible next surface (the Explorer
line, ADR-028/ADR-029; the overlay and capture host surfaces recorded in
`lore-capture-followups`). Every such face needs the same write
capability with the same guarantees. Binding capture to Guide's MCP
contract would couple a general write path to one delivery channel and
its budget; each new face would re-open the Guide contract again.

## Decision

Capture writes arrive through a sibling write surface, separate from
Guide. Guide remains read-only; ADR-030, ADR-031, ADR-032, and ADR-033
are not amended.

- The sibling surface is a separately-mounted module that the Guide
  server layer never imports. The ADR-031 isolation battery continues to
  pass unchanged, and gains a counterpart: the sibling surface imports
  write services but must not be importable from Guide.
- The surface is draft-only by construction: it can mint and write
  untrusted drafts (ADR-077 gate one's mechanical step) and can never
  write into the trusted corpus tree, merge, or promote. Promotion stays
  human-reviewed PR (ADR-065).
- It is one write path with many faces: the MCP capture tool is its first
  consumer, and any future desktop or web application face consumes the
  same surface rather than growing its own write path.
- It ships opt-in and off by default; enabling it is an explicit server
  or host decision. Audit obligations (ADR-084) extend to its writes.
- Its tool and endpoint contract is pinned and budgeted in its own design
  under the same discipline as Guide's (`guide-tool-surface` precedent),
  but with its own budget — it does not spend Guide's.

## Consequences

- Guide's contract, isolation guarantee, and standing token budget are
  untouched; existing consumers see no change.
- Agent capture and any future app face share one tested write path with
  the two-gate model enforced by construction, not per-surface
  convention.
- The cost is a second pinned surface to version and test, and a second
  mounting step for hosts that want capture — accepted as the price of
  keeping the read surface's guarantees simple and absolute.
- A future decision may still mount both surfaces on one server process
  (one port, two contracts); this decision constrains import graphs and
  contracts, not process topology (ADR-098 governs shared serving).

## Alternatives Considered

- A sixth tool inside Guide. Rejected: requires superseding the read-only
  clause of ADR-031, the surface enumeration of ADR-030, and re-measuring
  the ADR-033 budget; couples every future write-capable face to the MCP
  contract.
- Keeping capture CLI/skill-only. Rejected as a terminal state: it leaves
  the mid-session capture need unmet (July 2026 demand research) and
  pushes each future app face to invent its own write path.
- A fully separate server binary. Deferred, not rejected: the sibling
  module can be packaged either way; ADR-098 topology questions are
  decided when the first non-MCP face ships.

## Related Decisions

- adr-028
- adr-029
- adr-030
- adr-031
- adr-032
- adr-033
- adr-065
- adr-067
- adr-068
- adr-077
- adr-084
- adr-098

## Related Designs

- guide-capture-path

## Related Roadmaps

- agentic-demand-alignment
- lore-capture-followups
