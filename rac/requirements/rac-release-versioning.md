---
schema_version: 1
id: RAC-KV3GGM1TFHY4
type: requirement
---
# REQ-Release-Versioning

> The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY in this document are
> to be interpreted as described in BCP 14 (RFC 2119, RFC 8174) when, and only
> when, they appear in all capitals.

## Status

Proposed

## Problem

RAC publishes its own releases under Semantic Versioning (`vX.Y.Z`), and
setuptools-scm derives the package version from those tags. SemVer makes a
promise RAC's release stream does not keep: a patch bump asserts a
backward-compatible bug fix, a minor bump asserts backward-compatible new
behaviour, yet RAC's user-visible changes — CLI output, validation strictness,
artifact rules — do not map cleanly onto that contract, and no programmatic
consumer resolves these version constraints. The number is read by humans
scanning history, where the question is really *how recent is this build*, not
*is it compatible with my pin*.

A date-based release identity answers the question that is actually asked. It
states *when* a release was cut and stops encoding a compatibility claim RAC does
not maintain on the version string. Compatibility, where RAC needs to signal it,
already has an independent home in the schema/contract version (ADR-007), so the
two concerns can be separated cleanly rather than overloaded onto one identifier.

This requirement captures the date-based scheme as a recorded option. It is
filed `Proposed` and changes no tooling: the current SemVer release flow,
setuptools-scm configuration, the existing `vX.Y.Z` tag history, and the
versioned roadmap series all stand. Promotion to a decision, a roadmap, and an
implementation is deferred until release cadence or consumer needs justify the
apparatus.

## Requirements

- [REQ-001] A release version MUST be a UTC calendar date of the form `YYYY.MM.DD`, where `YYYY` is a four-digit year, `MM` a zero-padded month `01`–`12`, and `DD` a zero-padded day valid for that month and year (including leap-year February); the date MUST be the UTC date on which the release is cut, so the identifier is deterministic and timezone-independent.

- [REQ-002] When a single release is cut on a given UTC date, the version MUST omit the increment segment (`YYYY.MM.DD`); when more than one release is cut on the same UTC date, each release after the first MUST carry an increment segment starting at `.2` and rising by one (`YYYY.MM.DD.2`, `YYYY.MM.DD.3`, …), and an explicit `.1`, an increment of `.0`, and any leading-zero increment (`.02`) are invalid.

- [REQ-003] Release precedence MUST be the lexicographic order of the tuple `(YYYY, MM, DD, increment)`, where an omitted increment is treated as `1`, so that `2026.06.14` precedes `2026.06.14.2`, which precedes `2026.06.15`.

- [REQ-004] The release version MUST NOT encode any compatibility, stability, or severity signal; any such signal MUST live on the independent schema/contract version (ADR-007, `schema_version`), which versions and stabilises RAC's contracts separately from the release date.

- [REQ-005] A release MUST be event-triggered, assigning a new release version only when released content has changed; each release MUST correspond to exactly one commit and exactly one immutable tag, and MUST have a changelog entry recording its compatibility-surface changes.

- [REQ-006] A build that is not itself a release MUST carry a VCS-derived identifier (for example a development or local segment over the base release) that orders strictly after its base release and strictly before the next release or same-day increment, and a build identifier MUST NOT be mistaken for a release version.

- [REQ-007] Release verification MUST fail closed: a candidate version that is not a well-formed, calendar-valid date under REQ-001–REQ-003, or that lacks the changelog entry required by REQ-005, MUST NOT be published.

- [REQ-008] Adoption MUST be a one-way cutover: pre-cutover SemVer tags (`vX.Y.Z`) MUST be retained immutably and MUST NOT be reinterpreted as dates or placed in a single precedence relation with date versions, so that date versions and SemVer versions remain distinct ordering domains separated at the cutover boundary.

- [REQ-009] The canonical display form MUST be the zero-padded `YYYY.MM.DD[.increment]`, and a tool comparing versions MUST treat the PEP 440 normalised form (for example `2026.6.14`) as equal to its zero-padded canonical form, so packaging-layer normalisation does not create a spurious mismatch.

## Acceptance Criteria

- A verifier accepts `2026.06.14`, `2026.06.14.2`, `2026.12.31`, and
  `2024.02.29`, and rejects `2026.13.01`, `2026.00.10`, `2026.02.30`,
  `2025.02.29`, `2026.06.14.1`, `2026.06.14.0`, `2026.06.14.02`, and any
  SemVer-form tag (`v0.13.7`) presented as a release version.
- Sorting a set of valid release versions yields the REQ-003 order, with omitted
  increments ordered as `1`.
- A release lacking a changelog entry is rejected by the fail-closed check.
- Pre-cutover SemVer tags remain present and unmodified after the cutover, and no
  comparison places a date version and a SemVer version in one ordered sequence.

## Success Metrics

- Every published release version is a calendar-valid UTC date that round-trips
  through parse → sort → display without ambiguity.
- The release-date identifier and the schema/contract version (ADR-007) move
  independently: a release can be cut without a contract change, and a contract
  change is recorded on its own version, neither overloading the other.
- The cutover is documented once and requires no rewriting of historical tags.

## Risks

- The motivating pressure (many releases per day, SemVer patch numbers read as
  recency) may be weaker than the cost of replacing a working SemVer +
  setuptools-scm pipeline. Mitigated by filing this `Proposed` and deferring
  implementation until cadence justifies it.
- A cutover that co-orders SemVer and date tags under one relation would corrupt
  "latest release" selection. Mitigated by REQ-008's distinct ordering domains and
  immutable retention.
- Packaging-layer normalisation (PEP 440 dropping zero padding) could make a tool
  see two spellings of one version. Mitigated by REQ-009.

## Assumptions

- Compatibility signalling has, or can have, an independent home on the
  schema/contract version (ADR-007); this requirement concerns the *release*
  identifier, not that mechanism.
- Release dates are assigned in UTC by the release process, so the identifier is
  deterministic regardless of the releaser's local timezone.
- The increment form is confirmed as omit-when-single: a sole daily release is
  bare `YYYY.MM.DD`, and `.2` is the first explicit increment.

## Priority

Below RAC's core validation guarantees and additive to them: this changes only
how RAC labels its own releases, not what `rac validate` or `rac relationships
--validate` accept. It is recorded now to preserve the reasoning; it is not
scheduled. Promotion to an ADR, a roadmap item, and an implementation is a
separate, later decision contingent on release cadence or consumer demand.

## Related Decisions

- ADR-007
