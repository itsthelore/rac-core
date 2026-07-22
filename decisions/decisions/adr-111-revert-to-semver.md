---
schema_version: 1
id: RAC-KX04DH293JG8
type: decision
---
# ADR-111: Revert to SemVer Release Versioning

## Context

ADR-076 (`RAC-KVPTVX3YZ87K`) moved RAC's releases from SemVer (`vX.Y.Z`) to
CalVer (`YYYY.MM.N`), normatively specified by REQ-Release-Versioning
(`RAC-KV3GGM1TFHY4`). Its reasoning was sound for the problem as framed: the
SemVer minors had become planning scope-fences that asserted a compatibility
contract RAC does not keep, the published package had stalled at `v0.19.0` while
the roadmap numbers ran ahead, and a date sorts above `0.19.0` so it becomes
"latest" on PyPI cleanly. Three CalVer releases shipped under it —
`2026.06.1`, `2026.06.4` ("unlock"), and `2026.06.5` ("rename").

In use, CalVer did not fit how the maintainer wants to communicate releases. A
date answers *how recent* but says nothing about *what changed or how much*, and
the maintainer wants the release identifier to carry that intent again — the
readable major/minor/patch cadence a reader and a changelog reader both reason
about — and to re-converge the release line with the long-running `vX.Y.Z`
roadmap series rather than keep two numbering worlds apart. ADR-076 recorded its
own cutover as one-way (its Decision §4, Negative §1); this decision reverses
that on the maintainer's judgement and records the reversal honestly rather than
letting the corpus and the tooling disagree with practice.

The one hard constraint ADR-076 leaned on remains real: PyPI resolves the
highest version, and a CalVer `2026.x` sorts *above* any `0.x`, so a SemVer
release cannot become "latest" while the CalVer releases stand. The answer is to
**yank** the three CalVer PyPI releases — a one-time cleanup the maintainer
accepts — after which the SemVer line resolves as latest.

## Decision

RAC returns to **Semantic Versioning** (`vX.Y.Z`) as its release identifier,
superseding ADR-076. REQ-Release-Versioning is rewritten to specify SemVer
normatively.

1. **The release identifier is `vX.Y.Z`.** setuptools-scm derives the build from
   the tag, exactly as before the CalVer cutover; the fail-closed release
   verifier (`python -m rac.release`) is updated to accept a well-formed
   `vX.Y.Z` / `X.Y.Z` tag and reject a `YYYY.MM.N` one, and to require a matching
   `CHANGELOG.md` entry (REQ-007 unchanged in spirit).
2. **Compatibility still has its own home.** `schema_version` (ADR-007) remains
   where contract compatibility is versioned; SemVer's minor/patch here signal
   the *shape and size* of a release for humans, not a machine-resolved
   contract, and the changelog remains the authority on what changed.
3. **The CalVer detour is remapped to SemVer, not erased.** The three CalVer
   releases and the untagged `v0.23.0 "Hardening"` changelog label are renumbered
   into one monotonic SemVer line, and the current release is cut as `v0.22.0`,
   re-aligning the published line with the `v0.22.x` roadmap series:

   | CalVer / label | SemVer | Release |
   | --- | --- | --- |
   | `v0.23.0` (untagged label) | **v0.20.0** | Hardening |
   | `2026.06.1` → `2026.06.4` | **v0.21.0** | "unlock" (CalVer adoption + first wave) |
   | `2026.06.5` | **v0.21.1** | "rename" |
   | *(this release)* | **v0.22.0** | "scale" |

4. **Tags and PyPI.** The three CalVer git tags (`2026.06.1`, `2026.06.4`,
   `2026.06.5`) are deleted; retroactive `v0.20.0` / `v0.21.0` / `v0.21.1` tags
   are added as git-only historical markers (not re-published), and `v0.22.0` is
   tagged on the release commit and published. The three CalVer PyPI releases are
   **yanked**, so the SemVer line — though it sorts numerically below `2026.x` —
   becomes the highest non-yanked version and resolves as "latest".
5. **Roadmap numbers and releases re-converge.** The `vX.Y.Z` roadmap series
   codenames (ADR-094) and the release identifiers share a numbering world again;
   ADR-076's split of the two is unwound. This is a convenience, not a promise —
   a roadmap codename is still a planning boundary, not a guarantee that a release
   of that number exists.

## Consequences

### Positive

- The release number communicates release intent (major/minor/patch) again,
  which is what the maintainer wants a reader to get from it.
- The published line re-aligns with the `v0.22.x` roadmap series, ending the
  two-numbering-worlds drift from the other direction.
- The corpus, the tooling, and practice agree: the recorded decision matches how
  releases are actually cut.

### Negative

- A one-time PyPI cleanup: the three CalVer releases must be yanked, and the
  retroactive SemVer versions for the older releases are git-only (not
  re-published), so the PyPI history shows a CalVer gap rather than a continuous
  SemVer line.
- SemVer's minor/patch can still be *read* as a compatibility promise RAC does
  not machine-enforce; this is mitigated by keeping `schema_version` (ADR-007) as
  the contract signal and treating the SemVer number as human-facing intent.
- Reversing a decision ADR-076 recorded as one-way sets the precedent that even
  "irreversible" process decisions can be revisited; recording it as a
  superseding ADR keeps that legible rather than silent.

## Status

Accepted

## Category

Process

## Alternatives Considered

### Stay on CalVer

Keep `YYYY.MM.N` as ADR-076 decided.

#### Pros

- No tooling, tag, or PyPI churn; honours ADR-076's stated one-way cutover.

#### Cons

- Leaves the release identifier saying only *when*, which the maintainer has
  determined does not serve how they want to communicate releases, and keeps the
  release line and the roadmap series in separate numbering worlds.

Rejected on the maintainer's judgement that the fit is wrong.

### Start SemVer fresh at `v0.22.0`, leave the CalVer releases as historical CalVer

Resume SemVer going forward without renumbering the three CalVer releases.

#### Pros

- Less changelog and tag surgery.

#### Cons

- Leaves a permanent CalVer island in the middle of an otherwise SemVer history,
  and the CalVer PyPI releases still sort above `v0.22.0` unless yanked — so the
  yank is required either way, and remapping is the cheap part that makes the
  history one legible line.

Rejected in favour of the monotonic remap.

## Success Measures

- `v0.22.0` publishes to PyPI and, with the CalVer releases yanked, resolves as
  "latest".
- The release verifier accepts `vX.Y.Z` and rejects `YYYY.MM.N`; no release
  publishes with a malformed version or a missing changelog entry.
- The corpus validates with ADR-076 `Superseded` and no live artifact referencing
  a retired decision.

## Supersedes

- ADR-076

## Related Decisions

- ADR-007
- ADR-094
