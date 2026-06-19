---
schema_version: 1
id: RAC-KV6KFP1QDRB0
type: requirement
tags: [internal, performance, determinism, hashing]
---
# Requirement: Idempotent Content-Hash Processing

## Status

Accepted

Classification: `[internal]`. Scoped to the v0.23.0 hardening release (WS8,
core only). Implemented as `CorpusCache` on the `collect_corpus` seam
(`core/corpus.py`): a per-invocation, in-memory, content-hash-keyed snapshot
reuse, with `content_hash` over full on-disk source bytes. `rac doctor` — the
multi-phase command — shares one cache across its validation, relationship, and
degree/injection passes, so each artifact is parsed once per run; the additive
`cache` parameter on `validate_directory` / `validate_relationships` is the seam
it threads through. The MCP serving path is deliberately untouched and re-reads
per call (REQ-004); single-phase commands (`rac validate`, `rac eval`) gain the
parameter but see no within-run reuse, which is correct.

## Problem

Lore's buyers are teams with years of accumulated decisions, not a tiny repo on
day one. The inner loop and CI must stay fast on an ICP-sized corpus, and the
determinism guarantee that underpins the eval benchmark (WS1) needs reinforcing:
the same input must always produce identical derived output. Today the
per-invocation corpus walk (`walk_corpus` / `collect_corpus`) reparses and
reprocesses every artifact on every run of validation — and will do the same for
the WS1 eval and WS3 doctor passes once they land — even when nothing changed.
No content hash exists in any processing path today.

This is a per-invocation optimization, not a cross-invocation one. ADR-032
already names `collect_corpus` (v0.8.0) as "the optimization seam if scale ever
demands one"; this requirement uses that seam and no other.

## Requirements

- [REQ-001] Within a single CLI invocation, RAC MUST content-hash every walked artifact so validation, the WS1 `rac eval` pass, and the WS3 `rac doctor` pass can short-circuit an artifact whose hash is unchanged from an earlier phase of the same run rather than reparsing/reprocessing it per phase; the short-circuit is an in-memory reuse keyed on the snapshot's per-artifact hash that persists no state to disk and survives no process boundary.
- [REQ-002] The hash MUST be computed over the artifact's full on-disk source bytes (front matter plus body) so any edit — whitespace or front-matter-only included — changes the hash and forces reprocessing; the hash covers source content only, never derived output and never mtime or other filesystem metadata (mtime invalidation is rejected by ADR-032).
- [REQ-003] The short-circuit MUST apply to CLI processing only and MUST NOT introduce a persistent cache into the MCP serving path, which re-reads per call (ADR-032). Derived output (validation results, the eval `metrics` object, the doctor report) MUST therefore be idempotent and byte-stable — identical source bytes produce byte-identical derived output across repeated runs regardless of run history — and the short-circuit MUST NOT alter output versus a full reprocess; it is a performance path only, and a test MUST assert the two are byte-identical.
- [REQ-004] The short-circuit MUST apply to CLI processing only and MUST NOT add any persistent cache, file watcher, or session state to the MCP serving path, which re-reads the repository from disk on every tool call (`walk_corpus` per call; ADR-032); the existing interleaved-edit contract tests pinning ADR-032 MUST continue to pass so a repository edit between tool calls is reflected in the next response.
- [REQ-005] Resumability and crash-safe incremental job machinery — partial-run resumption, two-phase persistence, and on-disk cross-invocation caches — are explicitly out of scope (T3-C, deferred); there is no long-running interruptible operation yet and cross-invocation speedups are not part of this release.

## Acceptance Criteria

- Re-running validation/eval/doctor across phases of one invocation on an
  unchanged snapshot does near-zero redundant reprocessing and is provably
  idempotent (test).
- Changing one artifact's source bytes reprocesses only that artifact; a test
  edits one artifact and asserts exactly one artifact is reprocessed.
- Derived output (validation results, eval `metrics`, doctor report) is
  byte-stable across repeated runs, and byte-identical between the short-circuit
  path and a forced full reprocess.
- A test interleaving a repository edit with MCP tool calls observes the edit in
  the next response (ADR-032 unbroken).

## Success Metrics

- CI and the inner loop stay fast on a large, realistic corpus.

## Risks

- A hash short-circuit could mask a real change. Mitigation: hash over full
  on-disk source bytes (REQ-002); cover with a test that changes one artifact
  and asserts only it reprocesses, and a test asserting short-circuit output is
  byte-identical to a full reprocess.
- A contributor extends the hash into the MCP path as an innocent-looking cache,
  reintroducing staleness. Mitigation: REQ-004 plus the ADR-032 interleaved-edit
  tests fail if the serving path stops re-reading per call.

## Assumptions

- The source of truth stays in markdown/git; derived data is always rebuildable,
  so an absent or stale in-memory hash only costs a reprocess, never correctness.
- `collect_corpus` is the single seam the short-circuit attaches to (ADR-032);
  consumers (WS1 eval, WS3 doctor) read the hashed snapshot rather than
  re-walking.

## Related Decisions

- adr-032
- adr-011
- adr-013

## Related Requirements

- rac-grounding-eval-benchmark

## Related Roadmaps

- v0.23.0-hardening
