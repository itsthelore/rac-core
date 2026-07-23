---
schema_version: 1
id: RAC-KV4ZAGWPAA6X
type: decision
tags: [performance, parsing, engine]
---
# ADR-059: Reuse a Single Markdown Parser Instance

## Context

Parsing is the RAC engine's dominant cost: every corpus walk, validation,
portfolio summary, relationship analysis, and MCP tool call flows through
`rac.core.markdown.parse`. Profiling the parse path and the four MCP tool
bodies against a representative corpus showed that roughly half of parse time
was spent *constructing* the `markdown-it-py` parser, not parsing: each call
built a fresh `MarkdownIt("commonmark")`, which recompiles the linkify regexes
and introspects its rule chains on every instantiation.

A `MarkdownIt` parser is stateless across `parse(src)` calls — each call builds
its own parse state — so the per-call construction was pure waste. The question
was whether to cache anything, given that ADR-032 deliberately forbids the MCP
server from caching repository reads or results across tool calls.

## Decision

Construct one module-level `MarkdownIt("commonmark")` in
`rac.core.markdown` and reuse it for every `parse` call.

This caches a stateless parser *configuration* object, not corpus data,
parse results, or any repository read. It is therefore orthogonal to ADR-032,
which governs caching of repository state across MCP calls: identical input
still produces byte-identical output, and the MCP server still performs a fresh
corpus walk per tool call.

## Consequences

Positive: the engine's hottest path is roughly halved (measured ~2x faster per
parse and 40-57% lower wall time on the profiled MCP tool paths), with no change
to observable behavior. Determinism is preserved — token output and the parsed
`Product` were verified byte-identical to the previous per-call construction
across the entire fixture corpus before adoption.

Trade-off: a single shared instance assumes RAC parses on one thread at a time,
which holds today (CLI, MCP stdio server, and the TUI all parse serially). If
parsing ever moves to multiple threads, the shared instance must be re-verified
as safe (markdown-it-py builds fresh parse state per call, so this is expected
to hold, but it is no longer a non-question).

## Status

Accepted

## Category

Architecture

## Alternatives Considered

- **Keep constructing a parser per call.** Simplest and obviously
  thread-isolated, but pays the full construction cost on the engine's hottest
  path for no behavioral benefit.
- **Cache parse *results* (the `Product`) per file.** Rejected: this caches
  repository-derived data, which conflicts with ADR-032's no-cache stance for
  the MCP surface and introduces staleness and invalidation concerns the engine
  deliberately avoids. Reusing the parser captures the win without caching any
  derived state.

## Related Decisions

- adr-032
- adr-047

## Related Roadmaps

- v0.18.0-engine-simplification
