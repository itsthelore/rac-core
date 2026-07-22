---
schema_version: 1
id: RAC-KV2E9HYHVV8G
type: decision
---
# ADR-046: CLI Usage Telemetry

## Status

Accepted

## Category

Product

## Context

ADR-040 gave the Guide a way to answer one product question — is it used,
and which of its four tools matter — through opt-in, default-off,
local-only, content-free telemetry, read back with `rac mcp-stats` and
shared by a user-submitted GitHub issue. That decision is deliberately
narrow: it records only Guide MCP tool calls, and only while a long-running
`rac mcp` server runs with an explicit `--telemetry` flag.

A second question is now live: which `rac` CLI commands do users (and the
agents driving them) actually reach for? `validate`, `review`,
`watchkeeper`, `relationships`, `export`, and the rest each carry
maintenance cost and surface-design decisions, and today those decisions
proceed on anecdote. The agent-usage read-back feature
(`rac/roadmaps/future/agent-usage-readback.md`) wants to widen "your agent
usage" beyond the four Guide tools to the whole CLI — but only if the data
can be gathered without spending the trust the existing telemetry posture
protects.

The recorded constraints still bind. ADR-035 forbids a mandatory RAC cloud
dependency and the trust-transparency requirement names hosted
infrastructure a non-goal: RAC's credibility rests on being boring,
deterministic, and inspectable. ADR-032 requires that observability never
feed back into a command's output. ADR-040 already pins a content-free
event shape and, importantly, *rejected* environment-variable and
config-file enablement for the Guide because they are "persistent invisible
state" — telemetry silently on long after the user forgot setting it.

That rejection is the crux. The Guide keeps enablement visible because the
`--telemetry` flag sits in the client's server configuration, read every
time the server starts. One-shot CLI commands have no such persistent
visible flag: passing `--telemetry` on every `rac validate` is absurd, and
a flag that must be remembered every invocation records nothing in
practice. CLI usage telemetry therefore needs a different opt-in anchor,
and reusing a silent env var or config file is exactly what ADR-040
refused. This decision exists to record how CLI usage is recorded without
reintroducing invisible state.

## Decision

CLI usage telemetry is opt-in, default-off, local-only, and content-free,
gated by the existing recorded consent rather than a per-invocation flag.

- Enablement is the consent record already defined by ADR-041
  (`$XDG_CONFIG_HOME/rac/telemetry.json`, set at `rac init`, managed by
  `rac telemetry on|off`). When — and only when — consent is recorded,
  each completed CLI command appends one event to a separate local log,
  `$XDG_STATE_HOME/rac/rac-usage.jsonl`. This is not the silent state
  ADR-040 rejected: consent is an explicit act, always inspectable with
  `rac telemetry status`, and revocable with `rac telemetry off`. The
  log path is separate from ADR-040's `guide-telemetry.jsonl` so that
  decision's pinned schema and log are untouched.
- The event schema is pinned: `schema_version`, `ts` (ISO 8601 UTC),
  `session` (random per-process hex), `command` (the subcommand name
  only, e.g. `validate`), `outcome` (`ok` | `error` | `exception`),
  `duration_ms`. Argv, flag values, positional arguments, file paths,
  artifact IDs, and repository content are never recorded. The named
  absent fields are a test, not a comment. Adding a field is a recorded
  decision, not a patch.
- Recording is write-only observability outside the command's output
  (ADR-032): the recorder runs after dispatch, the log is never an input
  to any command, exit codes are unchanged, and a recorder that cannot
  write disables itself silently — telemetry failure never breaks a
  command.
- Read-back is local and unified: a single command summarizes both the
  Guide log and the CLI-usage log; `rac mcp-stats` continues to read the
  Guide log for back-compat. Sharing stays a deliberate act — a prefilled
  GitHub issue URL the user reviews and submits in their own browser, the
  local path stripped from the payload.
- RAC contains no network code for this surface. Building a URL is string
  formatting; transmission belongs to the user (ADR-035).

## Consequences

### Positive

- CLI surface decisions gain usage evidence under the same trust posture
  as the Guide: opt-in, local, content-free, user-submitted.
