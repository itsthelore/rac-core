---
schema_version: 1
id: RAC-KTW0M81E7TRA
type: decision
---
# ADR-032: Guide Stateless Reads

## Status

Accepted

## Category

Technical

## Context

Guide is a long-lived process: a client spawns it once and issues tool calls
across an agent session that may last hours. The repository changes during
that session — most importantly, by the very agent calling the tools.

That creates a freshness problem no short-lived CLI invocation has. A cache
that survives repository changes serves the agent stale artifacts; an agent
acting on a stale decision is precisely the failure mode Guide exists to
prevent. A wrong answer is strictly worse than a slow one.

Explorer faces the same problem interactively and solves it with explicit
reload and file-watching. Guide has no user watching a screen — every answer
must simply be correct.

At current corpus scale (hundreds of artifacts), a full repository read is
milliseconds. The single-walk corpus snapshot (`collect_corpus`, v0.8.0)
exists as the optimization seam if scale ever demands one.

## Decision

Every Guide tool call re-reads the repository from disk.

- No persistent cache, no file watcher, no session state in the server.
- Determinism is the contract: identical repository bytes and identical tool
  input produce identical tool output, regardless of call history.
- Correctness over speed: per-call latency is accepted at current scale and
  optimized only when a real user reports it, behind the corpus-snapshot
  seam, without breaking the determinism contract.

## Consequences

### Positive

- The agent can never act on stale repository state.
- The server holds no state to invalidate, migrate, or debug.
- Determinism makes tool output contract-testable byte-for-byte.
- Each tool call is independently reproducible.

### Negative

- Every call pays a full repository read.
- Large corpora will eventually make per-call latency noticeable.

### Risks

- Latency on a large corpus degrades the agent experience before anyone
  reports it. Mitigation: the review trigger below names a concrete scale;
  the optimization seam (corpus snapshot reuse keyed on repository state)
  is identified in advance.
- A future contributor adds an innocent-looking cache. Mitigation: the
  determinism contract is pinned by tests that interleave repository edits
  with tool calls.

## Alternatives Considered

### Modification-time cache

Cache parsed corpus keyed on file mtimes, invalidating on change.

#### Advantages

- Near-zero cost for repeated calls on an unchanged repository.

#### Disadvantages

- mtime granularity and editor behaviours make invalidation unreliable —
  exactly the silent-staleness failure Guide cannot afford.
- Cache state makes responses depend on call history.

### Index at startup

Load the corpus once when the server starts.

#### Advantages

- Simplest possible fast path.

#### Disadvantages

- The agent's own edits become invisible for the rest of the session — the
  worst version of staleness.

### File watcher

Watch the repository and refresh on change, as Explorer does.

#### Advantages

- Fresh and fast in steady state.

#### Disadvantages

- A background thread, platform-specific watch APIs, and race windows
  between change and refresh — complexity v1 does not need for
  milliseconds of saving.

Re-read per call is selected.

## Relationship to Other Decisions

- ADR-011 (file-first pipeline): files on disk are the only input; this
  decision keeps them the only state.
- ADR-013 (Git as the state store): the repository is the source of truth;
  the server holds no shadow copy.
- ADR-031: the services this decision calls per-request are consumed
  in-process, so the re-read cost is a directory walk, not a process spawn.

## Success Measures

- Contract tests that edit the repository between tool calls observe the
  change in the next response.
- No bug report involves a stale Guide answer.
- Per-call latency remains agent-tolerable on the dogfood corpus.

## Review Date

Review when measured per-call latency on a 1000-artifact corpus exceeds what
an interactive agent session tolerates, or when a real user reports Guide
latency.

## Related Requirements

- rac-agent-context-guide

## Related Roadmaps

- v0.10.0-guide-foundation
