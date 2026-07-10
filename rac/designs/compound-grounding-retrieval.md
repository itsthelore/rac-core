---
schema_version: 1
id: RAC-KX6WEVMJAJB9
type: design
tags: [retrieval, grounding, mcp, cli, determinism, benchmark]
---
# Grounding Retrieval Surface

## Context

ADR-113 decides that RAC owns its grounding opinion: a compound
deterministic retrieval operation exposed on both faces, plus a `live_only`
facet on search and a per-call `budget` on `get_artifact`. This design pins
the contracts — tool schema, CLI flags, JSON shapes, pipeline stages,
provenance fields, and budget semantics — so implementation and the
external benchmark can proceed without re-litigation.

## User Need

Two consumers, one contract:

- An **agent over MCP** wants "the best grounding for this task" in one
  lean call — ranked, current (no superseded decisions), within a context
  budget, with enough provenance to trust and cite what came back.
- A **benchmark harness** (the SWE-DecisionBench `rac` arm) needs the
  identical retrieval logic per cell without a server lifecycle, and
  machine-readable provenance a deterministic scorer can use to measure
  governing recall.

## Design

### Compound operation — one core function, two faces

Core: a pure service function (a `services/`-layer sibling of the search
and scope seams) with the signature:

```text
retrieve_grounding(directory_or_read_model, task,
                   scope=None, top_k=5, budget=10_000, live_only=True)
```

MCP tool (sixth pinned tool). Optional arguments use empty-string/zero
sentinels rather than nullable types — the `find_decisions` `topic: str = ""`
precedent — because a nullable parameter costs an `anyOf` in the generated
schema, and the standing surface is token-budgeted (ADR-030):

```text
retrieve_grounding(task: str, scope: str = "", top_k: int = 5,
                   budget: int = 0, live_only: bool = True)
```

`scope=""` means no scope channel; `budget=0` means the server budget.

CLI:

```text
rac retrieve "<task>" [directory] [--scope <path>] [--top-k K]
    [--budget N] [--live | --all] [--json]
```

Both faces call the one core function in-process (ADR-031). For the same
`(corpus, arguments)` the JSON output is byte-identical across faces.

### Pipeline (all existing seams, one pass, deterministic)

1. **Discovery.** Two channels, unioned:
   - *keyword*: the task string tokenised by the ADR-037 rule and matched
     over the full tier ladder including tags (ADR-038, ADR-109), via the
     existing search seam;
   - *scope* (when `scope` is given): governing decisions whose declared
     `## Applies To` covers the path — the `decisions-for` semantics. Scope
     hits bind regardless of keyword match; this channel is immune to
     corpus size.
