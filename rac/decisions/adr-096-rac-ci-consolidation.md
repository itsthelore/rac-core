---
schema_version: 1
id: RAC-KWA4ZD9Q6EPZ
type: decision
tags: [structure, org, ci, distribution]
---
# ADR-096: rac-ci Consolidation — Capability × Platform, Source-Install Dogfood, v1 Tagging

## Context

ADR-092 places all CI delivery in a single `rac-ci` repository and the `rac-ci`
roadmap consolidates the action sources that had lived in `rac-core`
(`action.yml`, `pr-gate-action/`, `validate-action/`) plus the standalone
`rac-actions` / `lore-watchkeeper` / `lore-gatekeeper` stubs. Landing that move
surfaced three choices the roadmap left open and that this ADR settles, since they
exceed a pure relocation.

`rac-core` **dogfooded** its own wrappers via `uses: ./` with `install-from:
source`, and the wrappers' `source` branch installed the in-repo engine from
`$GITHUB_ACTION_PATH`. That mode cannot survive the move (the rac-ci subdirs are
not the engine package), so the dogfood mechanism and the wrapper install surface
had to be decided, along with how the actions repo is versioned.

## Decision

### Capability × platform layout

`rac-ci` holds one subdir per **capability**, platform nested within (`github/`
first):

- `watchkeeper/github/` — `rac watchkeeper` (PR knowledge review).
- `gatekeeper/github/` — `rac gate --sarif` (required merge gate).
- `registrar/github/` — `rac validate --sarif` (well-formedness, ADR-058). The
  validate capability is named **Registrar**; it is a distinct, separately
  pinnable action, not folded into the gate.
- `recordkeeper/` — placeholder for the ADR-084 read-access recorder (no source
  yet).

`bitbucket/` and `jenkins/` join under each capability when demanded; the engine
is platform-neutral (SARIF/JSON), so that work is in the wrappers.

### Wrappers install the published engine

The `rac-ci` wrappers install the published `rac-core` from PyPI (default) or a
pinned `rac-version`. The previous `install-from: source` mode is removed — its
only consumer was `rac-core`'s own dogfood.

### rac-core dogfoods via source-install, not its own wrappers

`rac-core`'s pre-merge checks run the gates as **direct source-install CLI steps**
(`pip install -e .` then `rac watchkeeper` / `rac validate --sarif` / `rac gate
--sarif`), the same shape as its existing agent-rules / eval / doctor jobs.
`rac-core` does not consume its own published wrappers — it dogfoods the engine
itself, stays self-contained, and avoids a circular dependency on a `rac-ci`
release tag. The wrapper-contract tests move to `rac-ci`.

### Versioning: a moving major `v1`

`rac-ci` is consumed as `uses: itsthelore/rac-ci/<capability>/github@<ref>` and
ships **no PyPI artifact**, so ADR-076's CalVer (whose rationale is PyPI release
sorting) does not apply. `rac-ci` publishes a **moving major tag `v1`** that
consumers pin and that is repointed on each release — the GitHub Actions idiom.
The `setuptools-scm` constraint that forbade a moving tag in `rac-core` does not
exist here (no package).

### Versioned cutover

Old `rac-core` action references stay resolvable on their existing tags
(`itsthelore/rac-core@<oldtag>`, `…/validate-action@v0`, `…/pr-gate-action@v0`);
only `@main` and future tags drop the actions. New consumers use the `rac-ci`
paths. The predecessor repos are archived with redirect notes.

## Consequences

### Positive

- One bounded CI repo, capability-first, consistent with ADR-092; the per-action
  repos retire.
- `rac-core`'s dogfood tests the real engine and carries no dependency on a
  `rac-ci` tag.
- Actions versioning follows the ecosystem idiom (`@v1`) instead of a PyPI scheme
  that does not fit.

### Negative

- The wrappers lose `install-from: source`; anyone who relied on it (only
  `rac-core` did) uses a source install of the CLI directly instead.
- A moving `v1` is mutable by design; consumers wanting immutability pin a SHA.

### Risks

- A consumer pinned to an old in-repo action path breaks if those tags are
  deleted. Mitigation: retain the old `rac-core` tags; cut over by version.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

### rac-core consumes rac-ci's own actions for dogfood

Rejected: it couples `rac-core`'s CI to a `rac-ci` release tag (chicken-and-egg on
the first cut) and tests the wrapper rather than the engine. Source-install
dogfood is self-contained and more honest.

### CalVer (`YYYY.MM.N`) tags for rac-ci

Rejected: ADR-076's CalVer exists for PyPI release sorting; `rac-ci` ships no
package and is consumed by `uses:` ref, where a moving major `v1` is the
convention.

### Fold validate into the gate

Rejected: `rac gate` already runs validation, but the standalone Registrar
(`rac validate --sarif`, ADR-058) is a lighter, separately pinnable check
consumers adopt first; keeping it distinct preserves that adoption path.

## Relationship to Other Decisions

- ADR-092: realises the `rac-ci` repo in the topology.
- ADR-064: restores the single-CI-repo consolidation intent.
- ADR-068: retires the per-action `lore-watchkeeper` / `lore-gatekeeper` repos.
- ADR-090: capability-first satellite intent, realised as capability subdirs.
- ADR-063, ADR-058, ADR-049: the wrappers stay thin CLI consumers.
- ADR-076: CalVer governs PyPI releases; `rac-ci` (no package) uses a moving `v1`.

## Related Decisions

- adr-092
- adr-064
- adr-068
- adr-090
- adr-063
- adr-058
- adr-076

## Related Roadmaps

- rac-ci
- repo-topology-convergence