- One consent question governs both remote ping (ADR-041) and local CLI
  recording, so a user reasons about "share my usage" once rather than
  per surface.
- Everything stays inspectable: the log is plain JSONL on the user's
  disk, the export is the same bytes the user reads, and the share
  payload is reviewed before submission.
- The determinism contract survives intact and stays testable
  byte-for-byte with a recorder attached.

### Negative

- Opt-in means sparse, self-selected data; adoption questions get a
  floor, not a census.
- Tying local CLI recording to the ADR-041 consent record couples two
  things a user might want to separate: consenting to an anonymous
  remote ping now also enables local CLI recording. Mitigated by the
  read-back being local and the share flow staying explicit; revisited
  here rather than left implicit.
- A second generation of telemetry wants (per-flag usage, argument
  shapes) is foreclosed until a new decision revisits the schema.

### Risks

- Scope creep toward recording argv or paths under diagnostic pressure.
  Mitigation: the schema is pinned here and in the contract battery; the
  named absent fields are asserted by test.
- A future change accidentally routes the log into a command's output or
  makes recording affect an exit code. Mitigation: output- and
  exit-code-stability tests compare runs with and without a recorder.
- Consent coupling surprises a user who wanted the remote ping but not
  local recording. Mitigation: `rac telemetry status` states plainly
  what consent enables; revisit if users ask for split consent.

## Alternatives Considered

### Per-invocation `--telemetry` flag (the Guide model)

Mirror ADR-040 exactly: record only when `rac <command> --telemetry` is
passed.

#### Advantages

- Identical, already-reasoned-about posture; enablement visible in the
  command line every time.

#### Disadvantages

- Nobody types `--telemetry` on every command, so the flag records
  effectively nothing. The Guide flag works because it lives in
  persistent server configuration read on every start; a one-shot
  command has no equivalent durable, visible home.

### Silent environment variable or config flag dedicated to CLI telemetry

Add `RAC_USAGE_TELEMETRY=1` or a new config key separate from consent.

#### Advantages

- Decouples CLI recording from the remote-ping consent.

#### Disadvantages

- Reintroduces precisely the "persistent invisible state" ADR-040
  rejected: telemetry silently on, forgotten, with no obvious place to
  see it. A dedicated `rac telemetry` subcommand could surface it, but
  that is the consent record this decision already reuses.

### No CLI telemetry at all

Keep CLI surface decisions on anecdote; leave telemetry Guide-only.

#### Advantages

- Zero new code, zero new trust surface.

#### Disadvantages

- The agent-usage read-back stays narrow (four Guide tools), and the
  product question "which commands earn their place" stays unanswerable.

Consent-gated, content-free CLI recording into a separate local log is
selected.

## Relationship to Other Decisions

- ADR-040 (Guide local telemetry): this decision extends the telemetry
  posture to the CLI; it does not change ADR-040's log or pinned event
  schema, and it reconciles ADR-040's rejection of invisible enablement
  by anchoring opt-in to explicit, inspectable consent.
- ADR-041 (anonymous usage ping): reuses that decision's consent record
  as the enablement anchor; no new consent mechanism is introduced.
- ADR-032 (stateless reads): recording is write-only observability; a
  command's output and exit code stay a pure function of input.
- ADR-035 (user-managed credentials, no RAC cloud): no hosted endpoint,
  no transmission by RAC; sharing is user-submitted.

## Success Measures

- Driving any `rac` command with consent recorded yields events
  containing a command name but no argv, paths, or content; with consent
  absent, no usage file is touched.
- A command's output and exit code are byte-for-byte and value-for-value
  identical with and without a recorder attached.
- The unified read-back summarizes both logs, and at least one early-user
  report arrives through the share flow and informs a surface decision.

## Review Date

Review when the first real diagnostic need exceeds the pinned schema, or
one quarter after release if no user has opted in.

## Related Requirements

- rac-trust-transparency
- rac-agent-context-guide

## Related Roadmaps

- v0.24.0-visibility

## Related Designs

- agent-usage-surface