2. **Supersedes resolution.** With `live_only=True` (the default), retired
   artifacts (status in the type's spec-driven `retired_status` set) are
   dropped; when a dropped artifact has a live successor along an inbound
   `supersedes` edge, the successor is included and the substitution is
   recorded in provenance. Resolution follows the already-validated acyclic
   supersedes graph to its live end.
3. **Rank.** The existing BM25F + RRF fused ordering (ADR-078), unchanged.
   Scope-bound artifacts rank ahead of keyword-only hits; within each
   stratum the fused order applies, with the existing byte-stable
   tie-break.
4. **Cap.** Cut to `top_k`, then shape excerpts and enforce the character
   budget. Each item's `excerpt` is the head of the artifact's stored bytes
   capped at an even share of the budget (`budget // min(top_k, items)`), so
   k items carry comparable slices — symmetric with a top-k chunk retriever —
   instead of the first artifact consuming the response. The serialized
   payload is then guaranteed by the ADR-033 mechanism: excerpt-first
   truncation (trim the last kept item's excerpt tail), dropping whole items
   from the tail only when an emptied excerpt still does not fit, with the
   `truncated`/`omitted` markers (`omitted` counts dropped whole items).
5. **Assemble** the response with per-item provenance (below).

No model, network, clock, or randomness anywhere in the pass.

### Response shape (JSON, `schema_version: "1"`)

```json
{
  "schema_version": "1",
  "task": "…",
  "scope": "src/auth/tokens.py",
  "live_only": true,
  "items": [
    {
      "id": "RAC-…",
      "type": "decision",
      "title": "…",
      "status": "Accepted",
      "path": "rac/decisions/adr-….md",
      "excerpt": "…",
      "provenance": {
        "channels": ["scope", "keyword"],
        "matching_entry": "src/auth/**",
        "superseded": ["RAC-…"],
        "evidence": {"field": "title", "terms": ["token"], "tier": 1,
                     "score": 0.0,
                     "components": {"bm25": 0.0, "lexical_rank": 1,
                                     "graph_rank": 2, "inbound": 3}}
      }
    }
  ]
}
```

The ADR-033 markers (`truncated`, `omitted`, `hint`) are appended only when
truncation occurred — absent, not false, on a complete response.

- `channels` names every discovery route that surfaced the item:
  `"keyword"`, `"scope"`, `"supersedes"` (arrived as the live successor of
  a matched retired artifact).
- `matching_entry` is present only for scope-bound items: the declared
  `## Applies To` entry that covered the query path.
- `superseded` lists the retired artifact id(s) this item replaced, present
  only when the supersedes channel fired.
- `evidence` is the existing explain-hit object (field, terms, tier, score,
  components), present for keyword-channel items.
- `excerpt` is the head of the artifact's stored bytes, capped at the
  budget's per-item share (the Cap stage above).

Governing recall is scoreable from `items[].id` plus
`provenance.channels`/`matching_entry` alone; `evidence` explains ranking.

### `live_only` facet on search

- Core: the liveness predicate generalises to all types — *live* ⇔ status
  not in the type spec's `retired_status` set (same source relationship
  validation reads). Decisions keep their existing stricter predicate
  (`Accepted` and not retired) so `find_decisions` behaviour is unchanged.
- Faces: `rac find --live` (flag, default off) and
  `search_artifacts(live_only: bool = False)`. A pre-scoring constraint:
  the filter drops retired artifacts from the matched set before ranking —
  only matched files are re-read, never the whole corpus — so survivors
  rank among themselves while corpus-wide BM25 statistics stay
  corpus-global (the ADR-109 facet posture). Responses without the
  argument are byte-identical to today (ADR-007).

### Per-call `budget` on `get_artifact`

- `get_artifact(id, budget: int = 0)` (`0` — the default — means the
  server budget, the same sentinel encoding as the compound tool): when
  given, the effective budget is `min(server_budget, budget)` — a per-call
  value lowers, never raises, the server-wide ADR-033 budget. Enforcement,
  truncation strategy, and markers are the existing mechanism unchanged.
  Unit: characters of serialized JSON.
- The compound op's `budget` argument has the same unit and the same
  lower-only clamp on the MCP face; the CLI face has no server budget, so
  `--budget` applies directly with the same default.

### Benchmark consumption contract

- One CLI invocation per cell:
  `rac retrieve "<task>" <corpus-dir> --scope <path> --top-k K --budget N --json`.
- Exit codes: `0` on success including an empty `items` list (empty
  grounding is a valid answer), `2` on usage errors (unreadable directory,
  invalid arguments) — the existing CLI contract.
- The JSON shape above is additive and stable (ADR-007); scorers key on
  `items[].id`, `provenance.channels`, and `matching_entry`.
- Byte-identity across faces is a tested guarantee, so CLI-measured results
  speak for the MCP surface (ADR-097 family membership).

## Constraints

- Deterministic and offline end to end (ADR-002, ADR-066, ADR-097).
- One shared core implementation; no parallel search, scope, ranking, or
  budget path (ADR-031; reuse ADR-037/038/078/109 seams and the ADR-033
  budget mechanism).
- All changes to existing tools are additive; absent arguments produce
  byte-identical responses (ADR-007).
- The sixth tool's standing description must keep the pinned surface inside
  the standing token budget's hard cap (ADR-030); the description is a
  verbatim-pinned product string. The budget and cap constants are derived
  from a per-tool ceiling (200 budgeted / 250 capped per tool, the
  calibration of the original five-tool values), so they scale with
  deliberate surface growth — six pinned tools cap at 1500 — never with
  description bloat.
- Work-bounding caps (edge and traversal limits) apply before the budget,
  as elsewhere in the serving layer.

## Rationale

- **Characters, not tokens**, for `budget`: ADR-033's unit is deterministic
  across tokenizers; benchmark fairness needs reproducibility more than
  token precision, and a deterministic token approximation exists
  downstream for consumers that need a token view.
- **Scope-ahead-of-keyword stratification**: a decision that declares it
  governs the path is categorically more binding than a lexical match; the
  strata make governing recall insensitive to corpus growth, which is the
  property the benchmark exists to demonstrate.
- **Union then resolve, not resolve then union**: supersedes resolution
  runs over the unioned candidate set so a retired decision found by
  keyword still leads the consumer to its live successor — the exact
  failure (`must_not_return` surfacing a superseded decision) the grounding
  eval treats as a hard violation.
- **CLI face for the harness**: thousands of cells cannot each pay a server
  lifecycle; in-process sharing (ADR-031) makes the cheap path also the
  faithful path.

## Alternatives

- **Expose composition parameters (channel weights, strata toggles)**:
  rejected for v1 — every knob weakens "RAC's opinion" into "the caller's
  composition" and widens the benchmark's degrees of freedom.
- **Return full artifact bodies and let the caller trim**: rejected — the
  budget is the fairness fix; unbudgeted grounding reproduces the
  context-dump arm.
- **A `sections` selector on `get_artifact`** (return named `##` sections
  only): deferred to Open Questions — the character budget alone meets the
  lean-grounding need for v1 with a smaller contract.

## Accessibility

Human CLI output is plain text, colour-free, and column-aligned in the
style of the existing `decisions-for` rendering: one line per item with id,
status, and title, an indented `↳ via: <channels> [entry|evidence]`
provenance line, and a footer count including omissions — legible in
terminals, CI logs, and screen readers.

## Style Guidance

Follow the existing face conventions: `--json` selects the machine shape;
human output mirrors `render_decisions_for_human` alignment; JSON field
names are snake_case and emitted only when non-empty (absent-when-empty,
per the search-result precedent); errors are structured data on the MCP
face, never exceptions.

## Open Questions

- Whether a `sections` selector on `get_artifact` earns its contract weight
  once real budget-shaped usage exists, or the character budget suffices.
- Whether the scope channel should also admit non-decision artifacts with
  declared applicability once any other type carries scope sections.
- The exact stratum rule when an item is both scope-bound and a top lexical
  hit is fixed (scope stratum wins); whether provenance should also carry
  the lexical rank it would have had is open.

## Related Decisions

- adr-113
- adr-030
- adr-031
- adr-033
- adr-034
- adr-037
- adr-038
- adr-066
- adr-067
- adr-078
- adr-097
- adr-109
- adr-007

## Related Requirements

- rac-compound-grounding-retrieval
- rac-grounding-baseline-study

## Related Roadmaps

- grounding-retrieval-surface
