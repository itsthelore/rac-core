---
schema_version: 1
id: RAC-KTQ63DSC8SZW
type: decision
---
# ADR-027: CI Test Topology — Merge-Gated, Per-Service Batteries

## Status

Accepted

## Category

Process

## Context

RAC runs its test suite in GitHub Actions through a single reusable workflow,
`.github/workflows/tests.yml`, which is consumed by two callers:

- `.github/workflows/ci.yml` — continuous integration.
- `.github/workflows/python-publish.yml` — the release/publish pipeline.

Two aspects of this setup were never written down, and had begun to drift with each
CI edit:

1. **When tests run.** `ci.yml` triggered on every `pull_request` *and* on pushes to
   `main`. Every push to an open PR branch therefore re-ran the entire suite, and the
   policy for *when* CI should run was never recorded — so it was liable to be widened
   or narrowed incidentally.
2. **How the suite is shaped.** `tests.yml` ran the whole suite as a single `pytest`
   job parameterized only by Python version (`["3.11", "3.12", "3.13"]`). The Actions
   UI showed only `pytest (3.11)`, `pytest (3.12)`, `pytest (3.13)`. A failure named the
   Python version but not the **service** at fault, and the run shape did not reflect
   RAC's service-oriented architecture (ADR-008), where each capability is an isolated
   `.py` service under `src/rac/services/` plus the `core`, `cli`, and artifact layers.

The release path already gated publishing on the reusable test workflow
(`release-build: needs: test`), but that gate was likewise an unrecorded convention
rather than a stated policy.

Absent a recorded decision, each of these choices invites silent regression — a
re-added PR trigger, a collapsed matrix, a release that builds before tests — on the
next person's CI edit. This ADR fixes the CI test topology so future changes are
deliberate.

## Decision

RAC's CI test topology is governed by three rules.

### 1. Tests run on merge to `main`, not on pull requests

`ci.yml` triggers on `push:` to `main` (a merged PR or a direct push) and on
`workflow_dispatch` (manual). It does **not** trigger on `pull_request`.

The explicit, accepted consequence: **a pull request receives no automated test
feedback before it merges.** A regression is caught by the post-merge run on `main`
and then blocks the next release through the gate (rule 2), rather than being caught
on the PR itself. `workflow_dispatch` is the escape hatch — the full battery grid can
be run against any branch on demand from the Actions tab.

Runs on `main` use `concurrency` with `cancel-in-progress: false`, so every merge is
fully tested and a later merge does not cancel an in-flight run.

### 2. Releases are gated on the full suite

`python-publish.yml` runs the reusable test workflow as a `test` job and makes
`release-build` depend on it (`needs: test`). Nothing is built or published unless
**every** battery passes. This protects the public contracts a release ships — the CLI
command surface (ADR-005) and the JSON output (ADR-007).

### 3. The suite is organized as per-service batteries

`tests.yml` defines a two-axis matrix — supported Python version × **battery** — where
each battery is one `.py` service (`diff`, `improve`, `index`, `ingest`, `inspect`,
`portfolio`, `relationships`, `stats`), plus the grouped `core`, `cli`, and `artifacts`
layers. Each battery runs on every supported Python version (currently 3.11–3.13, per
`pyproject` `requires-python`). Job names surface service and version, e.g.
`relationships (py3.11)`.

The battery list is an **explicit, static enumeration** in the workflow — not
discovered dynamically — and every `tests/test_*.py` file maps to exactly one battery.

## Principles

### Principle 1 — Test topology mirrors the service architecture

ADR-008 makes each capability a reusable service. CI makes each service a battery, so a
red check names the responsible module instead of an opaque interpreter version.

### Principle 2 — One reusable workflow is the single source of truth

`tests.yml` is the only definition of *how* tests run. Both CI and the release gate
consume it, so day-to-day testing and release testing can never diverge.

### Principle 3 — The matrix is explicit and deterministic

The battery list is readable in the YAML and changes only by deliberate edit. This is
consistent with RAC's preference for deterministic, inspectable structure over
generated or dynamically discovered behavior.

### Principle 4 — Trigger policy is recorded, not incidental

*When* tests run is a decision with real tradeoffs. It lives here so a future CI edit
changes it on purpose, with this context in view, rather than by accident.

## Consequences

### Positive

- A failed check names the service and Python version, so triage starts at the right
  module without opening logs.
- The run shape matches the architecture; adding a service is a one-line battery
  addition.
- Releases cannot ship on a red suite, and the gate shares one definition with CI.
- PR pushes no longer trigger repeated full-suite runs, reducing Actions usage on
  in-flight branches.

### Negative

- Pull requests get no pre-merge test signal by default; regressions surface
  post-merge on `main`. Mitigated by `workflow_dispatch` and the release gate.
- More jobs per run (batteries × versions ≈ 33). They are short and run in parallel,
  but the checks list is longer.
- The battery list must be kept in sync: a new `tests/test_*.py` that is not added to a
  battery will not run in CI. Guarded by a coverage check at change time; a CI
  self-check could enforce it later.

## Alternatives Considered

### Run tests on every pull request

Keep the `pull_request` trigger so PRs are checked before they merge.

#### Pros

- Regressions are caught before landing — standard CI practice.

#### Cons

- The stated goal was to stop running the suite on every push to in-flight branches.
- Doubles runs (push + PR) and spends Actions minutes on branches that may be rebased
  or abandoned.

Deferred, not rejected — to be reconsidered if outside contributors need pre-merge
gating (see Review Date).

### Single job parameterized only by Python version (the prior shape)

#### Pros

- Fewer jobs; simplest possible matrix.

#### Cons

- A failure shows only the Python version, not the service.
- The run shape ignores the service architecture.

Rejected — it is exactly the opacity this decision removes.

### Per-test-file batteries

One job per `tests/test_*.py`.

#### Pros

- Finest possible granularity.

#### Cons

- ~19 batteries × 3 versions, with near-duplicates (e.g. three relationship files) and
  no service-level grouping; noisier than per-service for no extra signal.

Rejected.

### Dynamically discovered matrix

Generate the battery list from the filesystem at run time.

#### Pros

- No manual sync; new test files are included automatically.

#### Cons

- A generated matrix is opaque to read and non-deterministic; it contradicts RAC's
  preference for explicit, inspectable structure.

Rejected — the sync cost is instead paid by an explicit list plus a coverage check.

## Relationship to Other ADRs

### ADR-008 Agent-Ready Architecture

Capabilities live in reusable services. The per-service battery topology is the CI
projection of that architecture — one service, one battery.

### ADR-005 CLI First and ADR-007 JSON Contract Stability

The CLI and JSON outputs are RAC's public contracts. The release gate (rule 2) exists
so no release ever ships with those contracts broken.

### ADR-003 Structured Outputs First

Typed, structured outputs are what make services testable in isolation, which is what
lets the suite split cleanly along service lines.

## Success Measures

Evidence that this decision is working:

- A red CI check identifies the failing service and Python version without opening logs.
- Adding a new service adds exactly one battery entry — a one-line diff.
- No release builds or publishes while any battery is failing.
- Every `tests/test_*.py` belongs to exactly one battery; no test is silently unrun.
- The trigger policy changes only via a deliberate edit to this decision.

## Review Date

Review before v1.0.0, or sooner if RAC accepts outside contributors who need pre-merge
test feedback — which would warrant re-adding a `pull_request` trigger (rule 1) — or if
the job count from the battery × version grid becomes burdensome.
