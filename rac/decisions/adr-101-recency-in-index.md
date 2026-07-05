---
schema_version: 1
id: RAC-KWS8TTSKMGQA
type: decision
---
# ADR-101: Recency Materialised into the Persistent Index

## Context

ADR-045 derives recency from git on demand — one `git log` subprocess per
file, never stored — and records its own scale caveat: corpora are small,
so per-file subprocess cost is accepted. At scale that assumption fails
concretely: every search annotates each match with recency, so a
hundred-match search forks a hundred git processes, and artifact
provenance walks one `git show` per commit that ever touched the file.
Process-spawn latency dominates the warm read path that ADR-100's index
otherwise makes query-bound.

Recency depends on git state, not file bytes: an amend or rebase changes
the answer without changing any artifact's bytes. Any stored recency must
therefore be invalidated by git head, not by the content manifest.

## Decision

The persistent index (ADR-100) stores a last-committed timestamp per
document, and index-served surfaces read that column instead of forking
git per file. This supersedes ADR-045's "derived on demand, never stored"
pin for the opted-in index surfaces only.

- The stored value is exactly what the recorded per-file `git log` query
  would return for the git state the index was refreshed against; a parity
  assertion in CI compares the column against the live git answer for the
  same head.
- The recency column's invalidation key is the git head recorded in the
  index manifest. A refresh against a moved head updates recency for the
  paths git reports changed between the indexed head and the new head —
  one subprocess per refresh, not one per match.
- Frontmatter remains free of dates (ADR-045's motivating rule is
  unchanged); the column lives in the disposable index, never in the
  artifact files.
- Surfaces that do not opt into the index keep ADR-045 behavior
  byte-for-byte, including uncommitted-file semantics: a file with no
  committed history reports no recency, stored or live.
- Deep provenance (full status history for a single artifact) stays lazy
  and on demand; only the hot annotate-per-match path reads the column.

## Consequences

### Positive

- Search annotation cost stops scaling with match count times process
  spawn: the warm path reads a stored column.
- One git subprocess per refresh replaces one per match per query.

### Negative

- Recency freshness on index surfaces is bound to the refresh cadence: a
  commit made after the last refresh is invisible until the next one. The
  parity test and the git-head key bound the staleness to that window.
- A second representation of a git-derived fact exists while an index is
  open; it is disposable with the index and never authoritative.

## Status

Accepted

## Category

Technical

## Alternatives Considered

### Keep forking git per match and batch the calls

Batching (one `git log --name-only` walk per query) removes the per-match
spawn but still pays a repository-history walk on every query, and the
cost grows with history length, not query size. Rejected for the hot path;
the same walk is the right primitive for the refresh instead.

### Store recency in frontmatter

ADR-045 already rejected this: it turns a derived fact into hand-edited
state that drifts. Unchanged.

## Relationship to Other Decisions

- ADR-045 (RAC-KV2E5B1122YN): superseded for index-served surfaces only;
  its rule against storing dates in artifact files is reaffirmed.
- ADR-100 (RAC-KWS8TRXGQWHC): the index this column lives in; shares its
  disposability, schema versioning, and parity gate.
- ADR-043 (RAC-KTYZVKZQWD98): the git seam stays isolated in the revisions
  module; the refresh walk goes through it.

## Related Roadmaps

- single-node-scale
