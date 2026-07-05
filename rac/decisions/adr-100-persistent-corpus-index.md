---
schema_version: 1
id: RAC-KWS8TRXGQWHC
type: decision
---
# ADR-100: Persistent Corpus Index with Changeset Invalidation

## Context

Every read path is corpus-bound per call. ADR-032 pinned re-read-per-call;
ADR-099 answered its review trigger with an opt-in derived cache whose key
still re-reads every file's bytes on every call and whose single JSON blob
rebuilds wholesale on any change. The scale evidence is measured: any CLI
command costs about a millisecond per artifact per invocation (121 seconds
at one hundred thousand artifacts, timing out past a million), warm cached
search inverts at one hundred thousand (the per-call rehash plus blob
rehydration exceed the work saved), and an incremental thousand-file change
costs the same as a full pass at every corpus size. The single-node-scale
roadmap requires warm retrieval flat across the corpus-size curve,
incremental work bound by changeset size, and only the cold build scaling
with corpus size.

ADR-099's own red lines — content addressing over clocks, disposability,
byte-parity, no external services — remain correct. What fails at scale is
the granularity: whole-corpus keys force whole-corpus reads and rebuilds.

## Decision

RAC gains an opt-in **persistent corpus index**: an on-disk, memory-mapped
index directory that is built once, refreshed by changeset, and served
warm. This decision supersedes ADR-099's whole-corpus cache granularity and
further revises ADR-032's per-call freshness mechanism for the surfaces
that opt in.

- **Contents.** Four structures, derived only from artifact bytes and the
  relationship registry: an inverted term index (sorted term dictionary
  with prefix-range lookup, per-field postings with term frequencies, and
  stored aggregates for document frequency and mean field length); a
  compact graph adjacency in both directions with materialised inbound
  counts; a document store (path, id, type, title, aliases, field lengths,
  last-committed timestamp); and a per-file manifest (content hash, size,
  mtime, indexed git head).
- **Analyzer parity is the contract.** The index tokenises with the exact
  ADR-037 tokenizer, matches by equality-or-prefix with AND semantics, and
  scores with the recorded ranking from stored aggregates. Index-served
  output is byte-identical to the fresh walk-and-parse path for any corpus
  state; parity is asserted in CI over golden fixtures, index-on versus
  index-off.
- **Changeset invalidation, bytes decide.** Refresh enumerates files with
  stat-only calls, selects candidates whose size or mtime differ from the
  manifest (plus path-set adds and removes), reads and hashes only the
  candidates, and re-indexes only files whose content hash actually
  changed. Mtime is a hint to avoid reading unchanged bytes, never an
  authority: a candidate is confirmed or dismissed by its byte hash alone.
  A strict verify mode re-hashes everything, recovering ADR-032's per-call
  byte guarantee when correctness must trump latency.
- **Freshness in the long-lived server.** The opt-in serving mode holds the
  index open and watches the corpus root with native filesystem events
  (directory-level watches; no polling daemon, no external service).
  Events mark paths dirty; the next call splices exactly the dirty
  changeset before serving. Where watches are unavailable, the server
  falls back to the stat-scan refresh per call. This deliberately
  supersedes ADR-032's "no file watcher" pin for the opted-in server only;
  the recorded residual race is the interval between a write and its event
  delivery, and the fallback restores stat-scan semantics.
- **Disposable, never authoritative.** The files in git remain the source
  of truth. The index lives in its own directory under the ADR-099 cache
  root, carries a pinned schema version, and any corruption, version
  mismatch, or deletion degrades to a full rebuild — a latency cost, never
  an answer change.
- **Opt-in, defaults unchanged.** The default CLI and MCP serving paths
  are byte-for-byte unchanged, including ADR-099's cache flag behavior.
  The index is enabled explicitly; index-aware wiring is additive.
  Existing tests keep passing unmodified; the new invariants are pinned by
  new tests.

## Consequences

### Positive

- Warm queries touch postings for their terms and score only candidate
  documents: latency is bound by query selectivity, not corpus size.
- Incremental work is bound by the changeset: detection is stat-only, and
  re-indexing splices only files whose bytes changed.
- Exact lookups and searches stop paying the full relationship-graph
  build; inbound counts are a stored column.
- The cold build remains the only corpus-bound path, parallel across
  cores, and is paid once.

### Negative

- A second on-disk representation with a real format: schema versioning,
  splice correctness, and aggregate maintenance are now code to maintain,
  guarded by the byte-parity gate.
- The watcher mode narrows ADR-032's freshness guarantee from
  every-call-reads-bytes to event-driven-plus-confirmation; the race
  window and the strict-verify escape hatch are recorded here.
- A byte edit that preserves both size and mtime is invisible to the stat
  hint outside watcher mode; the strict verify mode exists for exactly
  this, and the byte-hash authority bounds the failure to a missed
  refresh, never a wrong merge of stale and fresh state.

## Status

Accepted

## Category

Technical

## Alternatives Considered

### Keep ADR-099's whole-corpus cache and tune it

Compression or faster hashing reduce constants, not the complexity class:
the warm path still reads every byte of the corpus per call and any change
still rebuilds everything. Measured to invert at one hundred thousand
artifacts. Rejected.

### An external index service or embedded database

Rejected on the recorded red lines: single node, no external services, no
second authority. The index is a disposable derived structure in a cache
directory, not a datastore.

### Sharding the corpus

Distribution is explicitly out of scope for the single-node-scale roadmap;
the mandate is single-node efficiency. Rejected.

## Relationship to Other Decisions

- ADR-099 (RAC-KWMZ3MR9DZ09): superseded in granularity — content
  addressing, disposability, byte-parity, and opt-in defaults are kept;
  whole-corpus keys, per-call full rehash, and the single JSON blob are
  replaced by the manifest, changeset splicing, and the mapped format.
- ADR-032 (RAC-KTW0M81E7TRA): its freshness mechanism is revised for the
  opted-in server (events plus byte confirmation, strict verify escape);
  its determinism contract — identical bytes, identical output — is
  unchanged and enforced by the parity gate.
- ADR-037 and ADR-038 (RAC-KTXTAF6ZKDK8, RAC-KTXTAG63E89H): unchanged; the
  tokenizer and lexical tiers are the index's analyzer contract. No
  embeddings, no semantic scoring.
- ADR-059 (RAC-KV4ZAGWPAA6X): unchanged; the parser instance is reused at
  index build time.

## Related Roadmaps

- single-node-scale
