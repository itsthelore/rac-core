---
schema_version: 1
id: RAC-KW6HY8W1CBK6
type: decision
tags: [process, roadmap, workflow, github]
---
# ADR-093: Roadmap Intent Lives in the Corpus; Execution Is Tracked in GitHub Issues

## Context

RAC models roadmaps as first-class *knowledge* artifacts: the durable record of
what product capability is intended and why, with a lifecycle status (Planned,
Achieved, Superseded, Abandoned — ADR-061). ADR-017 draws the governing line —
**RAC manages knowledge, not work**: the corpus records decisions and intent, not
tasks, assignment, sprints, or who-is-doing-what-now.

Two recent shifts make the *execution* side of roadmaps awkward:

- **CalVer decoupled the numbers (ADR-076).** Roadmap `vX.Y.Z` labels are internal
  scope-fences, no longer release identifiers. In practice recent series run in
  parallel (v0.28/29/30/31), so the numeric order implies a sequence the team does
  not actually follow. The corpus has no honest place to record execution order or
  task progress — and by ADR-017 it should not.
- **External ticketing now exists (ADR-087).** A `## Related Tickets` relationship
  section links an artifact to external tickets, with the provider chosen per repo
  (`rac init --ticketing <provider>`); `rac validate` format-lints the entries
  offline and the edge surfaces in the graph export marked external. The engine
  never fetches ticket state (ADR-002, ADR-032) — it is a format-linted reference
  only.

What is missing is an explicit, recorded workflow for *how* outstanding roadmap
work is tracked and ordered without dragging work-tracking into the corpus. This
ADR settles that, building on ADR-017 (the principle), ADR-087 (the mechanism),
and ADR-061 (the roadmap lifecycle).

## Decision

Roadmap **intent** lives in the corpus; roadmap **execution** is tracked in GitHub
issues; the two are linked by `## Related Tickets`.

- **The roadmap artifact is the intent of record.** It states the outcomes,
  initiatives, and justification — the durable "what and why." Its `## Status`
  (ADR-061) reflects the *intent* lifecycle (is this intended / delivered /
  dropped), **not** task progress.
- **Execution is work, so it lives in the work-tracker (ADR-017).** Ordering,
  prioritisation, assignment, and the granular state of the *doing* live in GitHub
  issues and a project board — never as task state in the corpus.
- **The bridge is `## Related Tickets` (ADR-087).** A live roadmap item links to
  the GitHub issue(s) executing it. `rac-core` sets `ticketing.provider: github`
  in `.rac/config.yaml`, so `rac validate` format-lints those references
  (`owner/repo#123` or a URL) offline.
- **The engine never imports issue state.** Issue status, comments, and ordering
  are read in GitHub, not by `rac`. `rac validate` / `rac gate` stay offline and
  deterministic (ADR-002, ADR-032); the edge is a reference, not a sync.
- **Ordering is the board's job, not the roadmap number's.** Because the project
  board carries execution order, the `vX.Y.Z` scope-fence label no longer needs to
  imply sequence; it remains a stable identifier (ADR-094 subsequently settled the
  open question — the numeric scheme is retired for live roadmaps in favour of
  codenames; shipped/historical series keep their versioned names).

This operationalises ADR-017 for roadmaps: the corpus answers "what capability,
and why"; GitHub answers "what's being worked, by whom, in what order, now."

## Consequences

### Positive

- Order-independent execution (a board drives sequence) **without** renaming or
  restructuring roadmap artifacts — the corpus stays stable while the work moves.
- A clean intent/execution separation: the durable product story stays in the
  typed, validated corpus; transient task state stays in the tool built for it.
- ADR-017 is honoured concretely — no task, sprint, or assignment data enters the
  corpus — while roadmap items gain a live execution link.

### Negative

- Two places to look: the corpus for intent, GitHub for execution. Mitigation: the
  `## Related Tickets` edge makes the jump one click, and the graph export marks it.
- A roadmap item and its issue can drift (issue closed, roadmap still Planned).
  Mitigation: the roadmap `## Status` tracks *intent* coarsely (flip to Achieved
  when the capability ships); fine-grained state is the issue's job, by design.

### Risks

- Creep toward syncing issue state into the corpus. Mitigation: ADR-002/032 forbid
  it; `## Related Tickets` is a format-linted reference only (ADR-087).
- Roadmap statuses left stale because "the issue has it." Mitigation: intent-level
  status is light and owned by the roadmap; only the *execution* detail moves out.

## Status

Accepted

## Category

Process

## Alternatives Considered

### Track roadmap execution in the corpus

Add task/progress/assignment fields to roadmap artifacts.

Rejected: this is work-tracking, which ADR-017 keeps out of RAC; it would turn the
knowledge store into a project tool and pull transient state into a durable record.

### Move roadmaps wholesale into GitHub issues

Replace roadmap artifacts with issues/epics.

Rejected: it dumps *knowledge* (durable intent, the typed relationship graph,
offline validation, the export surfaces) into a *work-tracker*, losing exactly
what ADR-017 and the roadmap artifact model exist to preserve. Intent is not a
transient ticket.

### Status quo — `vX.Y.Z` carries execution order

Keep using the roadmap numbers to sequence work.

Rejected: CalVer (ADR-076) decoupled the numbers from releases, and parallel
series show the linear sequence is fiction; there is still no honest home for
assignment or task state.

## Related Decisions

- adr-017
- adr-087
- adr-061
- adr-076
- adr-002
- adr-032
