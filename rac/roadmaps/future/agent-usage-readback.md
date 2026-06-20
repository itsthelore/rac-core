---
schema_version: 1
id: RAC-KV2E9H9QQ96F
type: roadmap
---
# RAC — Agent Usage Read-Back (Future)

## Status

Superseded

Superseded by `v0.24.0-visibility`, which schedules this intent into the v0.24.0
release (WS-E — Agent usage read-back). Retained as the originating record.

## Context

A recurring product idea: a command that runs locally, shows a user their
own agent-decision usage, and offers an explicit, one-click "share these
aggregates with the maintainer" where the user sees exactly what is sent.
The framing is deliberate — it flips telemetry from extraction into a
feature. The user gets a reason to come back and look at their own usage;
the maintainer gets principled, opt-in aggregates.

Most of the machinery already ships. `rac mcp-stats` reads the local Guide
telemetry log and reports per-tool call counts, errors, truncations,
average latency, sessions, and time range (ADR-040). `rac mcp-stats
--share` builds a prefilled GitHub issue URL containing the exact JSON
aggregate, with the local path stripped, that the user reviews and submits
in their own browser — RAC transmits nothing. Consent for anonymous remote
pings is already modelled (`rac telemetry`, ADR-041). This is not
`rac stats`, which summarizes a corpus of artifacts and has nothing to do
with agent usage.

So the genuinely unbuilt part is two-fold: the product framing (a
utilitarian "Guide Telemetry" diagnostic is not yet something a user wants
to revisit), and the breadth of what counts as "agent usage" (today only
the four Guide MCP tools, and only while `rac mcp --telemetry` runs).

This item is recorded as considered, not scheduled. It is a real build,
gated on user-research signal that people actually want to see their own
usage; it must not become a substitute for nearer-term committed work.
When scheduled, this graduates out of `future/` into a versioned series
folder and grows an implementation contract.

## Outcomes

- A user can inspect their own agent usage locally in a form worth
  returning to — recent activity over time, not just a flat lifetime
  count — turning telemetry into a feature rather than extraction.
- "Agent usage" spans the whole `rac` CLI, not only the four Guide MCP
  tools, so the picture reflects what agents and users actually do.
- Sharing aggregates with the maintainer stays a single, explicit,
  fully-inspectable act: the user sees the exact payload before their own
  browser submits it; RAC never transmits.
- The trust posture is preserved end to end: opt-in, default-off,
  local-first, content-free.

## Initiatives

### Initiative 1 — Read-back as a feature (no schema change)

Enhance the existing `rac mcp-stats` read-back into a user-facing summary,
working entirely within ADR-040's pinned, content-free event schema. Every
addition is derived from already-recorded fields (`ts`, `session`, `tool`,
`outcome`, `duration_ms`, `truncated`): a recent-activity trend
(per-day counts over the last N days), a per-session view, and reframed
narrative copy that leads with the human value and keeps counts as
support. The `--share` flow is unchanged — it already meets the
one-click, see-exactly-what-is-sent bar. The read-back/export payload may
grow additively (it is the export, distinct from the pinned event schema);
goldens regenerate. No new recorded fields, no new ADR.

### Initiative 2 — Widen the recorded source to all CLI usage

Record one content-free event per completed `rac` command (command name,
outcome, duration — never argv, paths, or content) into a separate local
log, gated by the existing `rac telemetry` consent rather than a
per-invocation flag, with the same never-raise, write-only posture as the
Guide recorder. This is a new instrumentation surface and a new opt-in
anchor, so it carries its own decision, ADR-046 — chiefly because the
Guide's visible per-invocation `--telemetry` flag cannot sensibly gate
one-shot commands, and ADR-040 rejected silent config/env enablement.

### Initiative 3 — Unified read-back surface

Since the data is no longer Guide-only, present a single user-facing
read-back spanning both the CLI-usage log and the Guide log, keeping
`rac mcp-stats` working for back-compat. This realizes the instinct that
the honest name is usage, not stats. Sharing reuses the existing
string-only, user-submits flow.

## Constraints

- Content-free (ADR-040, ADR-046): no argv, artifact IDs, query strings,
  paths, or repository content in any recorded event; the absent fields
  are tests, not comments.
- Determinism (ADR-032): recording is write-only observability; command
  and tool output, and exit codes, stay a pure function of input, proven
  byte-for-byte with and without a recorder.
- No network in RAC (ADR-035, ADR-040): sharing is URL string-formatting;
  the user's browser transmits.
- Opt-in, default-off: recording is off until explicit, inspectable
  consent (`rac telemetry status`).

## Non-Goals

- Recording any content — artifact IDs, queries, flag values, or paths.
- Automatic, default-on, or remote-by-default telemetry.
- A hosted dashboard or any RAC-side transmission; sharing stays
  user-submitted.
- Changing ADR-040's pinned Guide event schema or its log.

## Success Measures

- The local read-back is compelling enough that opted-in users open it
  more than once — measured, fittingly, by the read-back command's own
  usage once Initiative 2 lands.
- With consent recorded, any `rac` command yields a content-free usage
  event; with consent absent, no usage file is touched.
- Output and exit codes are identical with and without a recorder.
- At least one early-user report arrives through the share flow and
  informs a CLI surface decision.

## Assumptions

- User-research calls confirm demand for a self-usage view before this is
  scheduled; without that signal it stays considered, not built.
- The Guide-MCP-only signal proves too narrow to be interesting, which is
  what justifies Initiative 2's broader instrumentation.
- Tying CLI recording to the existing consent record is acceptable; if
  users want split consent, that is a later decision.

## Risks

- "Build the principled telemetry feature" becomes a dodge for committed
  near-term work. Mitigation: this item is explicitly gated and recorded
  as considered, not scheduled.
- Coupling CLI recording to the ADR-041 consent record surprises a user
  who wanted only the remote ping. Mitigation: `rac telemetry status`
  states plainly what consent enables (see ADR-046).

## Related Decisions

- ADR-032
- ADR-035
- ADR-040
- ADR-041
- ADR-046

## Related Requirements

- rac-trust-transparency
- rac-agent-context-guide

## Related Designs

- agent-usage-surface

## Related Roadmaps

- v0.24.0-visibility
