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

Accepted

## Problem

RAC published its own releases under Semantic Versioning (`vX.Y.Z`), and
setuptools-scm derived the package version from those tags. SemVer makes a
promise RAC's release stream does not keep: a patch bump asserts a
backward-compatible bug fix, a minor bump asserts backward-compatible new
behaviour, yet RAC's user-visible changes — CLI output, validation strictness,
artifact rules — do not map cleanly onto that contract, and no programmatic
consumer resolves these version constraints. In practice the SemVer minors were
used as roadmap scope-fences, not releases: the planning numbers ran to v0.26
while the published package sat at `v0.19.0`, and the number was read by humans
scanning history, where the question is really *how recent is this build*, not
*is it compatible with my pin*.

A date-based release identity answers the question that is actually asked. It
states *when* a release was cut and stops encoding a compatibility claim RAC does
not maintain on the version string. Compatibility, where RAC needs to signal it,
already has an independent home in the schema/contract version (ADR-007), so the
two concerns are separated cleanly rather than overloaded onto one identifier.

This requirement is `Accepted` and adopted by ADR-076. The release cadence is
monthly rather than daily, so the identifier is month-granular with a
within-month counter (`YYYY.MM.N`) rather than a full calendar date. The
versioned roadmap series (`vX.Y.Z`) were, at the time of the CalVer cutover,
explicitly **internal scope-fences** decoupled from release identifiers (ADR-094
later retired that scheme for *live* roadmaps in favour of codenames; shipped and
historical series keep their versioned names as the record); the pre-cutover
SemVer tags stand immutably.

## Requirements

- [REQ-001] A release version MUST be of the form `YYYY.MM.N`, where `YYYY` is a four-digit UTC year, `MM` a zero-padded month `01`–`12`, and `N` a within-month release counter; the year and month MUST be the UTC year and month in which the release is cut, so the identifier is deterministic and timezone-independent.

- [REQ-002] The counter `N` MUST start at `1` for the first release of a given month and rise by one for each subsequent release that month (`2026.06.1`, `2026.06.2`, …); a counter of `0`, a leading-zero counter (`01`), and a bare `YYYY.MM` with no counter are invalid.

- [REQ-003] Release precedence MUST be the lexicographic order of the tuple `(YYYY, MM, N)`, so that `2026.06.1` precedes `2026.06.2`, which precedes `2026.07.1`.

- [REQ-004] The release version MUST NOT encode any compatibility, stability, or severity signal; any such signal MUST live on the independent schema/contract version (ADR-007, `schema_version`), which versions and stabilises RAC's contracts separately from the release identifier.

- [REQ-005] A release MUST be event-triggered, assigning a new release version only when released content has changed; each release MUST correspond to exactly one commit and exactly one immutable tag, and MUST have a changelog entry recording its user-visible changes.

- [REQ-006] A build that is not itself a release MUST carry a VCS-derived identifier (for example a development or local segment over the base release) that orders strictly after its base release and strictly before the next release or same-month increment, and a build identifier MUST NOT be mistaken for a release version.

- [REQ-007] Release verification MUST fail closed: a candidate version that is not a well-formed `YYYY.MM.N` identifier under REQ-001–REQ-003, or that lacks the changelog entry required by REQ-005, MUST NOT be published.

- [REQ-008] Adoption MUST be a one-way cutover: pre-cutover SemVer tags (`vX.Y.Z`) MUST be retained immutably and MUST NOT be reinterpreted as dates, and RAC's own tooling MUST NOT co-order date versions and SemVer versions in one precedence relation, so the two remain distinct ordering domains separated at the cutover boundary. (At the packaging layer a date version such as `2026.06.1` necessarily sorts above the final SemVer `0.19.0`, which is what lets it become "latest" on the index; this requirement constrains RAC's verifier, not the index's numeric ordering.)

- [REQ-009] The canonical display and tag form MUST be the zero-padded `YYYY.MM.N`, and a tool comparing versions MUST treat the PEP 440 normalised form (for example `2026.6.1`) as equal to its zero-padded canonical form (`2026.06.1`), so packaging-layer normalisation does not create a spurious mismatch.

## Acceptance Criteria

- A verifier accepts `2026.06.1`, `2026.06.2`, `2026.12.1`, and `2027.01.10`,
  and rejects `2026.13.1`, `2026.00.1`, `2026.06.0`, `2026.06.01`, the bare
  `2026.06`, and any SemVer-form tag (`v0.19.0`) presented as a release version.
- The normalised spelling `2026.6.1` parses equal to the canonical `2026.06.1`.
- Sorting a set of valid release versions yields the REQ-003 order.
- A release lacking a changelog entry is rejected by the fail-closed check.
- Pre-cutover SemVer tags remain present and unmodified after the cutover, and no
  comparison places a date version and a SemVer version in one ordered sequence.

## Success Metrics

- Every published release version is a well-formed `YYYY.MM.N` identifier that
  round-trips through parse → sort → display without ambiguity.
- The release identifier and the schema/contract version (ADR-007) move
  independently: a release can be cut without a contract change, and a contract
  change is recorded on its own version, neither overloading the other.
- The cutover is documented once and requires no rewriting of historical tags.

## Risks

- A cutover that co-orders SemVer and date tags under one relation would corrupt
  "latest release" selection. Mitigated by REQ-008's distinct ordering domains and
  immutable retention.
- Packaging-layer normalisation (PEP 440 dropping zero padding) could make a tool
  see two spellings of one version. Mitigated by REQ-009.
- Month granularity cannot distinguish two releases in the same month on its own.
  Mitigated by REQ-002's within-month counter.

## Assumptions

- Compatibility signalling has, or can have, an independent home on the
  schema/contract version (ADR-007); this requirement concerns the *release*
  identifier, not that mechanism.
- Release year and month are assigned in UTC by the release process, so the
  identifier is deterministic regardless of the releaser's local timezone.
- The release cadence is monthly or slower; a same-month second release is the
  exception handled by the counter, not the norm.

## Priority

Below RAC's core validation guarantees and additive to them: this changes only
how RAC labels its own releases, not what `rac validate` or `rac relationships
--validate` accept.

## Related Decisions

- ADR-007
- ADR-076
- ADR-094
