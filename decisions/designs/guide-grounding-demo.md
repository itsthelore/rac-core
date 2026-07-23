---
schema_version: 1
id: RAC-KTW0M82KTAXV
type: design
---
# Guide Grounding Demo

## Context

The strategic purpose of RAC Guide is a provable claim:

> An agent connected to RAC respects decisions an unconnected agent
> violates.

If that claim cannot be demonstrated in ninety seconds, the server is
plumbing without a pitch. The demo is therefore a requirement, not marketing
collateral — it is the acceptance test for the entire Guide effort and the
centerpiece of the launch (REQ-005 of the Agent Context Guide requirement).

The demo also closes the loop on ADR-034: no conflict-detection tool exists,
so the demo is the evidence that serving facts is enough — the agent itself
recognizes the conflict and cites the decision.

## User Need

Three audiences, one artifact:

- A launch viewer with no RAC context must be able to state what the product
  does after watching once.
- A stranger must reproduce the grounded behaviour from the repository alone,
  without help from the author.
- The maintainer needs a regression check that tool descriptions still
  trigger retrieval on current agent models.

## Design

### Scenario corpus

A self-contained RAC corpus in `examples/guide/`, separate from the existing
`examples/example_dashboard_v*.md` walkthrough files, with its own
`.rac/config.yaml`:

- one decision artifact recording a deliberate technical choice with stated
  consequences — true-to-life, the kind a real team records (a deliberately
  chosen locking strategy, a soft-delete-only data policy, a mandated ID
  scheme); "use tabs not spaces" fails this bar
- one requirement related to the decision
- enough connected artifacts (design or roadmap) for `get_related` to have
  something to show

The scenario should ideally be lifted from a real decision in RAC's own
dogfood corpus, so it cannot read as a strawman.

### The code task

A small implementation task, stated in one or two sentences, whose naive
implementation violates the recorded decision. The violation must be the
natural thing an uninformed implementer would do — not a trap.

### The contrast protocol

Two runs of the same agent client on the same task:

1. **Without RAC.** The agent receives the task with no MCP server
   configured. Expected: the naive, decision-violating implementation.
2. **With RAC.** The same agent with `rac mcp` configured. Expected: the
   agent calls `search_artifacts` or `get_artifact`, cites the decision by
   ID, and produces a compliant implementation.

The contrast format is the argument. A feature walkthrough shows what Guide
has; the contrast shows what it changes.

### The script

`examples/guide/demo.md` contains the verbatim prompts for both runs, the
client configuration step, and the expected observable behaviour at each
step, so a stranger can run the demo without interpretation.

### Measurement

The grounded run is scripted and repeatable:

- 10 scripted runs; the grounded agent must cite the correct decision ID in
  at least 8.
- A run counts as a citation only if the response names the decision's
  identifier, not merely its topic.
- The measurement is re-run before release and after any change to tool
  description text (the design contract in `guide-tool-surface`).

### The recording

A screen recording of one contrast pair:

- at most 90 seconds, real time, no edits beyond trimming
- shot order: the task prompt — the ungrounded violation (compressed) — the
  config block — the grounded run with the tool call and citation visible —
  the compliant diff
- the recording is a release asset and exists before the release is
  announced; it headlines the announcement and the README

Claude Code is the headline client (best MCP tool-calling reliability of the
target clients at time of design).

## Constraints

- The demo corpus passes `rac validate` and relationship validation; a demo
  built on invalid artifacts undermines the product it advertises.
- The existing `examples/example_dashboard_v*.md` files and the README diff
  walkthrough that uses them are not disturbed.
- The grounded path uses only the four shipped tools (ADR-030) — no custom
  prompt scaffolding that tells the agent which tool to call; the
  descriptions must do that work.
- The decision artifact satisfies the true-to-life bar (REQ-005).
- The recording shows real tool calls, not mockups.

## Rationale

A scripted, measured demo converts a stochastic behaviour into a testable
claim: 8 of 10 is an acceptance threshold, not an anecdote. Recording in
advance de-risks live failure; scripting de-risks reproduction by strangers;
the true-to-life bar de-risks the strawman reading from a technical
audience.

The with/without structure was chosen over a feature tour because the
product's value is a behavioural delta, and a delta needs a baseline.

## Alternatives

- Feature walkthrough video: shows capability, proves nothing about
  grounding; rejected as the headline (may exist as secondary material).
- Live demo only, no recording: stochastic agent behaviour makes live
  failure likely enough to be reckless at launch.
- CI-based catch (the original Watchkeeper framing): proves enforcement,
  not grounding, and depends on a surface RAC has deferred.

## Accessibility

The recording carries captions or on-screen labels for each phase, the
demo script is fully usable without the video, and transcript text shown in
the recording must be legible at common embed sizes.

## Style Guidance

- The scenario names real technologies and a plausible team context.
- Prompts are short and natural; an over-specified prompt reads as coaching
  the agent.
- The violation diff and the compliant diff are small enough to read in the
  recording without pausing.

## Open Questions

- Which true-to-life decision the scenario records — lifted from RAC's own
  corpus, or authored for a familiar generic stack; to be settled when
  v0.10.2 begins.
- Whether the ungrounded run appears in the script as a full transcript or
  a summarized contrast in `demo.md`.

## Related Requirements

- rac-agent-context-guide

## Related Decisions

- ADR-030
- ADR-034

## Related Roadmaps

- v0.10.2-guide-grounding-demo
