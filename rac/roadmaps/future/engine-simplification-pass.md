---
schema_version: 1
id: RAC-KV4X5WC8D2MY
type: roadmap
---
# Engine Simplification and Optimization Pass

## Outcomes

A simpler, faster, more maintainable RAC engine, achieved without changing
any observable behavior. The pass is behavior-preserving: the full test
suite, line and branch coverage, the four MCP tool contracts, the CLI
surface, output determinism, and schema-validation results are all held
constant. Net lines removed is tracked as a scoreboard, never the objective —
a change is accepted only when it makes the design genuinely simpler or
faster, and rejected if it harms readability, coverage, determinism, types,
or error handling.

The dominant cost in the engine is Markdown parsing, and roughly half of
that cost is parser *construction* rather than parsing: a fresh
`markdown-it-py` parser is built (and its linkify regexes recompiled) on
every `core.markdown.parse` call. Removing that repeated construction is the
single highest-value optimization, because parsing underlies every corpus
walk, validation, portfolio summary, relationship analysis, and MCP tool
call.

## Initiatives

- **Reuse the Markdown parser.** Construct the `MarkdownIt("commonmark")`
  parser once and reuse it across `parse` calls in `core/markdown.py`. The
  parser is stateless across `parse(src)` invocations, so reuse is
  byte-identical and deterministic. This caches a parser *configuration*
  object, not corpus data or results, and so does not conflict with the MCP
  no-cache decision (ADR-032), which governs cross-call caching of repository
  reads in the server.

- **Consolidate duplicated validation logic.** Extract the title check
  (`missing-title` / `multiple-titles`) and the required-section check —
  currently copy-pasted across the per-type validators in `core/validation.py`
  — into shared helpers that read from `ArtifactSpec`, preferring existing
  data structures over new abstractions. Extract the repeated duplicate-detection
  pattern in the requirement validator into one named helper. Issue codes,
  messages, line numbers, and pass/fail outcomes are preserved exactly.

- **Reduce incidental complexity in service routing.** Collapse the
  near-identical per-type validity-stat blocks in `services/stats.py` into a
  single helper, keeping every emitted statistic and output ordering
  identical.

## Success Measures

- The full test suite passes with the same or better result before and
  after, and line and branch coverage do not decrease.
- Parser construction no longer appears in a profile of the parse and MCP
  hot paths; measured parse throughput improves materially.
- Cyclomatic complexity of the touched validation and stats functions falls,
  with no change to their observable behavior.
- Golden CLI output and the MCP determinism battery remain byte-identical.

## Assumptions

- `markdown-it-py` parsers are safe to reuse across `parse` calls (the
  documented usage); each call constructs its own parse state.
- The corpus gates (`rac validate`, `rac relationships --validate`,
  `rac review`) and the existing pytest batteries are the authority on
  behavior preservation.

## Risks

- A shared parser instance could in principle leak state between calls;
  mitigated by verifying byte-identical tokens and `Product` output across
  the fixture corpus before adopting the change.
- Helper extraction could subtly alter an issue code, message, or ordering;
  mitigated by the golden-output battery and per-change test and coverage
  runs, reverting any change that regresses.

## Related Decisions

- ADR-047
- ADR-032
