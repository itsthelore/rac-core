---
schema_version: 1
id: RAC-KVPTVX3YZ87K
type: decision
---
# ADR-076: Adopt CalVer (`YYYY.MM.N`) for RAC Releases

## Context

RAC published its package under SemVer (`vX.Y.Z`), with setuptools-scm deriving
the build from the latest tag. Two numbering systems had quietly diverged: the
roadmap series (`vX.Y.Z`) ran to v0.26 as planning **scope-fences**, while the
published PyPI package sat at `v0.19.0` — nothing had been tagged in seven
series. The SemVer minors were never used as release promises; they were scope
fences, and a patch/minor bump asserted a compatibility contract RAC does not
maintain on the version string and no consumer resolves.

REQ-Release-Versioning (`RAC-KV3GGM1TFHY4`) captured the date-based alternative
in detail and sat `Proposed`, deferred until cadence justified it. That point
has arrived: a backlog of shipped work needs releasing, and the maintainer
confirmed releases are cut monthly, not daily. A constraint also forces the
shape of the answer — PyPI versions are one-way: `0.1.0`…`0.19.0` are already
published and immutable, and pip resolves the highest version, so the next
release must sort **above** `0.19.0`. A `YYYY.MM.N` identifier does (`2026.06.1`
→ `(2026, 6, 1)` ≫ `(0, 19, 0)`), which both honours the constraint and answers
the question a reader actually asks of the number: *how recent is this build*.

## Decision

RAC releases adopt CalVer of the form **`YYYY.MM.N`** — the UTC year and
zero-padded month a release is cut, plus a within-month counter starting at `1`
— as specified normatively by REQ-Release-Versioning (now `Accepted`).

1. **The release identifier is `YYYY.MM.N`.** Month-granular with a within-month
   counter (`2026.06.1`, `2026.06.2`, `2026.07.1`), matching a monthly cadence.
   The first release under this scheme is `2026.06.1`.
2. **The version carries no compatibility signal.** Stability and contract
   compatibility live on `schema_version` (ADR-007), independent of the release
   date. The CalVer number says only *when*.
3. **Roadmap `vX.Y.Z` numbers stay as internal scope-fences**, decoupled from
   release identifiers. They schedule and bound work; they are not releases.
4. **The cutover is one-way (REQ-008).** Pre-cutover SemVer tags (`v0.1.0`…
   `v0.19.0`) are retained immutably and never reinterpreted as dates; RAC's own
   tooling does not co-order the two domains. Once a `2026.x` tag exists there is
   no return to `0.x`/`1.x` — those sort lower and pip would ignore them.
5. **Release is fail-closed (REQ-007).** The publish workflow verifies the tag is
   a well-formed `YYYY.MM.N` identifier and that `CHANGELOG.md` has a matching
   entry before anything is built or published (`python -m rac.release`).

## Principles

### Principle 1 — The release number answers the question it is actually asked

Readers ask "how recent is this build", not "is it compatible with my pin". A
date answers the former honestly; SemVer answered the latter falsely.

### Principle 2 — Compatibility has its own home

`schema_version` (ADR-007) versions RAC's contracts. Overloading that onto the
release string is what made SemVer misleading; CalVer keeps the two separate.

### Principle 3 — Scope-fences and releases are different things

The roadmap `vX.Y.Z` numbers are planning boundaries and remain useful as such.
Releases are date-stamped events. Conflating them is what let the two numbering
systems drift seven versions apart.

## Consequences

### Positive

- The next release sorts above `0.19.0`, so it cleanly becomes "latest" on PyPI;
  the publish pipeline (setuptools-scm → tag) needs no change beyond the tag form.
- No more debating whether a change is a "minor" or whether the product is "1.0":
  the date is the version.
- A fail-closed verifier prevents a malformed tag or a release with no changelog
  entry from publishing.

### Negative

- The cutover is irreversible: CalVer is a permanent commitment, and SemVer
  numbers can never be used again for this package.
- A date carries no semantic-change signal; consumers wanting a compatibility
  cue must read `schema_version` or the changelog, not the version.
- The roadmap `vX.Y.Z` numbers no longer correspond to released versions, which
  readers used to (loosely) assume; this ADR and the changelog record the split.

## Alternatives Considered

### Cut a `v1.0.0` (or continue `v0.20.0+`) under SemVer

Stay on SemVer and release the backlog as `1.0.0` or `0.26.0`.

#### Pros

- Familiar; no tooling or convention change.

#### Cons

- Keeps asserting a compatibility contract RAC does not maintain, and re-opens
  the "what does the minor mean / is it 1.0 yet" question every release — the
  exact friction that left the package unreleased for seven series.

Rejected in favour of separating recency (the date) from compatibility
(`schema_version`).

### Day-granular CalVer `YYYY.MM.DD` (REQ-Release-Versioning as first drafted)

The originally-proposed scheme, with same-day `.2`/`.3` increments.

#### Pros

- Encodes the exact release day.

#### Cons

- Its motivation was many releases per day; the actual cadence is monthly, so a
  full date is more precision than the cadence carries.

Rejected; the requirement was revised to the month-granular `YYYY.MM.N`.

## Status

Superseded

Superseded by ADR-111, which reverts RAC to SemVer (`vX.Y.Z`). The CalVer scheme
this ADR adopted did not fit how the maintainer wants to communicate releases;
the three CalVer releases are remapped to SemVer and the CalVer PyPI releases are
yanked. See ADR-111 for the reversal and the remap.

## Category

Process

## Relationship to Other ADRs

### ADR-007 JSON Contract Stability

`schema_version` is where compatibility is versioned. This ADR moves the release
identifier off that job entirely, so the two signals stop being overloaded onto
one string.

### ADR-027 CI Test Topology — Merge-Gated, Per-Service Batteries

The release gate (ADR-027 rule 2) already blocks publishing on a red suite; this
ADR adds the fail-closed version/changelog check as a sibling release gate.

## Success Measures

- The first `2026.06.1` release publishes to PyPI and resolves as "latest".
- No release publishes with a malformed version or a missing changelog entry.
- The release identifier and `schema_version` move independently.
- Historical `vX.Y.Z` tags remain present and unmodified.

## Related Decisions

- ADR-007
- ADR-027
