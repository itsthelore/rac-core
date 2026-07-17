---
schema_version: 1
id: RAC-KTYPAB0HWFJD
type: decision
---
# ADR-041: Anonymous Usage Ping

## Status

Accepted

## Category

Product

## Context

ADR-040 gave Guide local, opt-in, content-free telemetry, with sharing
as a hand-submitted GitHub issue. That channel works while the
maintainer can talk to every user; past roughly thirty teams it cannot
answer the retention question — do installs come back — and no amount
of local logging will.

ADR-040's decision includes the clause "RAC contains no network code.
Building a URL is string formatting; transmission belongs to the
user." The trust-transparency requirement names hosted infrastructure
a non-goal. RAC's ICP are exactly the engineers who read what a CLI
phones home; a tool that quietly uploads usage forfeits its trust
posture on launch day. Any remote signal has to survive that audience
reading the source.

The decision is the shape of remote telemetry that earns it: opt-in
twice over, minimal, anonymous, and one readable module wide.

## Decision

RAC sends, with explicit recorded consent and never otherwise, at most
one anonymous daily ping to PostHog.

- Consent is its own explicit act, separate from the local
  `--telemetry` flag: an honest one-line question at `rac init`
  ("Share anonymous usage to help shape Lore? [y/N]") — TTY-gated,
  default No, asked at most once per machine because either answer is
  persisted — and a `rac telemetry on|off|status` command to flip or
  inspect it at any time. This is deliberately the CLI's first
  interactive prompt: one honest question, never in CI, never twice.
- The payload is pinned in full; adding a field is a new recorded
  decision: `api_key` (public project write key), `event`
  (`lore-daily-ping`), `timestamp` (ISO 8601 UTC), and `properties`
  carrying `distinct_id` (install id), `$process_person_profile`
  (`false` — PostHog creates no person profile, so the event stays
  anonymous on the sink side too), `schema_version` (`"1"`),
  `rac_version`, and `active_repos` (int). The shape follows PostHog's
  documented capture contract. Never repository contents, paths,
  artifact text, queries, tool arguments, or anything identifying.
- The install id is random (`secrets.token_hex(16)`), minted at
  opt-in and preserved across off-and-on toggles — random beats a
  salted hash of machine attributes because it derives from nothing.
- Active repos are counted locally: a salted digest of each served
  repository root, with a per-install salt that never leaves the
  machine, pruned to a thirty-day window. Only the count transmits.
- The sink is PostHog Cloud (EU region) via one plain stdlib HTTP
  POST — no SDK dependency. RAC itself still hosts no infrastructure; the
  third-party-processor trade-off is accepted and recorded here, and
  the sink is swappable behind one constant.
- An empty `POSTHOG_API_KEY` constant is a kill switch: nothing sends
  even with consent, and `rac telemetry status` says so.
- Fire-and-forget posture: a daemon thread in the `rac mcp` server,
  one attempt per 24 hours tracked by a local marker, a three-second
  socket timeout, every exception swallowed, no retries, no queueing.
  The ping never blocks, delays, or alters a tool call.
- The network surface of RAC is one module: only the ping module may
  import `urllib.request`, enforced by the isolation battery.

## Consequences

### Positive

- The retention curve becomes measurable past the scale where every
  user can be reached individually.
- The trust story survives scrutiny: opt-in twice over, a pinned
  content-free payload printed verbatim in the docs, and a network
  surface one readable file wide.
- The empty-key kill switch makes every build inert until the
  PostHog project exists, decoupling code review from data flow.

### Negative

- ADR-040's flat "no network code" claim no longer holds; every
  honesty surface that quoted it must be rewritten, and the weaker
  claim ("one module, consent-gated") takes more words to defend.
- PostHog is a third-party data processor; "we send to PostHog" is a
  line in the privacy story that a self-hosted collector would avoid.
- Opt-in data is sparse and self-selected; the curve is a floor, not
  a census.

### Risks

- Payload creep under product pressure. Mitigation: the battery
  asserts exact key sets at both payload levels; additions require a
  new ADR.
- The consent prompt erodes into a nag. Mitigation: either answer
  persists; the gate is a file-exists check, pinned by tests.
- A future contributor adds a network import elsewhere. Mitigation:
  the isolation rule fails the build.

## Alternatives Considered

### Self-hosted collector

A dead-simple endpoint RAC's maintainer controls.

#### Advantages

- No third-party processor; the strongest possible privacy story.

#### Disadvantages

- There is no lore domain or infrastructure to host it yet, and
  standing it up delays the signal. Revisit when infrastructure
  exists; the sink hides behind one constant.

### No remote telemetry ever

Keep the GitHub issue share flow as the only channel.

#### Advantages

- ADR-040's posture survives verbatim.

#### Disadvantages

- Retention is unmeasurable past the hand-callable scale; product
  investment returns to guesswork exactly when the stakes rise.

### Salted-hashed machine identifier

Derive the install id by hashing hostname or hardware attributes.

#### Advantages

- Survives a deleted consent file.

#### Disadvantages

- Derivable is the opposite of anonymous: a hash of machine
  attributes can in principle be correlated; a random token cannot.
  Random wins.

The consented daily ping with a pinned payload is selected.

## Relationship to Other Decisions

- ADR-040 (local telemetry): amended — its "RAC contains no network
  code" clause narrows to "the network surface is the ping module,
  and nothing sends without recorded consent". Local recording and
  the user-driven share flow are unchanged.
- ADR-032 (stateless reads): untouched — the ping runs outside the
  request/response contract; nothing it reads or writes ever feeds a
  tool response, and responses stay byte-identical.
- ADR-035 (no RAC cloud dependency): honored — the dependency is
  optional by consent and inert by the kill switch; core
  functionality never needs it.
- ADR-013 (Git as the state store): consent and ping state are
  user-machine state under XDG directories, never repository state.

## Success Measures

- A captured ping matches the pinned payload byte-for-byte and
  contains no path, salt, or repository content.
- Declining at `rac init` results in zero network attempts, verified
  by the battery's wire capture.
- The isolation battery rejects any network import outside the ping
  module.
- A retention curve exists by the first release where opt-in count
  exceeds what the maintainer can ring individually.

## Review Date

Review when a self-hosted collector becomes practical, when PostHog's
free tier no longer covers the volume, or when the first product
question demands a field the pinned payload lacks.

## Related Requirements

- rac-agent-context-guide
- rac-trust-transparency

## Related Roadmaps

- v0.10.6-anonymous-usage-sharing
