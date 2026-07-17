---
schema_version: 1
id: RAC-KV2GTA8V6QGK
type: design
---
# Agent Usage Read-Back

## Context

A recurring product idea: a command that runs locally, shows a user their
own agent-decision usage, and offers an explicit, one-click "share these
aggregates with the maintainer" where the user sees exactly what is sent.
The framing flips telemetry from extraction into a feature — the user gets
a reason to return and look at their own usage, and the maintainer gets
principled, opt-in aggregates. The umbrella for this work is the considered
roadmap `agent-usage-readback`; this design records the implementation
approach so it lives in the corpus rather than in a tool's scratch space.

Most of the machinery already ships, and the honest starting point is to
map it. This is **not** `rac stats`, which summarizes a corpus of artifacts
and has nothing to do with agent usage:

- `rac mcp-stats` reads the local Guide telemetry log
  (`$XDG_STATE_HOME/rac/guide-telemetry.jsonl`) and reports per-tool call
  counts, errors, truncations, average latency, sessions, and time range
  (ADR-040). Code: `src/rac/mcp/telemetry.py` — `summarize`,
  `TelemetrySummary`, `ToolUsage`; renderers in `src/rac/output/human.py`
  and `src/rac/output/json.py`.
- `rac mcp-stats --share` builds a prefilled GitHub issue URL carrying the
  exact JSON aggregate, with the local path stripped (a home path can embed
  a username), which the user reviews in their own browser and submits.
  RAC transmits nothing (`share_url` in `telemetry.py`). This already meets
  the "one-click, see exactly what is sent" bar.
- `rac telemetry on|off|status` plus the consent record
  (`$XDG_CONFIG_HOME/rac/telemetry.json`, `src/rac/consent.py`) and the
  anonymous daily ping (`src/rac/mcp/ping.py`) model consented sharing
  (ADR-041).

