---
schema_version: 1
id: RAC-KWGMTEW4T2D0
type: roadmap
---
# Cross-Language Conformance Fixture Suite

## Status

Planned

Unscheduled member of the `agnostic-surfaces` programme, Track 2
(contract hardening). This is the second of ADR-063's two native-port
preconditions: "a cross-language conformance fixture suite proves
output parity." It also answers the risk four of six council ballots
flagged — every additional client multiplies contract-churn cost until
a fixture suite keeps them honest.

## Outcomes

- There is one runnable definition of "agrees with the engine": a
  fixture corpus plus pinned expected outputs that any client in any
  language can replay against its own deserialization.
- The existing TypeScript SDK is the first consumer: its CI exercises a
  real engine against the suite, replacing the integration path that is
  currently skipped for lack of a `RAC_BIN`.
- Contract drift is caught at the pull request that causes it, in
  whichever repo it lands.

## Initiatives

- Settle the home question recorded as open in `sdk-expansion-strategy`
  (proposed: fixtures and pinned outputs live beside the contract in
  the engine repo, versioned with it; consumers fetch or vendor them by
  release — decide and record at pickup).
- Seed the suite from what already exists: the byte-pinned golden
  `--json` outputs and the fixture corpora in the engine's test tree
  already cover validate, resolve, find, relationships, review, stats,
  export, and schema — package that pairing (corpus in, expected JSON
  out) as a consumable artifact rather than inventing a parallel one.
- Define the replay contract: for each case, the command argv, the
  fixture corpus path, the expected stdout, and the expected exit code;
  a conforming client must produce equal deserialized results (field
  order per ADR-007, additive fields tolerated).
- Wire the TypeScript SDK's CI to install the engine, run the suite,
  and fail on divergence — converting its existing skipped integration
  tests into a required conformance job (per-service battery, merge
  gate per ADR-027 and ADR-075 practice).
- Document the suite as the entry bar for any future client, per the
  reordering trigger recorded by the council ("TS SDK 1.0 + conformance
  suite operational" is the standing precondition for any second SDK).

## Constraints

- The suite tests the contract, not internals: only documented `--json`
  outputs, export payloads, and exit codes are pinned (ADR-007,
  ADR-063).
- Additive tolerance is built in: a client must not fail when the
  engine adds fields; it must fail when documented fields change shape
  or disappear.
- Deterministic and offline (ADR-002, ADR-066): fixtures are committed
  corpora; no network, no generation at test time.
- No native reimplementation is smuggled in: the suite proves clients
  deserialize the one engine correctly; it does not certify a second
  engine (that remains gated by ADR-063 in full).

## Success Measures

- The TypeScript SDK repo has a required CI job that replays the suite
  against a real installed engine, and it is green.
- A deliberate contract-breaking engine change fails the suite before
  merge; a purely additive change passes without client edits.
- The suite's case list covers every command the TypeScript client
  wraps.

## Assumptions

- The existing golden corpus is a sufficient seed; gaps (for example
  stdin validation and agent-rules output) are added as cases, not as a
  new mechanism.
- Cross-repo consumption (engine fixtures, SDK CI) is workable with
  release-pinned fetching or vendoring; the exact mechanism is an
  implementation detail decided at pickup.

## Risks

- Byte-pinning JSON across languages overreaches (key order, number
  formatting) and produces false failures; mitigated by comparing
  deserialized structures, not bytes, on the client side.
- Fixture drift between repos if the suite is vendored and forgotten;
  mitigated by pinning suite version to engine release and surfacing
  the pin in the SDK's CI job.
- The suite ossifies exploratory output surfaces too early; mitigated
  by pinning only documented stable contracts and leaving experimental
  flags out until documented.

## Related Decisions

- ADR-002
- ADR-007
- ADR-027
- ADR-063
- ADR-066
- ADR-075

## Related Roadmaps

- agnostic-surfaces
- artifact-specs-extraction
- ts-sdk-stable-release
