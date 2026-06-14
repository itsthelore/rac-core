---
schema_version: 1
id: RAC-KV2E5B1122YN
type: decision
---
# ADR-045: Recency Is Derived From Git, Not Stored In Frontmatter

## Status

Accepted

## Category

Technical

## Context

The Welcome series wants a write-habit signal: a cadence nudge
(v0.13.3) that notices when a corpus has stopped growing, and a basis
for measuring whether users keep authoring. Both need to know when an
artifact was last written. RAC artifacts carry no such timestamp:
frontmatter is exactly `schema_version`, `id`, `type`, and
`relationships` (the hybrid-metadata contract, ADR-025), and `type`
schemas deliberately avoid dates — ADR-017 keeps RAC out of work
tracking, which is where created/updated/due dates usually lead.

Two sources could supply recency. A frontmatter date field would be
self-contained but require a `schema_version` bump, would be
hand-maintained and so drift from reality, and would push RAC toward the
work-status modelling ADR-017 rejects. Git history already records,
precisely and automatically, when every file last changed, and ADR-013
makes leveraging existing source control a standing principle. ADR-043
already isolated git access to one module for watchkeeper.

## Decision

Artifact recency is derived from git history, never stored in artifacts.

- A `recency` service computes each artifact's last-authored time from
  `git log -1 --format=%cI -- <path>` (commit time, ISO-8601,
  timezone-aware), plus corpus aggregates (most recent overall and per
  type).
- No frontmatter field is added and `schema_version` is not bumped. The
  supported field set is unchanged.
- Recency is advisory and degrades to "unknown" (`None`) rather than
  raising: outside a git repository, or for untracked or uncommitted
  files, the answer is unknown, never an error.
- Git access stays isolated, alongside `revisions.py`, to honour
  ADR-043's single-boundary posture; no other service imports git
  helpers.
- Recency is framed as a *capture-cadence* signal — "when product
  knowledge was last written" — explicitly not a work-status, deadline,
  or review-due signal, so consumers (the cadence nudge) stay inside
  ADR-017.

## Consequences

### Positive

- No schema change, no migration, no hand-kept dates: the timestamp is
  always real because git maintains it.
- The write-habit features (v0.13.3, v0.13.4) get the data they need
  while RAC stays out of work tracking (ADR-017 intact).
- Reuses the established git posture (ADR-013, ADR-043): read-only,
  offline, no `.git` mutation.

### Negative

- Recency is only available inside a git repository; corpora kept
  outside version control have no cadence signal. Accepted: RAC's
  audience versions knowledge alongside code (ADR-013).
- Commit time moves under rebase, amend, or squash, so recency reflects
  history rewriting, not only original authorship. Accepted for a
  cadence signal, where "recently touched in history" is the intent.

### Risks

- Per-file `git log` is one subprocess each. Mitigated: corpora are
  small and recency is computed only on demand.
- A future need for true authored-vs-edited semantics could outgrow
  commit time. Mitigated: the service boundary is narrow; its internals
  can change without touching artifacts.

## Alternatives Considered

### A frontmatter date field

Add `created`/`updated` to frontmatter, bumping `schema_version`.

#### Advantages

- Self-contained; works without git.

#### Disadvantages

- Hand-maintained dates drift from reality, a `schema_version` bump and
  migration are required, and date fields pull RAC toward the work-status
  modelling ADR-017 rejects. Git already has the truth.

### Filesystem modification time

Use each file's mtime.

#### Advantages

- No git dependency; trivial to read.

#### Disadvantages

- mtime is not portable across clones, is reset by checkouts and tooling,
  and means nothing about when knowledge was authored. It is noise, not a
  cadence signal.

### A git library dependency

Read history via a Python git implementation.

#### Advantages

- No reliance on a git binary.

#### Disadvantages

- A heavyweight dependency for one porcelain call, against the package's
  minimal-dependency posture and inconsistent with ADR-043, which already
  shells out to git.

## Success Measures

- Recency for a corpus committed at a known time matches that time, per
  artifact and in aggregate, in a throwaway-repository test.
- Untracked files and non-git directories yield "unknown" with no
  exception crossing the service boundary.
- No frontmatter or `schema_version` change accompanies the feature.

## Review Date

Revisit if a consumer needs to distinguish original authorship from later
edits, at which point commit time alone is insufficient and the source of
recency needs reconsidering.

## Related Decisions

- adr-013
- adr-017
- adr-025
- adr-043

## Related Requirements

- rac-growth-adoption

## Related Roadmaps

- v0.13.2-git-recency
