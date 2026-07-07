---
schema_version: 1
id: RAC-KWYEHJXR0M3G
type: decision
---
# ADR-110: One-Shot `rac find --cache` Reuses the Persistent Store

## Context

The persistent memory-mapped index store (ADR-104) makes candidate discovery
scale-invariant, but it has been reachable only through the long-lived MCP
server (`rac mcp --cache`), which holds the store open and watches the corpus
with filesystem events (ADR-105). The benchmark that drives candidate discovery
invokes `rac find` as a one-shot CLI process per query, and that path has no
store reuse: `cmd_find` walks, parses, and rebuilds the relationship graph on
every invocation — exactly the entry-point cost the store exists to remove.

A one-shot process cannot hold the store open or use the event watcher, but the
store is content-addressed on disk and shared across processes, so a first
invocation can build and write it and every later invocation against the
unchanged corpus can serve from it. The seam already exists:
`DerivedIndexCache.load_or_build` opens the store on a warm hit and builds
fresh + writes it on a cold miss, and the serving paths already branch on the
returned read-model type.

## Decision

`rac find` gains an opt-in `--cache` flag that serves the query from the
persistent index store via `DerivedIndexCache.load_or_build`, byte-identical to
the uncached walk.

- **Opt-in, default unchanged.** `--cache` is off by default; without it
  `rac find` walks and parses exactly as before (ADR-104's opt-in posture, the
  same shape as `rac mcp --cache` and `rac validate --cache`). The store is
  disposable and content-addressed under `$XDG_CACHE_HOME` (`RAC_CACHE_DIR`
  overrides); deleting it costs only latency.
- **Byte-parity.** The cached result is the same `SearchResult` the walk
  produces — search, the `--decisions` live query, `--type`, the `--tag` facet,
  and `--explain` evidence are all served through the read-model exactly as
  `mcp/server.py` serves them (a `ReadModelView` postings fast path on a warm
  hit, `search_index` / `find_decisions_in` over a fresh `DerivedIndex` on a
  cold miss). Recency annotation is unchanged — it is joined per-match from git
  after ranking (ADR-045), independent of how the matches were produced.
- **Cross-process reuse.** The first `--cache` invocation against a corpus
  builds fresh and writes the store; every later one-shot process against the
  unchanged corpus serves from the memory-mapped store with no walk, parse, or
  graph rebuild. This is the aggregate win for a benchmark or agent that issues
  many one-shot queries against a stable corpus.

### The two honest costs

- **The O(n) hash floor stands.** `load_or_build` recomputes the corpus content
  hash on every call to detect change before reusing anything, reading every
  file's bytes. A warm one-shot therefore still pays O(n) *hashing* — it skips
  the far more expensive parse, derive, and re-tokenisation, not the hash. Only
  the long-lived server escapes the hash via the event watcher (ADR-105); a
  one-shot cannot, by construction.
- **A cold run is slower than the plain walk.** The miss path forks workers and
  writes the store, heavier than the current single-process build. A genuine
  single query with no follow-up is net-negative; the fork and write only
  amortise across later warm invocations. This is why `--cache` is opt-in rather
  than the default.

## Consequences

### Positive

- One-shot `rac find` becomes bound by query selectivity, not corpus size, on
  the warm path — the entry-point fix reaches the CLI, not only the server.
- No new machinery: the flag is a thin consumer of the existing store, cache,
  and read-model, and inherits their byte-parity guarantees.

### Negative

- A second reuse surface for the store means the store's freshness and
  disposability contracts now matter to a short-lived process too; the O(n) hash
  floor and the cold-run penalty are real and recorded here so the flag is used
  where it pays (repeated queries against a stable corpus), not blindly.

## Status

Accepted

## Category

Technical

## Alternatives Considered

### Make `--cache` the default for `rac find`

Default reuse would speed a benchmark's plain `rac find` without a harness
change, but it slows a genuine single one-shot (the cold fork + write) and
amends ADR-104's opt-in-defaults-unchanged posture. Rejected in favour of an
opt-in flag; the default walk path stays byte-for-byte unchanged.

### Share the server's event-watched freshness with the CLI

The watcher (ADR-105) that lets the server skip the per-call hash needs a
persistent process to hold the state and receive events. A one-shot CLI has no
such process, so it cannot avoid the hash. Rejected as inapplicable; the O(n)
hash floor is accepted and documented instead.

### A per-invocation stat-only changeset scan

Detecting change by stat instead of hashing the bytes would lower the floor, but
it is still O(files) and is the same unshipped residual the single-node-scale
work records; not in scope for this flag.

## Relationship to Other Decisions

- ADR-104 (RAC-KWS7QCT10Q5A): extends the persistent store to a one-shot CLI
  surface; inherits its content-addressing, disposability, and byte-parity.
- ADR-099 (RAC-KWMZ3MR9DZ09): the derived cache whose `load_or_build` seam the
  flag consumes directly.
- ADR-105 (RAC-KWSDFYW7PCW6): the event-watched freshness a one-shot cannot use,
  which is why the O(n) hash floor stands.
- ADR-106 (RAC-KWSH9J2S7QB1): the precedent — `rac validate --cache` introduced
  opt-in store reuse to a CLI command as its own decision.
- ADR-031 (RAC-KTW0M81B0GBB): the CLI and the MCP tool serve the same result
  from the same read-model.
- ADR-045 (RAC-KV2E5B1122YN): recency stays a git-per-match join after ranking,
  unaffected by the search path.

## Related Roadmaps

- candidate-discovery
