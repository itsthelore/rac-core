# Grounding retrieval benchmark fixture (v0.23.0, WS1)

This directory is the versioned fixture the `rac eval` grounding benchmark
scores. It is a dev/CI surface, not a RAC artifact corpus — nothing here is part
of the product knowledge under `rac/`.

## Layout

- `corpus/` — a small, schema-valid fixture corpus (`rac validate` exit 0),
  spanning all five artifact types, modelling a fictional collaborative editor
  ("Aurora"). It includes:
  - a **supersession chain**: `decision-token-expiry-v1` (Status: Superseded) is
    superseded by `decision-token-refresh-v2` (Status: Accepted). The superseded
    member is the canonical `must_not_return` hard negative — a query about the
    current policy must surface v2, never v1.
  - **distractors**: e.g. `decision-rate-limiting` ("token-bucket") shares the
    word "token" with the auth decisions but must not be confused with them.
  - an **ambiguous pair**: `design-sidebar-navigation` and
    `design-mobile-navigation` both concern navigation; a specific query must
    disambiguate to the right one.
- `queries.json` — the scored query set. Each case names exactly one tool
  (`search_artifacts` or `get_related`), a `query` (a search string, or the
  artifact id to look up for `get_related`), a `category`, the `relevant` ids,
  and an optional `must_not_return` set.
- `eval-config.json` — the gate's floors and tolerance. Gated metrics:
  `overall.p_at_1`, `overall.r_at_5`, `negative_violations`, and each query
  category's `p_at_1` / `r_at_5`. Per-tool figures are diagnostic.
- `baseline.json` — the committed `metrics` baseline, written by
  `rac eval --update-baseline` (human-only; CI never rebaselines).

## Running

```sh
rac eval                  # human-readable scorecard
rac eval --json           # full scorecard JSON
rac eval --check          # CI gate: exit 0 pass / 1 regression / 2 usage error
rac eval --update-baseline  # human-only re-baseline
```

## Calibration

The initial floors come from the first green run, on which every category scored
1.0. Overall floors are the fixed targets (`p_at_1 ≥ 0.90`, `r_at_5 ≥ 0.95`);
per-category floors sit a margin below their calibrated values, with the
committed baseline minus the tolerance (`0.02`) providing the tight per-category
regression guard. When the corpus or query set legitimately changes, re-run
`rac eval --update-baseline` and commit the new baseline alongside the change.
