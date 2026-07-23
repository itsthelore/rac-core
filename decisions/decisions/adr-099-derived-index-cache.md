---
schema_version: 1
id: RAC-KWMZ3MR9DZ09
type: decision
---
# ADR-099: Derived-Index Cache

## Status

Accepted

## Category

Technical

## Context

Every read rebuilds the same expensive derived structures from disk: the
repository index, the resolved relationship graph, and the tokenised field
vectors BM25 scores over. ADR-032 chose that re-read-per-call model
deliberately — correctness over speed — and recorded its own review trigger:
"optimized only when a real user reports it, behind the corpus-snapshot seam,
without breaking the determinism contract," with a concrete threshold ("a
1000-artifact corpus" / "a real user reports Guide latency"). The
`lore-at-team-scale` rollout is that report: an organisation-scale corpus where
per-call re-tokenisation and re-indexing cost real latency.

ADR-080 already anticipated the answer and deferred it: "a *persistent derived
index* may be warranted at scale, but it is a rebuildable cache behind ADR-032's
snapshot seam … not a database and not authoritative." What is missing is the
recorded contract that lets such a cache exist without eroding ADR-032's
determinism-and-freshness guarantee — and the deliberate revision of ADR-032's
"no persistent cache, no session state in the server" pin, which a cache on the
serving path plainly touches. ADR-032 lists the failure mode to avoid by name: a
modification-time cache whose invalidation is unreliable, serving silent
staleness. The cache must be invalidated on content, not clocks.

## Decision

RAC gains an optional, content-addressed **derived-index cache** behind the
corpus-snapshot seam, and ADR-032's "no persistent cache on the serving path"
pin is revised — by this decision, for everyone — to permit it under strict
conditions.

- **Content-addressed, never clock- or event-addressed.** The cache is keyed on
  a corpus-level content hash that extends the per-file `content_hash` primitive:
  the sorted `(repository-relative path, per-file digest)` pairs hashed together.
  Any byte change to any artifact — or any add, remove, or rename — changes the
  key and forces a rebuild. This is precisely the invalidation ADR-032's
  rejected mtime cache lacked; there is no time- or event-based invalidation.

- **Freshness holds on the serving path.** The key is recomputed on every call,
  so every call still detects any corpus change since the previous one (ADR-032's
  contract). Derived structures are reused only under an unchanged key; the agent
  can never observe stale state. Re-hashing per call is cheap relative to the
  parse, tokenise, and index work it guards.

- **Byte-parity is the coherency guarantee.** With the cache enabled, every CLI
  and MCP output is byte-identical to the uncached path for any corpus state —
  the structures are serialised and rehydrated losslessly and every consumer
  produces identical output whether a structure came from cache or fresh compute.
  This is asserted over golden fixtures in CI, cache-on versus cache-off.

- **Disposable, never authoritative.** The files in git are the source of truth
  (ADR-080); the cache is a rebuildable index. Deleting the cache directory — or
  a corrupt, unreadable, or wrong-version cache file — costs only latency: the
  reader falls back to a fresh build. No daemon, no lockfile protocol, no
  datastore semantics. The cache writes only to its own disposable directory
  (`$XDG_CACHE_HOME/rac/derived`, `RAC_CACHE_DIR` overriding), never to the
  corpus.

- **Opt-in, off by default.** The default serving path is unchanged
  (re-read-per-call, ADR-032); the cache is enabled explicitly (`rac mcp
  --cache`). This keeps cache-on-versus-cache-off the byte-parity test toggle and
  leaves the zero-state posture exactly as before.

## Consequences

### Positive

- Per-call work stops scaling with corpus size once warm: an unchanged corpus
  skips re-tokenisation and re-indexing, so latency stays agent-tolerable at
  organisation scale.
- The ADR-032 review clause is answered on the record, and its "no persistent
  cache" pin is revised by decision, not by an innocent-looking cache slipped in
  against the determinism tests.
- No new datastore: the only moving parts remain a git checkout, a stateless
  reader, and a disposable derived index (ADR-080).

### Negative

- A second representation of the derived structures exists on disk; its
  correctness rests on the content hash being exact and the serialisation being
  lossless — both asserted in CI, but both now things to maintain.
- The first call on a changed corpus pays the full rebuild plus the cache write;
  the win is on repeated reads of an unchanged corpus.

### Risks

- Wrong invalidation serves stale results. Mitigation: pure content addressing
  (any byte change changes the key) plus the byte-parity assertion — staleness
  cannot survive both, and there is no mtime or event path to get wrong.
- The cache drifts into a datastore. Mitigation: disposability is pinned — it is
  never read as authoritative, deleting it changes only latency, and it holds no
  state git does not.
- A serialisation change silently rehydrates a stale shape. Mitigation: a pinned
  cache schema version; a mismatch is treated as a miss and rebuilt.

## Alternatives Considered

### Keep re-read-per-call unconditionally (ADR-032 unchanged)

Leave the serving path rebuilding everything each call.

#### Disadvantages

- Ignores ADR-032's own review trigger, which has now fired; per-call latency on
  a large corpus degrades the agent experience the tool exists to serve.

### A modification-time (mtime) cache

Invalidate cached structures when file mtimes change.

#### Disadvantages

- ADR-032 already rejected this: mtime granularity and editor behaviours make
  invalidation unreliable — the silent-staleness failure the tool cannot afford.
  Content addressing is the correct key.

### A central database as a shared derived store

Stand up a database that holds the derived index for the team.

#### Disadvantages

- ADR-080's red line: a second authoritative representation to reconcile with
  `main`, losing git's diffability and offline operation. The cache is a
  disposable rebuildable index, not a store.

A content-addressed, disposable, opt-in cache with byte-parity to the uncached
path is selected.

## Relationship to Other Decisions

- ADR-032: this decision answers its recorded review clause and revises its "no
  persistent cache on the serving path" pin, preserving its determinism and
  freshness contract.
- ADR-080: the cache is the "rebuildable derived index behind the snapshot seam"
  that ADR-080 deferred — disposable, never authoritative.
- ADR-002: content addressing and lossless serialisation keep output
  deterministic and byte-identical across runs and platforms.
- ADR-066: no embeddings or semantic structures are cached — only the
  deterministic derived index, graph, and token vectors.
- ADR-007: the cache is additive and off by default; no existing contract field
  changes and the uncached path is byte-unchanged.

## Related Requirements

- rac-derived-index-cache

## Related Roadmaps

- lore-at-team-scale
