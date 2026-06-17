---
schema_version: 1
id: RAC-KV8YZRHVYVSQ
type: roadmap
---
# RAC — Wayfinder Extraction (Future)

## Status

Planned

Unscheduled — captured as future intent, not yet on a release.

## Context

`rac route` (ADR-068) is a deterministic prompt-complexity router built inside
RAC as an exploration. ADR-069 decides it should not live here: it is a runtime
*inference* concern, divergent from Lore's recorded-knowledge product line, and
belongs in its own product — **Wayfinder** — as a sibling repo under the
`itsthelore` org (the topology of ADR-064 and the `repo-extraction-programme`).

This programme sequences that move. It is structural, not a feature release, and
is gated on Wayfinder actually shipping before anything is removed from RAC
(ADR-064's safety contract: never delete until the capability lives elsewhere).
Until then `rac route` stays exactly as built. When scheduled, this graduates out
of `future/` into a versioned plan.

## Outcomes

- Wayfinder exists as its own repository and package, **fully independent of RAC**
  — no `rac` import, no `requirements-as-code` dependency, no reading of `.rac/`.
- Wayfinder reaches behavior parity with `rac route`: the same structural score,
  features, and local/cloud recommendation, with ADR-068's boundary intact (score
  deterministically; never invoke a model).
- `rac route` is removed from RAC after the cutover, with history preserved, so
  the engine carries no long-term out-of-domain command.

## Initiatives

### Initiative 1 — Stand up `itsthelore/wayfinder`

Create the standalone product: the pure scorer (heritage of
`src/rac/core/complexity.py`), an **inlined** `split_frontmatter` (~17 generic,
import-free lines from `src/rac/core/frontmatter.py`), a config loader over
Wayfinder's **own** namespace (`wayfinder.toml` / env / flags — a ~10-line walk-up
modelled on `find_config_file`, never `.rac/`), a `wayfinder` CLI (prompt file /
stdin → recommendation + score + features, human and JSON), a small
`score_complexity` Python API, and its own tests, packaging, LICENSE, and ADRs.
Nothing imports `rac`.

### Initiative 2 — Confirm the name before it is public

Check availability of the `wayfinder` name (PyPI package, trademark, org repo)
before it is committed to any public surface. If taken, choose an alternative
here rather than after publishing.

### Initiative 3 — Deprecate and remove `rac route` from RAC

**Done.** Now that Wayfinder exists in the `wayfinder/` subproject at full parity,
the `rac route` prototype and all its supporting code (`core/complexity.py`,
`services/route.py`, the routing config loader in `services/init.py`, the route
renderers, the SDK exports, `tests/test_route.py`, the `route` CI battery, and the
`docs/cli.md` section) have been removed from RAC by restoring those files to their
pre-route state. The routing corpus artifacts (this roadmap, ADR-068, ADR-069, and
the `prompt-complexity-routing` design) are kept as the historical record. What
remains here is publishing Wayfinder to its own `itsthelore/wayfinder` repository.

The original plan: once Wayfinder ships and is verified, remove `rac route` and its
supporting code, with a deprecation note pointing users to Wayfinder, following
ADR-064's history-preserving cutover discipline.

## Constraints

- Independence (ADR-069): Wayfinder has zero runtime dependency on RAC and never
  reads the `.rac/` namespace.
- Routing boundary (ADR-068): deterministic, offline scoring and a recommendation
  only; Wayfinder never invokes a model, selects a provider, reads a credential,
  or tokenizes per a vendor model.
- Safety contract (ADR-064): nothing is removed from RAC until Wayfinder ships and
  is confirmed; history is preserved across the move.

## Non-Goals

- Sharing code at runtime between RAC and Wayfinder (the ~30 generic lines are
  reimplemented, not depended upon — ADR-069).
- Building any model invocation, provider selection, or credential handling into
  Wayfinder.
- Scheduling the work: this is recorded as considered, not committed to a release.

## Success Measures

- Wayfinder installs and runs with no `requirements-as-code` present and no
  `.rac/` directory on the path.
- Wayfinder output matches `rac route` for the same prompt and threshold.
- After cutover, RAC contains no `route` command and no routing code, and its
  tests pass.

## Assumptions

- The `wayfinder` name (or a chosen alternative) is available for public use.
- Demand for a standalone deterministic prompt router is real but unproven; this
  stays considered until that signal arrives.
- Reimplementing the ~30 generic lines in Wayfinder is preferable to a shared
  dependency (ADR-069).

## Risks

- The prototype lingers in RAC and removal never happens. Mitigation: Initiative 3
  is explicit and gated on Wayfinder shipping.
- Drift between `rac route` and Wayfinder while both exist. Mitigation: the window
  is bounded — parity then removal — and `rac route` is frozen, not extended,
  during it.

## Related Decisions

- adr-069
- adr-068
- adr-064

## Related Roadmaps

- repo-extraction-programme
- complexity-based-model-routing
