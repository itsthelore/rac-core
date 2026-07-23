---
schema_version: 1
id: RAC-KTYZVKZQWD98
type: decision
---
# ADR-043: Watchkeeper Revision Materialization

## Status

Accepted

## Category

Technical

## Context

The watchkeeper series (v0.12.x) compares two repository states. The
head state is normally the working tree; the base state is normally a
git revision such as `main` or a pull request base ref. Something has
to turn a revision name into a directory of artifact files that the
existing corpus loader can walk — and RAC's services have been
deliberately git-free to date: every service takes a directory and
reads bytes.

Three properties matter. The comparison services must stay testable
without git (golden tests pin output byte-for-byte and must not depend
on repository state). Nothing may mutate the user's repository — a
review tool that touches `.git` state forfeits trust and complicates
concurrent CI runs. And the mechanism must be offline: no network, per
the trust posture recorded across the corpus.

## Decision

Revision materialization is isolated in one module,
`src/rac/services/revisions.py` — the only git-aware code in the
package — and implemented with `git archive`.

- `materialized_revision(repo_root, rev, subpath)` is a context
  manager: it runs `git archive --format=tar <rev> -- <subpath>`,
  extracts the tar stream into a temporary directory, yields the
  materialized corpus path, and removes the directory on exit.
- The repository root is discovered with `git rev-parse
  --show-toplevel` from the corpus directory; the subpath is the corpus
  directory relative to that root, so only corpus files are extracted.
- Unknown revisions raise `RevisionNotFound`; running outside a git
  repository raises `NotAGitRepository`. The CLI maps both to exit 2.
- A revision that exists but lacks the corpus subpath materializes an
  empty directory: an empty base corpus is a valid "everything added"
  comparison, which is exactly the fresh-adoption case.
- The comparison services themselves never see git: both sides of a
  comparison are plain directories. The CLI treats a base or head value
  naming an existing directory as that directory and resolves anything
  else as a revision — which also keeps golden tests git-free.

## Consequences

### Positive

- The git surface of RAC is one small module invoking two well-known
  porcelain commands with captured output; everything else stays pure.
- No `.git` mutation: concurrent CI runs and user working trees are
  untouched, and there is no cleanup liability beyond a temporary
  directory.
- Directory-to-directory comparison keeps tests deterministic and lets
  users compare arbitrary snapshots (an export, a backup) for free.

### Negative

- Materialization copies corpus bytes per invocation. Corpora are
  Markdown measured in kilobytes; accepted.
- `git archive` honours `export-ignore` attributes, so a repository
  that marks corpus files export-ignored would silently exclude them.
  Documented; no RAC repository has a reason to do that.

### Risks

- A future service importing git helpers directly would erode the
  single-module isolation. Mitigated: the watchkeeper battery asserts
  the comparison services accept plain directories, and review should
  hold the import boundary.

## Alternatives Considered

### git worktree add

Create a linked worktree for the base revision and point the loader at
it.

#### Advantages

- A real checkout; no tar handling.

#### Disadvantages

- Registers state in `.git/worktrees` that must be pruned, fails on
  concurrent runs against the same revision without unique paths,
  materializes the whole tree rather than the corpus subpath, and
  mutates the user's repository metadata — the property this decision
  exists to avoid.

### git show per file

List files with `git ls-tree`, then `git show rev:path` for each.

#### Advantages

- No temporary directory; fully streaming.

#### Disadvantages

- One subprocess per file and a bespoke in-memory corpus loader,
  duplicating the directory walker the services already share. The
  existing loader takes a directory; materializing one is the smallest
  seam.

### A git library dependency

Use a Python git implementation instead of subprocesses.

#### Advantages

- No reliance on a git binary on PATH.

#### Disadvantages

- A heavyweight dependency for two porcelain calls, against the
  package's minimal-dependency posture. Every environment running a
  pull request review has git.

## Success Measures

- A corpus round-trips byte-for-byte through materialization from a
  throwaway repository in the revisions battery.
- Unknown revisions and non-git directories fail with exit 2 and a
  one-line message, never a traceback.
- Golden tests for watchkeeper run with no git repository involved.

## Review Date

Review if a consumer needs comparison across remotes (fetching), at
which point the offline constraint needs its own decision.

## Related Requirements

- rac-product-intent-ci-watchkeeper

## Related Roadmaps

- v0.12.0-repository-review
