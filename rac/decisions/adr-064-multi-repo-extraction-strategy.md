---
schema_version: 1
id: RAC-KV68XJGEXBNB
type: decision
tags: [structure, org, packaging, distribution]
---
# ADR-064: Multi-Repo Extraction Strategy for the itsthelore Organisation

## Status

Accepted

## Category

Architecture

## Context

`requirements-as-code` has moved from a personal GitHub account
(`tcballard`) into the `itsthelore` organisation. The repository is a
monorepo for **Lore** (the product) whose engine is **RAC** — the
`requirements-as-code` package under `src/rac/`. Alongside the engine it
carries several components that are self-contained and were only colocated
because a personal account is, in practice, a single repository:

- `decisiongrounding/` — a reproducible benchmark with its own
  `pyproject.toml`, tests, LICENSE, and independent version. It treats `rac`
  as an external CLI on `PATH` and imports no engine code (DG-ADR-0001).
- `validate-action/action.yml` and the root `action.yml` (Watchkeeper) —
  thin GitHub composite actions that wrap the `rac` CLI (ADR-058 governs the
  validation action).
- `examples/` — the flagship grounding demo (`examples/guide/`, referenced by
  `guide-grounding-demo` and the v0.10.2 roadmap) and dashboard fixtures the
  test suite depends on. This is product-defining, dogfooded material, distinct
  from the *separately planned* liftable SDK examples sub-project that the
  v0.20.1 roadmap designs to "graduate to their own repo."

An organisation can host sibling repositories, so colocation is no longer
forced. There is no recorded decision about the org move or about which
components should live in their own repos, and RAC's own rules require
durable, cross-cutting structural thinking to be recorded in the corpus
(`rac-agent-session-start`). This ADR settles the repository topology; the
`repo-extraction-programme` roadmap sequences the moves.

Two existing decisions fence this one:

- ADR-029 freezes the engine and its MCP server (`rac mcp`) into a *single*
  package and release pipeline. This decision must not fragment that.
- ADR-036 and ADR-039 freeze the distribution names (PyPI
  `requirements-as-code`, CLI `rac`, server identity `lore`). This decision is
  about repository topology, not renaming any shipped surface.

## Decision

Adopt a small **multi-repo** topology under `itsthelore`: extract the
genuinely standalone components into their own repositories, and keep the
engine and everything that ships or governs it in
`itsthelore/requirements-as-code`.

**Extract into their own `itsthelore` repositories:**

| Component | Current path | New repo | Why it leaves |
| --- | --- | --- | --- |
| Decision-grounding benchmark | `decisiongrounding/` | `itsthelore/decisiongrounding` | Zero code coupling; own packaging, tests, LICENSE, and ADRs, which travel with it. |
| GitHub Actions | `validate-action/action.yml`, root `action.yml` | `itsthelore/rac-actions` | Thin CLI wrappers reusable by any repo, with a release cadence independent of the engine. |

The GitHub Actions land in a **single** `itsthelore/rac-actions` repository,
each action in its own subdirectory (`gatekeeper/`, `watchkeeper/`), referenced
as `itsthelore/rac-actions/<name>@<ref>`. The `validate` action is **renamed
Gatekeeper** — it holds the gate on corpus validity, a sibling to Watchkeeper
(ADR-049, "enforcement is the product").

**Keep in `itsthelore/requirements-as-code`:**

- The engine — `src/rac/` (CLI, core, services, output, explorer) and the MCP
  server (`rac mcp`). ADR-029 keeps these one package; do not split them.
- Bundled agent skills (`src/rac/skills/`), templates, and git hooks — these
  are shipped resources, discovered and installed by the CLI.
- The dogfood corpus (`rac/`) — it governs the project and stays with the code
  it governs.
- `examples/` — the grounding demo (`examples/guide/`) is the product's
  headline proof, woven into the corpus (a design and the v0.10.2 roadmap
  reference it) and into the test fixtures (`example_dashboard_v*.md`).
  Extracting it would fragment the demo and strand the fixtures; it stays.
