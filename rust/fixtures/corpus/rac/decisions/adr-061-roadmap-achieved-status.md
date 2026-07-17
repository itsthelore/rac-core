---
schema_version: 1
id: RAC-KV5112MVD0AM
type: decision
tags: [roadmap, lifecycle, knowledge-model]
---
# ADR-061: Roadmaps Carry an "Achieved" Terminal Lifecycle Status

## Context

A roadmap's `## Status` is a *knowledge-currency* lifecycle (ADR-051): is this
thinking the current intent, or has it moved on? The original enum —
`Planned` (current intent), `Superseded` (replaced by newer thinking),
`Abandoned` (dropped) — has no terminal state for "this intent was delivered."

The practical consequence is wrong: a roadmap whose work has shipped is stuck
at `Planned`, which is future-tense and false once delivered. It cannot move to
`Superseded` (its thinking was not replaced) or `Abandoned` (it was not
dropped). Completed series therefore read as still-planned.

ADR-017 ("RAC manages knowledge, not work") deliberately keeps delivery
tracking, scheduling, and workflow states out of RAC, so adding a "shipped"
concept needs an explicit boundary rather than a silent reversal.

## Decision

Add `Achieved` to the roadmap status enum as a **live terminal** state: the
roadmap's intent has been realized and the item is now a historical record.

`Achieved` is a knowledge-lifecycle marker, not work tracking. It records *what
the knowledge is* (a realized intent), not *how work progressed* — there is no
assignee, no progress, no scheduling, and it is set by a human at release, not
auto-flipped by a merge. This refines ADR-017's boundary: a terminal
"realized" lifecycle state is knowledge currency (the same category as
`Superseded`/`Abandoned`, which already coexist with ADR-017); work-progress
tracking remains excluded.

`Achieved` is deliberately **not** a retired status (ADR-051): a delivered
roadmap is still valid knowledge to reference, so links to it are legal and are
not flagged as pointing at a retired target. The live state stays `Planned`;
no `Active`/in-progress state is introduced.

## Consequences

Completed roadmap items can read truthfully (`Achieved`) instead of being
stranded at `Planned`. The status vocabulary now spans the full knowledge
lifecycle: `Planned` → `Achieved` (delivered) or `Superseded`/`Abandoned`
(retired). The change is additive — existing `Planned` items are unaffected,
and the `invalid-roadmap-status` validation message picks up the new value
automatically.

Trade-off: marking an item `Achieved` is a manual editorial step at release
time. RAC does not (and per ADR-017 will not) flip it automatically on merge;
the delivery event itself stays in Git history.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

- **Keep completed items at `Planned`; read delivery from Git.** The status
  quo. Rejected: it leaves `Planned` reading as false on shipped work, which is
  the problem being solved.
- **Reuse `Superseded` for delivered items.** Rejected: `Superseded` means the
  thinking was replaced by newer thinking, which is not what delivery means;
  it would also (incorrectly) mark the item retired, breaking inbound links.
- **Add a full work-state machine (in-progress, in-review, done).** Rejected:
  that is exactly the work tracking ADR-017 excludes. A single terminal
  knowledge state is the minimal, in-scope change.
- **Auto-set `Achieved` from a merge hook.** Rejected: merge-triggered status
  automation is workflow tooling; the status is authored knowledge, set at
  release by a human.

## Related Decisions

- adr-017
- adr-051

## Related Roadmaps

- v0.19.0-roadmap-achieved-status
