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

RAC first published under SemVer (`vX.Y.Z`), then adopted CalVer (`YYYY.MM.N`)
via ADR-076 to answer *how recent is this build* and to sort a release above the
stalled `v0.19.0` on PyPI. In use the date-only identifier did not fit how the
maintainer wants to communicate releases — it says nothing about *what changed or
how much* — and it kept the release line and the `vX.Y.Z` roadmap series in two
numbering worlds. ADR-111 reverts to SemVer and this requirement is rewritten to
specify it normatively; the three CalVer releases are remapped to SemVer and the
CalVer PyPI releases yanked, so a SemVer release resolves as "latest" again.

Compatibility, where RAC needs to signal it, still has an independent home in the
schema/contract version (ADR-007), so the release identifier is not overloaded
with a machine-resolved contract claim: the SemVer number is human-facing release
intent, and the changelog is the authority on what changed.

## Requirements

- [REQ-001] A release version MUST be of the form `vX.Y.Z` (major, minor, patch), where `X`, `Y`, and `Z` are non-negative integers without leading zeros; the canonical tag form is `v`-prefixed (`v0.22.0`) and the PEP 440 normalised distribution form drops the prefix (`0.22.0`).

- [REQ-002] The three components MUST follow Semantic Versioning ordering: the patch `Z` rises within a minor, the minor `Y` within a major, and a higher component resets the lower ones to `0` (`v0.22.0`, `v0.22.1`, `v0.23.0`).

- [REQ-003] Release precedence MUST be the SemVer precedence of the tuple `(X, Y, Z)`, so that `v0.22.0` precedes `v0.22.1`, which precedes `v0.23.0`.

- [REQ-004] The release version MUST NOT be relied on as a machine-resolved compatibility contract; contract compatibility MUST live on the schema/contract version (ADR-007, `schema_version`), which versions RAC's contracts separately from the release identifier — the SemVer major/minor/patch is human-facing release intent, not a guarantee the tooling enforces.

- [REQ-005] A release MUST be event-triggered, assigning a new release version only when released content has changed; each release MUST correspond to exactly one commit and exactly one immutable tag, and MUST have a changelog entry recording its user-visible changes.

- [REQ-006] A build that is not itself a release MUST carry a VCS-derived identifier (for example a development or local segment over the base release) that orders strictly after its base release and strictly before the next release, and a build identifier MUST NOT be mistaken for a release version.

- [REQ-007] Release verification MUST fail closed: a candidate version that is not a well-formed `vX.Y.Z` identifier under REQ-001–REQ-003, or that lacks the changelog entry required by REQ-005, MUST NOT be published, and a `YYYY.MM.N` CalVer identifier MUST be rejected by the verifier.

- [REQ-008] The CalVer detour is remapped, not co-ordered: the three published CalVer releases (`2026.06.1`, `2026.06.4`, `2026.06.5`) and the untagged `v0.23.0` changelog label MUST be renumbered into one monotonic SemVer line (`v0.20.0`, `v0.21.0`, `v0.21.1`, `v0.22.0`), their CalVer git tags deleted and the CalVer PyPI releases yanked; RAC's tooling MUST NOT co-order CalVer and SemVer identifiers in one precedence relation, and because a CalVer `2026.x` sorts above any `0.x` on PyPI, yanking the CalVer releases is what lets the SemVer line resolve as "latest".

- [REQ-009] The canonical display and tag form MUST be `v`-prefixed `vX.Y.Z`, and a tool comparing versions MUST treat the PEP 440 normalised form (`0.22.0`) as equal to its canonical tag form (`v0.22.0`), so packaging-layer normalisation does not create a spurious mismatch.

## Acceptance Criteria

- A verifier accepts `v0.22.0`, `v0.22.1`, `v1.0.0`, and `v2.3.10`, and rejects
  `2026.06.1`, `v0.22`, `v01.2.3`, a bare `0.22`, and any `YYYY.MM.N` CalVer tag
  presented as a release version.
- The normalised spelling `0.22.0` parses equal to the canonical `v0.22.0`.
- Sorting a set of valid release versions yields the REQ-003 (SemVer) order.
- A release lacking a changelog entry is rejected by the fail-closed check.
- After the remap, `v0.22.0` publishes and — with the CalVer PyPI releases
  yanked — resolves as "latest".

## Success Metrics

- Every published release version is a well-formed `vX.Y.Z` identifier that
  round-trips through parse → sort → display without ambiguity.
- The release identifier and the schema/contract version (ADR-007) move
  independently: a release can be cut without a contract change, and a contract
  change is recorded on its own version, neither overloading the other.
- The release line and the `vX.Y.Z` roadmap series share one numbering world
  again, with the CalVer detour recorded as remapped history.

## Risks

- SemVer's minor/patch can be *read* as a compatibility promise RAC does not
  machine-enforce. Mitigated by REQ-004: compatibility lives on `schema_version`,
  and the SemVer number is treated as human-facing intent, not a resolved pin.
- The CalVer PyPI releases sort above `v0.22.0`, so a stale index could resolve a
  CalVer release. Mitigated by yanking them (REQ-008), after which the SemVer
  line is the highest non-yanked version.
- Retroactive SemVer versions for the older releases are git-only, so the PyPI
  history shows a CalVer gap rather than a continuous SemVer line. Accepted as a
  one-time cost of the reversal.

## Assumptions

- Compatibility signalling has, or can have, an independent home on the
  schema/contract version (ADR-007); this requirement concerns the *release*
  identifier, not that mechanism.
- The release cadence and its labelling are the maintainer's to set; this
  requirement fixes the *form* and *ordering* of the identifier, not the pace.

## Priority

Below RAC's core validation guarantees and additive to them: this changes only
how RAC labels its own releases, not what `rac validate` or `rac relationships
--validate` accept.

## Related Decisions

- ADR-007
- ADR-094
- ADR-111