- `lore-web/` — no Python coupling, but its Portal shell is *vendored* into
  `src/rac/` through a build script and a drift-guard test. Extraction is
  **deferred** until a publish/vendor contract exists; it is a future review
  trigger, not decided here.

Distribution names stay frozen (ADR-036, ADR-039). Extracted repos follow the
`rac-<name>` convention where they relate to the engine; `decisiongrounding`
keeps its established name. Each repo carries its own `examples/` subdirectory
where useful — the same convention the engine keeps for `examples/guide` —
rather than a central examples repository.

## Consequences

### Positive

- Ownership and release cadence become per-component: a benchmark run, an
  action bump, or an examples refresh no longer rides the engine's release.
- The engine repository shrinks to the engine, its shipped resources, and its
  governing corpus — a smaller surface to validate, review, and reason about.
- The standalone components prove themselves as outside consumers of the
  published package exactly as a third party would, strengthening the public
  contract (ADR-062).

### Negative

- More repositories to create, permission, and maintain under the org.
- Extracting the GitHub Actions **changes the `uses:` path** consumers
  reference (`itsthelore/requirements-as-code/validate-action@ref` and the
  root action) — a breaking change that requires a versioned cutover and a
  documentation update, not a silent move.

### Risks

- **Cross-repo drift.** Components that no longer live beside the engine can
  lag its contract. Mitigation: each extracted repo depends on the *published*
  package or the public CLI, never on engine internals, and pins a version.
- **Stranded action references.** Consumers pinned to the old `uses:` path
  break on extraction. Mitigation: the roadmap extracts the actions last,
  behind a versioned cutover with a deprecation note.

## Alternatives Considered

### Keep everything in the monorepo

Leave all components colocated and rely on directory boundaries.

#### Advantages

- No migration work; no `uses:`-path churn.

#### Disadvantages

- Couples unrelated release cadences to the engine's, and keeps the engine
  repository carrying a benchmark and actions that no longer need to be there
  now that an org can host siblings.

### Extract `examples/` to its own repo

Lift `examples/` into a dedicated `itsthelore/rac-examples` alongside the
benchmark.

#### Advantages

- A single home for pedagogical material across the org.

#### Disadvantages

- `examples/guide` is the grounding demo — the product's headline proof — and
  is referenced by a design, the v0.10.2 roadmap, and the test fixtures.
  Extracting it fragments the demo and strands fixtures the suite depends on.
  Rejected; examples stays, and each repo keeps its own `examples/` subdir
  instead. (The separately planned liftable SDK examples sub-project, v0.20.1,
  is unaffected.)

### Extract `lore-web` now as well

Lift the web viewer in the same pass.

#### Advantages

- Fully separates the TypeScript stack from the Python engine.

#### Disadvantages

- The Portal shell is vendored into `src/rac/` via a build script and a
  drift-guard. Extracting before a publish/vendor contract exists would break
  the vendoring path. Rejected for now; tracked as a future review trigger.

## Related Decisions

- adr-012
- adr-029
- adr-036
- adr-039
- adr-058
- adr-062

## Related Requirements

- rac-growth-extensibility

## Related Roadmaps

- repo-extraction-programme

## Success Measures

- Each extracted component lives in its own `itsthelore` repository, depends
  only on the published package or public CLI, and shows no engine-coupling
  regression.
- Consumer-facing references (action `uses:` paths, docs, CI) are updated and
  no issue traces to a stranded reference.
- The engine repository's `rac validate`, `rac relationships --validate`, and
  `rac review` gates stay green after each extraction.

## Review Date

Revisit when the `lore-web` Portal-shell vendoring gains a publish/vendor
contract (then decide its extraction), or when a third-party schema-bundle
ecosystem (`rac-growth-extensibility`) begins and the `rac-<name>` repo
convention needs hardening.