So the unbuilt part is two-fold: the product framing (a utilitarian "Guide
Telemetry" diagnostic is not yet something a user wants to revisit), and
the breadth of "agent usage" — today only the four Guide MCP tools, and
only while `rac mcp --telemetry` runs.

## User Need

Two audiences, one artifact:

- The operator (often an agent's human) wants to see, locally and quickly,
  what their agents have been doing — recent activity over time, not a flat
  lifetime counter — in a form worth opening more than once.
- The maintainer wants principled, opt-in aggregates to decide which
  surfaces earn their place, without asking anyone to extend trust RAC has
  not earned.

The need is real but unproven; this design is gated on user-research signal
that people actually want to see their own usage (see the roadmap). It must
not displace nearer-term committed work.

## Design

Three initiatives, separable so the cheap, no-decision work does not wait on
the heavier instrumentation work.

### Layer A — read-back as a feature (no schema change)

Enhance the existing `rac mcp-stats` read-back into a user-facing summary,
entirely within ADR-040's pinned, content-free event schema. Every addition
is derived from already-recorded fields (`ts`, `session`, `tool`,
`outcome`, `duration_ms`, `truncated`):

- a recent-activity trend (per-day counts over the last N days from `ts`);
- a per-session view (calls and errors grouped by the recorded `session`);
- reframed narrative copy that leads with the human value and keeps counts
  as support.

`--share` is unchanged. The read-back/export payload may grow additively —
it is the export, distinct from the pinned *event* schema — so goldens
under `tests/golden/mcp_stats_*.txt` regenerate. No new recorded fields and
no new decision. Touch points: aggregation in `src/rac/mcp/telemetry.py`
(`summarize`/`TelemetrySummary`); renderers in `src/rac/output/human.py`
and `src/rac/output/json.py`.

### Layer B — widen the recorded source to all CLI usage

Record one content-free event per completed `rac` command — command name,
outcome, duration; never argv, paths, or content — into a separate local
log (`$XDG_STATE_HOME/rac/rac-usage.jsonl`, kept separate so ADR-040's
pinned log and schema stay untouched), with the same never-raise,
write-only posture as `TelemetryRecorder`. Opt-in is the existing
`rac telemetry` consent record, not a per-invocation flag, because the
Guide's visible `--telemetry` flag cannot sensibly gate one-shot commands
and ADR-040 rejected silent config/env enablement. This is a new
instrumentation surface and a new opt-in anchor, so it carries its own
decision, ADR-046. Touch points: a recorder hook around dispatch in
`src/rac/cli.py` (`main` calling `args.func(args)`); consent gating via
`src/rac/consent.py`; aggregation alongside `summarize`.

### Layer C — unified read-back surface

Since the data is no longer Guide-only, present one user-facing read-back
spanning both the CLI-usage log and the Guide log, keeping `rac mcp-stats`
working for back-compat. This realizes the instinct that the honest name is
usage, not stats. Sharing reuses the existing string-only, user-submits
flow.

## Constraints

- Content-free (ADR-040, ADR-046): no argv, artifact IDs, query strings,
  paths, or repository content in any recorded event; the absent fields are
  asserted by test, not comment.
- Determinism (ADR-032): recording is write-only observability; command and
  tool output, and exit codes, stay a pure function of input, proven
  byte-for-byte with and without a recorder attached.
- No network in RAC (ADR-035, ADR-040): sharing is URL string-formatting;
  the user's browser transmits.
- Opt-in, default-off: recording is off until explicit, inspectable consent
  (`rac telemetry status`).
- Versioning: this is a new thematic surface (new decision, new/renamed
  read-back command, new instrumentation), so it belongs in a new minor
  series after watchkeeper; the maintainer names the theme and version when
  it is scheduled and graduates out of `future/`.

## Rationale

Layer A is separated from Layer B precisely because it needs no decision and
no schema change: it is the lowest-risk way to test whether a self-usage
view earns return visits before paying for broader instrumentation. Layer B
is justified only if the Guide-MCP-only signal proves too narrow to be
interesting. Anchoring CLI opt-in to the existing consent record, rather
than inventing a third mechanism, keeps the user reasoning about "share my
usage" once; the coupling cost is recorded in ADR-046.

## Alternatives

- Build a brand-new `rac stats`-style command: rejected — `rac stats` is
  taken (corpus summary) and most of the read-back already exists in
  `rac mcp-stats`; the work is enhancement, not greenfield.
- Per-invocation `--telemetry` flag for CLI usage: rejected — nobody types
  it on every command, so it records nothing; see ADR-046.
- A silent env var or config flag for CLI telemetry: rejected — reintroduces
  the "persistent invisible state" ADR-040 refused.
- Recording richer signal (which artifacts/queries agents reach for):
  out of scope — collides with ADR-040's content-free pin and would require
  superseding it.

## Accessibility

The read-back is read by people in a terminal: lead with a plain-language
sentence before any table, keep counts legible without colour (colour is
already TTY-gated in `src/rac/output/human.py`), and emit the same
information in `--json` so non-visual and programmatic consumers are not
second-class. The share payload stays plain JSON the user can read in full
before submitting.

## Style Guidance

- Human output leads with the human value ("your agents made N calls across
  M sessions") and keeps counts as supporting detail.
- Vocabulary matches what users see (`command`, `session`, `tool`), never
  internal module names.
- JSON output carries `schema_version` and grows only additively (ADR-007).

## Open Questions

- The retention window N for the recent-activity trend (Layer A).
- Whether to split consent so a user can take the remote ping without local
  CLI recording, or keep one consent for both (ADR-046 keeps one for now).
- The final name and version of the unified read-back command, settled when
  the series is scheduled.

## Related Requirements

- rac-trust-transparency
- rac-agent-context-guide

## Related Decisions

- ADR-032
- ADR-035
- ADR-040
- ADR-041
- ADR-046

## Related Roadmaps

- v0.24.0-visibility
