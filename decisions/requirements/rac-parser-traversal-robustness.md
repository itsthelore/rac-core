---
schema_version: 1
id: RAC-KV6KFJ7BERWG
type: requirement
tags: [internal, robustness, parser, traversal, mcp]
---
# Requirement: Parser and Bounded-Traversal Robustness

## Status

Accepted

Classification: `[internal]` — invisible, but the server must never crash in
front of a partner. Scoped to the v0.23.0 hardening release (WS4).

## Problem

The MCP server sits in an agent's critical path. A malformed artifact, an
oversized field, or a pathological relationship graph must never crash, hang, or
exhaust memory. Red-teaming the current code (`src/rac/core/markdown.py`,
`src/rac/core/frontmatter.py`, `src/rac/services/relationships.py`,
`src/rac/mcp/server.py`, `src/rac/mcp/budget.py`) surfaced concrete gaps:

- **No input-size cap anywhere.** `parse_file` does `fh.read()` on the whole
  file and `split_frontmatter` does `text.split("\n")` over it; a multi-gigabyte
  `.md` file (or one with millions of lines) is read fully into memory before any
  guard runs. The corpus walk (`walk_corpus`) parses every discovered file with
  no per-file ceiling.
- **No front-matter size or shape cap.** `parse_frontmatter` hands the raw block
  to PyYAML's `SafeLoader`. `SafeLoader` blocks arbitrary object construction and
  the `_StrictLoader` subclass rejects duplicate keys, but neither caps a huge
  scalar, a deeply nested mapping/sequence, or an alias-expansion ("billion
  laughs") blow-up — those still allocate before validation sees them.
- **Body-text fields are uncapped.** Parsed section bodies, `search_sections`,
  and requirement lines accumulate every line of the body with no per-field
  ceiling, so an oversized field survives into the served `Product`.
- **ReDoS surface is small but unaudited.** The parser/validator regexes
  (`_BRACKET_RE`, `_CANONICAL_ID_RE`, `ID_RE`, `_AMBIGUOUS_RE`, `_NORMATIVE_RE`,
  `_QUARTER_RE`) are anchored literal-alternation patterns with no nested
  quantifiers, so none is currently catastrophic — but this release must *assert*
  that property so a future pattern (e.g. a doctor heuristic) cannot regress it.
- **`get_related` ordering is path-based, not the budget's documented order.**
  `_incoming_from` sorts `incoming` by `(path, section)` and `_outgoing_from`
  preserves declaration order; the ADR-033 budget then truncates whole `incoming`
  entries from the tail. Output is bounded and deterministic, but the kept set is
  ordered by filesystem path rather than the (relationship type, ascending id)
  order REQ-004 requires, so truncation can drop edges in a surprising order.
- **High-fan-out / cyclic graphs are bounded only by the response budget.**
  `relationships_from_corpus` is a single pass (no recursion, so no cycle hazard
  for 1-hop), but a hub artifact with thousands of incoming edges builds the full
  `incoming` list in memory before the budget truncates it — bounded output, but
  not bounded work.

While `get_related` is one-hop and the ADR-033 response budget bounds its
*output*, none of the above is asserted against adversarial input, and input
work is not yet bounded ahead of that budget.

## Requirements

- [REQ-001] The parser MUST enforce a per-file byte cap in `parse_file` before the file is read fully into memory (size-check the path, then read at most the cap), and the in-memory `parse` entrypoint MUST reject input longer than the same cap before tokenizing; the cap is a module-level constant (default 1 MiB, overridable via `RAC_MAX_FILE_BYTES`), measured in bytes so it is unicode-width-independent, and over-cap input is reported as a structured oversize issue, never an exception.
- [REQ-002] `parse_frontmatter` MUST cap the raw front-matter block before it reaches PyYAML — a byte cap (default 64 KiB) plus bounded nesting depth and rejection of alias expansion ("billion laughs") — so deeply nested or alias-bombed YAML is reported as a structured `malformed-frontmatter` issue without unbounded allocation; the existing `SafeLoader` and duplicate-key rejection are retained and these bounds are added on top.
- [REQ-003] Each captured body field (per-section bodies, requirement lines, `search_sections`) MUST be bounded by a per-field length and total captured-line cap so a single oversized field cannot dominate the served `Product`; the field is marked truncated rather than failing the whole parse, and this parser-level cap is independent of the ADR-033 response budget.
- [REQ-004] `get_related` output MUST remain bounded by the ADR-033 response budget, with a deterministic result cap and ordering (relationship type, then ascending artifact id) and a backward-compatible truncation signal. Separately, every regex applied to artifact content (`_BRACKET_RE`, `_CANONICAL_ID_RE`, `ID_RE`, `_AMBIGUOUS_RE`, `_NORMATIVE_RE`, `_EARS_IF_RE`, `_THEN_RE`, `_QUARTER_RE`) MUST be linear-time (anchored, no nested quantifiers, no overlapping alternation) with a test asserting bounded-time termination on a pathological string; no new content-applied regex may use unbounded backtracking, and user/query input MUST stay matched by literal token comparison, never compiled as a regex.
- [REQ-005] A single malformed or oversize artifact MUST degrade gracefully — reported and skipped — and MUST NOT crash `get_artifact` / `search_artifacts` / `get_related`, abort the corpus walk, or fail CI uninformatively; the walk MUST continue past it, surfacing a structured issue that feeds WS3 `doctor` and validation.
- [REQ-006] `get_related` output MUST remain bounded by the ADR-033 response budget, with the kept set ordered before truncation by relationship type (the artifact's own spec/section order) then ascending artifact id, so tail-truncation drops the lowest-priority edges deterministically; the truncation signal stays the existing additive `truncated` / `omitted` / `hint` marker (ADR-007) and the `incoming` ordering change is additive-compatible.
- [REQ-007] `get_related` MUST bound work, not only output: incoming and outgoing edge collection MUST stop building after a per-call edge cap (default 1000) is reached, recording the overflow via the same truncation marker, so a high-fan-out hub cannot force an unbounded in-memory list before the response budget trims it.
- [REQ-008] When any cap truncates output, the kept items MUST be selected and ordered deterministically so output stays byte-stable across repeated runs on unchanged input.
- [REQ-009] The release MUST add fuzz/property tests over the parser and the serving path covering malformed YAML, oversized files and fields, alias bombs, deep nesting, unicode (invalid/partial sequences and width edge cases), and binary junk, and the harness MUST be deterministic in CI — a fixed seed, a bounded committed fixture corpus (or a seeded generator with a pinned iteration count and time budget), and no network — so a failure is reproducible from the recorded seed.
- [REQ-010] Any future multi-hop traversal MUST add explicit depth, frontier, visited-set, and work-budget caps before shipping; this release does not add multi-hop traversal and `get_related` stays 1-hop.

## Acceptance Criteria

- A file over `RAC_MAX_FILE_BYTES` and a front-matter block over its cap each
  yield a structured oversize / `malformed-frontmatter` issue and do NOT crash or
  hang `parse_file`, `get_artifact`, `search_artifacts`, or `get_related`; the
  corpus walk continues past them.
- An alias-bomb / deeply nested YAML front matter is rejected as a structured
  issue without unbounded allocation (asserted under a bounded memory/time
  budget), not raised as an uncaught exception.
- A ReDoS-style adversarial string against each content-applied regex completes
  within a bounded time assertion; a test enumerates the regexes so a new one
  cannot be added without coverage.
- `get_related` over fuzz graph fixtures — cycles, self-references, deep chains,
  and a high-fan-out hub (more incoming edges than the edge cap) — terminates
  within the edge cap and the ADR-033 budget, emits well-formed JSON with the
  `truncated` / `omitted` / `hint` marker set, and the kept `incoming` set is
  ordered by relationship type then ascending id.
- A test asserts `get_related` serialized output is byte-identical across
  repeated runs on an unchanged adversarial corpus, with no unbounded time or
  memory.
- Parser fuzz tests pass deterministically from a recorded seed / committed
  fixture corpus, with no network access.

## Success Metrics

- No input — oversized file, malformed/alias-bombed front matter, oversized
  field, or pathological graph — can hang, crash, or OOM any parse or serving
  path; every such input is reported as structured data.
- `get_related` output for any corpus is bounded by both the per-call edge cap
  and the ADR-033 character budget, and is byte-stable.

## Risks

- Over-tight caps could reject legitimately large artifacts or fan-out hubs.
  Mitigation: caps are module-level constants with safe defaults (1 MiB file,
  64 KiB front matter, 1000 edges) proven against the fixture corpus; the
  file-byte cap is overridable via `RAC_MAX_FILE_BYTES` for repos with genuinely
  large artifacts.
- Re-ordering `incoming` by (type, id) changes the serialized order versus the
  current (path, section) order. Mitigation: the change is additive-compatible
  per ADR-007 (field shape unchanged, only ordering) and is pinned by a contract
  test; no client depends on the prior order.

## Assumptions

- The ADR-033 budget already bounds response *size*; this release proves that
  guarantee against adversarial input and adds the missing *work* bounds (input
  size, field size, edge count) ahead of it, rather than re-architecting serving.
- The parser stays single-threaded (ADR-059's shared parser instance holds), so
  per-call caps need no locking.

## Related Decisions

- adr-033
- adr-055
- adr-032

## Related Requirements

- rac-doctor-diagnostic-validator

## Related Roadmaps

- v0.23.0-hardening
