---
schema_version: 1
id: RAC-KV68XS3J7P6C
type: roadmap
tags: [structure, org, distribution]
---
# Repo Extraction Programme

## Status

Planned

## Context

ADR-064 records the decision to adopt a small multi-repo topology under the
`itsthelore` organisation: extract the standalone components and keep the
engine, its shipped resources, and its governing corpus in
`itsthelore/requirements-as-code`. This programme sequences those extractions.
It is a non-versioned `future/` item because the work is structural and
cross-cutting, not a feature release on the current series.

Two components extract; `examples/` is explicitly kept (ADR-064), since
`examples/guide` is the grounding demo and the dashboards are test fixtures.
The two extraction targets differ in risk. `decisiongrounding` imports no
engine code and can move with no consumer impact. The GitHub Actions are the
consumer-breaking target: extraction changes the `uses:` path that downstream
workflows reference, so they come last and behind a versioned cutover.

## Outcomes

- Each target component lives in its own `itsthelore` repository, depending
  only on the published `requirements-as-code` package or the public `rac`
  CLI — never on engine internals — with no coupling regression.
- The engine repository carries only the engine, its shipped resources
  (skills, templates, hooks), and the dogfood corpus.
- Every consumer-facing reference (action `uses:` paths, docs, CI workflows)
  is updated, and no stranded reference is left behind.

## Initiatives

### Initiative 1 — Extract `decisiongrounding` (reference migration)

The cleanest target and the pattern for the rest. Move `decisiongrounding/`
to `itsthelore/decisiongrounding` with history preserved, carrying its own
`pyproject.toml`, tests, LICENSE, Makefile, and its `decisions/` ADRs
(DG-ADR-0001 onward). It already treats `rac` as an external CLI on `PATH`, so
no code changes are needed; remove the directory from the monorepo and update
any references to it (including the v0.20.1 roadmap's "mirrors
`decisiongrounding/`" note, which becomes a cross-repo reference).

### Initiative 2 — Extract the GitHub Actions to `itsthelore/rac-actions`

Move `validate-action/action.yml` and the root `action.yml` (Watchkeeper) into
a single `itsthelore/rac-actions` repository, each action in its own
subdirectory: `gatekeeper/` (the `validate` action, **renamed Gatekeeper** — it
holds the gate on corpus validity, a sibling to Watchkeeper) and
`watchkeeper/`. This changes the `uses:` path consumers reference, so it ships
behind a versioned cutover: publish the new location, document the new `uses:`
references (`itsthelore/rac-actions/gatekeeper@v1`,
`itsthelore/rac-actions/watchkeeper@v1`), leave a deprecation note for the old
`itsthelore/requirements-as-code/validate-action@ref` path, and update this
repository's own `.github/workflows/` to the new location. ADR-058 governs the
validation action and moves with it.

### Initiative 3 — Keep `examples/`; adopt the per-repo examples convention

`examples/` is **not** extracted. `examples/guide` is the grounding demo and
the dashboards are test fixtures, so they stay in the engine repo (ADR-064).
The convention going forward: each repo carries its own `examples/`
subdirectory where useful, rather than a central examples repository. The
separately planned liftable SDK examples sub-project (v0.20.1) is unaffected by
this programme.

## Constraints

- No engine behaviour change and no change to the public surface: this is a
  topology move, not a feature.
- Distribution names stay frozen (ADR-036, ADR-039): PyPI
  `requirements-as-code`, CLI `rac`, server identity `lore`.
- The engine and MCP server stay one package (ADR-029); they are not part of
  any extraction.
- Each extraction preserves history (`git filter-repo` or `git subtree`,
  decided per repo) rather than copying files flat.

## Non-Goals

- Extracting `examples/` or creating a `rac-examples` repo — examples stays in
  the engine repo (ADR-064).
- Extracting `lore-web` — deferred by ADR-064 until its Portal-shell vendoring
  has a publish/vendor contract.
- Renaming the package, CLI, or server.
- Creating the org repositories as part of this corpus task; the repos are
  created when each initiative is executed.

## Implementation Contract

**Safety sequencing.** Populate each destination repo with preserved history
and confirm it *before* removing anything from the engine repo. Never delete
from `requirements-as-code` until the content lives elsewhere.

**Seed `itsthelore/decisiongrounding`** (history-preserving):

```bash
git clone <engine-url> dg && cd dg
git filter-repo --path decisiongrounding/ --path-rename decisiongrounding/:
git remote add origin <decisiongrounding-url> && git push -u origin main
```

**Seed `itsthelore/rac-actions`** (history-preserving, two subdirs):

```bash
git clone <engine-url> acts && cd acts
git filter-repo --path validate-action/ --path action.yml \
  --path-rename validate-action/:gatekeeper/ \
  --path-rename action.yml:watchkeeper/action.yml
```

Then rename the validate action to **Gatekeeper** inside
`gatekeeper/action.yml` (the `name:` field and header comment), add a README
documenting the new `uses:` references, tag `v1`, and push.

**Removal + rewire PR on `requirements-as-code`** (one PR for the whole
carve-out): remove `decisiongrounding/`, `validate-action/`, and the root
`action.yml`; repoint the engine's own self-tests in
`.github/workflows/pr-checks.yml` (`uses: ./` → `…/rac-actions/watchkeeper@v1`;
`uses: ./validate-action` → `…/rac-actions/gatekeeper@v1`); update or remove
`tests/test_validate_action.py` and `tests/test_watchkeeper.py`; update
`docs/watchkeeper.md`, `docs/validation.md` (grep for others) to the new repo
and add a deprecation note for the old path; keep `examples/` untouched.

After the removals the engine repository's `rac validate rac/`,
`rac relationships rac/ --validate`, and `rac review rac/` gates stay green,
and `pytest` passes.

## Success Measures

- Both extraction targets (`decisiongrounding`, `rac-actions`) live in their
  own repos and consume only the published package or public CLI; neither
  imports engine internals.
- No issue traces to a stranded `uses:` path or a missing relocated component.
- The engine repository's corpus gates remain green throughout.

## Assumptions

- The `itsthelore` organisation can host the sibling repositories and the
  maintainer can create and permission them when each initiative runs.
- `decisiongrounding` continues to consume `rac` only as an external CLI on
  `PATH`, so its move needs no code change (DG-ADR-0001 holds).
- The extracted actions consume only the public `rac` CLI, not engine
  internals, so they run from any repo once published.
- `lore-web` stays in this repository until its vendoring contract exists, so
  no Portal-shell drift-guard breaks during this programme.

## Risks

- **Stranded action references.** Consumers pinned to the old `uses:` path
  break. Mitigation: actions move last, behind a versioned cutover with a
  deprecation note.
- **Cross-repo drift.** Extracted components lag the engine contract.
  Mitigation: each pins a published-package or CLI version and depends on no
  internals.
- **History loss.** A flat copy discards provenance. Mitigation: the contract
  mandates a history-preserving move.

## Related Decisions

- adr-064
- adr-058

## Related Roadmaps

- v0.20.1-python-sdk-docs

## Related Requirements

- rac-growth-extensibility
