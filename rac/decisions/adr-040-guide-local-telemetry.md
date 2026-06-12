---
schema_version: 1
id: RAC-KTY25D945HYK
type: decision
---
# ADR-040: Guide Local Telemetry

## Status

Accepted

## Category

Product

## Context

Nothing today answers whether the Guide is actually used, or which of
its four tools earn their place. Search-quality work (v0.10.3), tool
description revisions, and future surface decisions all want usage
evidence; without it they are guesses.

The obvious industry answer — automatic remote telemetry — collides
with recorded positions. ADR-035 forbids a mandatory RAC cloud
dependency, and the trust-transparency requirement names hosted
infrastructure a non-goal: RAC's credibility rests on being boring,
deterministic, and inspectable. A tool that quietly phones home
forfeits exactly the trust the Guide asks an agent's operator to
extend. ADR-032 adds a technical constraint: tool output is a pure
function of repository bytes and tool input, so observability must
never feed back into a response.

The need is real and the constraints are recorded. The decision is the
shape of telemetry that satisfies both.

## Decision

Guide telemetry is opt-in, default-off, local-only, and content-free.

- Enablement is an explicit `--telemetry` flag on `rac mcp` — visible
  in the client's server configuration, never persistent, never implied
  by a config file or environment variable. When enabled, the server
  announces on stderr what is recorded and where.
- Each tool call appends one JSON line to
  `$XDG_STATE_HOME/rac/guide-telemetry.jsonl` (default
  `~/.local/state/rac/guide-telemetry.jsonl`). The event schema is
  pinned: `schema_version`, `ts` (ISO 8601 UTC), `session` (random
  per-process hex), `tool`, `outcome` (`ok` | `error` | `exception`),
  `error` (structured error code, only when outcome is `error`),
  `duration_ms`, `truncated`. Tool arguments, artifact IDs, query
  strings, paths, and repository content are never recorded. Adding a
  field is a recorded decision, not a patch.
- Recording is write-only observability outside the request/response
  contract: the payload returns unchanged, the log is never an input to
  a response, and a recorder that cannot write disables itself silently
  — telemetry failure never breaks a tool call.
- Read-back is local: `rac mcp-stats` summarizes the log; its `--json`
  output is the export. Sharing is a deliberate act: `--share` prints a
  prefilled GitHub issue URL for the repository's usage-report issue
  form, and the user reviews and submits it in their own browser.
- RAC contains no network code. Building a URL is string formatting;
  transmission belongs to the user.

## Consequences

### Positive

- Usage evidence becomes available without compromising the recorded
  trust posture; future surface decisions can cite data.
- Everything is inspectable: the log is plain JSONL on the user's disk,
  the export is the same bytes the user reads, and the share payload is
  reviewed before submission.
- The determinism contract survives intact and remains testable
  byte-for-byte with a recorder attached.

### Negative

- Opt-in means sparse, self-selected data; adoption questions get a
  floor, not a census.
- Reports arrive as public GitHub issues, readable by anyone — counts
  and timestamps only, but public.
- A second generation of telemetry wants (latency percentiles, query
  shapes) is foreclosed until a new decision revisits the schema.

### Risks

- Scope creep toward recording content under diagnostic pressure.
  Mitigation: the schema is pinned here and in the contract battery;
  the named absent fields are a test, not a comment.
- A future change accidentally routes the log into a response.
  Mitigation: payload-stability tests compare responses byte-for-byte
  with and without a recorder.

## Alternatives Considered

### Automatic remote telemetry

Send events to a hosted endpoint by default, with opt-out.

#### Advantages

- Real adoption data across the install base.

#### Disadvantages

- Directly contradicts ADR-035 and the trust-transparency non-goal;
  requires hosted infrastructure, a privacy policy, and the very
  category of trust conversation RAC exists to avoid.

### Environment-variable or config-file enablement

Enable via `RAC_TELEMETRY=1` or a user config file.

#### Advantages

- Survives across sessions without editing client server args.

#### Disadvantages

- Persistent invisible state: telemetry silently on long after the
  user forgot setting it. The flag keeps enablement where the server
  is configured and visible every time.

### No telemetry at all

Keep guessing from issues and conversations.

#### Advantages

- Zero code, zero trust surface.

#### Disadvantages

- The Guide's product questions stay unanswerable; investment in
  search quality and descriptions proceeds on anecdote.

Opt-in local recording with user-driven sharing is selected.

## Relationship to Other Decisions

- ADR-032 (stateless reads): telemetry is write-only observability
  outside the request/response contract; tool output remains a pure
  function of repository bytes and tool input.
- ADR-035 (user-managed credentials, no RAC cloud): no hosted
  endpoint, no transmission by RAC.
- ADR-031 (in-process Core consumption): the recorder lives in the
  server layer; Core and services stay telemetry-unaware.
- ADR-034 (structured errors): outcome classification reads the
  structured error code the tools already return.
- ADR-013 (Git as the state store): the telemetry log is user-machine
  state, not repository state; it never enters the corpus.

## Success Measures

- Driving the four tools with `--telemetry` yields events containing
  no arguments or content; without the flag, no file is touched.
- Existing Guide goldens pass unchanged in the implementing change.
- At least one early-user report arrives through the share flow and is
  useful for a surface decision.

## Review Date

Review when the first real diagnostic need exceeds the pinned schema,
or one quarter after release if no user has opted in.

## Related Requirements

- rac-agent-context-guide
- rac-trust-transparency

## Related Roadmaps

- v0.10.4-guide-telemetry
