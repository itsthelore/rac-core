---
schema_version: 1
id: RAC-KVSTYENH8X0S
type: roadmap
---
# RAC — Lore at Team Scale (Future)

## Status

Planned

Unscheduled — captured as future intent for teams of 50+ developers, not yet on
a release. Nothing here has hit its trigger; it graduates out of `future/` into a
versioned series when one does.

## Context

Lore is built as files-in-git: one canonical corpus on `main`, served read-only
and re-read per call (ADR-032), with no database (ADR-080). That model is correct
and keeps consistency where git already provides it. Two questions appear only at
team scale, and both have answers that are *servers and caches, never a database*:

- **Consistency.** In the default topology each developer runs a local `rac mcp`
  against their own checkout, so two developers can be on different commits until
  they pull. A team may want every agent to call one always-current source of
  truth instead of individual copies.
- **Performance.** As a corpus grows into the thousands of artifacts — plausible
  once large note-tool vaults are imported — re-reading and re-indexing on every
  call starts to cost real latency, which ADR-032 explicitly defers optimising
  "behind the corpus-snapshot seam" until a real user reports it.

This item records the intent for both, on the no-database terms ADR-080 sets.

## Outcomes

- A team can point every developer's agent at one always-current endpoint that
  reflects `main`, so reads come from a single source of truth rather than
  individual checkouts that lag.
- Per-call latency stays acceptable as the corpus grows large, without changing
  the determinism or freshness contract.
- No database is introduced: git stays the system of record (ADR-080).

## Initiatives

### Initiative 1 — Centralised shared MCP server (HTTP transport)

`rac mcp` gains an HTTP / streamable transport so a single instance, fronting an
auto-updated `main` checkout, serves the whole team from one endpoint. It stays
read-only and stateless per call (ADR-032); a merge webhook (or periodic pull)
keeps the checkout current, so every agent reads `main`. This is the single
source of truth everyone calls — a server, not a database (ADR-080). Today
`rac mcp` is stdio-only, so this is the load-bearing build.

### Initiative 2 — Derived-index persistence (behind the ADR-032 seam)

A content-addressed, rebuild-on-change index cache so per-call work stops scaling
with corpus size: the relationship graph and search index are derived once and
reused while the corpus content-hash is unchanged, and invalidated on any change
so freshness and determinism hold (ADR-032). It is a rebuildable cache, not a
store — "files are truth, the index is disposable." Likely triggers: corpus-wide
BM25 document-frequency statistics from the relevance-ranking work, and large
note-tool vault imports.

### Initiative 3 — Operate-it documentation

A deployment recipe for the shared server (container, the keep-current webhook,
read-only posture, no secrets) and guidance on when a team needs it versus the
local-clone default — so the central-source-of-truth option is reproducible.

## Constraints

- No database as a system of record; files-in-git stay canonical (ADR-080).
- Read-only and stateless per call; the determinism and freshness contract of
  ADR-032 holds for both the shared server and the cache.
- The cache is a rebuildable derived index, never authoritative; any corpus change
  invalidates it.

## Non-Goals

- A database, vector store, or any persistent system of record other than git.
- Write-through the server: knowledge still changes only by PR to `main`
  (ADR-065).
- Embeddings or semantic indexing (ADR-066).

## Success Measures

- With the shared server, every team agent returns the same answer for the same
  query at a given moment, because all read one `main`-backed checkout.
- With the cache, repeated reads of an unchanged large corpus avoid re-indexing,
  and a single change invalidates and rebuilds it; answers stay byte-identical to
  the uncached path.
- No new datastore appears in the deployment: the only moving parts are a git
  checkout and a stateless reader.

## Assumptions

- Teams that want a single live endpoint are a real segment; the local-clone
  default remains correct for everyone else.
- Per-call recompute is fine at current scale and becomes a latency concern only
  for large corpora — so persistence is a deferred optimisation, not a day-one
  need (ADR-032).

## Risks

- A shared server drifts from `main` if the keep-current step fails. Mitigation:
  the server re-reads per call (ADR-032) and the pull is driven by merge events,
  so staleness is bounded and observable.
- A persistent cache serves stale results if invalidation is wrong. Mitigation:
  content-addressed keying — any byte change to the corpus changes the key and
  forces a rebuild — keeping the determinism contract intact.

## Related Decisions

- adr-080
- adr-032
- adr-001
- adr-066
- adr-073
