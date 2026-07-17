---
schema_version: 1
id: RAC-KV4134WXQY0Y
type: design
tags: [ci, github-action, sarif, dx]
---
# Design: CI Action and Developer Experience

## Context

ADR-058 decides to distribute validation as a thin composite GitHub Action that
runs `rac validate --sarif` and uploads to Code Scanning. `rac validate --sarif`
(v0.15.2) already emits deterministic SARIF 2.1.0 over core + OKF findings (and,
after v0.17.1, the per-type standards findings). This design works out the
action's shape and the docs that make adoption copy-paste.

## User Need

A team adopting RAC wants its corpus checked on every pull request, with findings
annotated inline on the diff, set up by pasting one workflow file — and a first
run on a legacy repo must not fail the build on hundreds of pre-existing findings.

## Design

### The composite action

`action.yml` at the repository root (or `action/`), a *composite* action:

1. `actions/setup-python`.
2. `pip install requirements-as-code` (pinned, or `[ingest]` extras if inputs ask).
3. `rac validate "${{ inputs.path }}" --sarif > rac.sarif` (continue-on-error so a
   non-zero exit still uploads the SARIF).
4. `github/codeql-action/upload-sarif` with `sarif_file: rac.sarif`.
5. Re-surface the CLI exit code as the step result (fail the check on errors).

Inputs: `path` (default `rac/`) and `fail-on` (mapped to the CLI's exit
behaviour). The action owns no validation logic — it shells the CLI (ADR-058).
Required permission, documented: `security-events: write`.

### Warnings-first by construction

Errors fail the check; warnings — including findings a repo downgraded via the
`.rac/config.yaml` `validation` section (ADR-053) — annotate without failing. So
the onboarding path is: adopt with noisy types/rules downgraded to warning, get a
green check with inline annotations, tighten over time.

### Developer-experience docs

- A **CI quickstart**: the workflow snippet, the permission, and the expected
  inline-annotation result.
- A **warnings-first onboarding walkthrough**: point at a legacy repo, downgrade in
  `.rac/config.yaml`, watch the check go green, then ratchet.
- The **extensibility-boundary note**: custom artifact types and custom
  relationship edges are deferred (ADR-052, ADR-055); the code-defined type and
  relationship registries are the supported surface, with worked examples of the
  built-ins rather than docs for unbuilt machinery.

### Demonstration

Run the action on a sample-repo PR and confirm findings annotate inline; a fixture
test asserts the wiring (SARIF produced, exit code propagated). The SARIF
determinism guarantees (ADR-054) mean the annotations are stable across re-runs.

## Constraints

- **Thin wrapper (ADR-058 / ADR-005).** No logic beyond installing and running the
  CLI; the CLI stays the source of truth.
- **OKF-grain (the invariant).** Validation needs only a Git checkout and the CLI;
  the only network step is the SARIF upload to GitHub.
- **Determinism (ADR-002).** Same corpus state → same SARIF → same annotations.
- **Additive (ADR-007).** A new distribution surface; no change to the CLI or SARIF
  contracts.

## Rationale

A composite action is the lightest surface that does the job (a `pip install` plus
one CLI call), avoids a container build, and keeps the CLI authoritative. Reusing
`github/codeql-action/upload-sarif` means RAC inherits GitHub's inline-annotation
behaviour rather than reimplementing it.

## Alternatives

- A Docker container action: heavier and slower; deferred (ADR-058).
- Emitting `::error` workflow commands instead of SARIF: ephemeral, not stored as
  code-scanning alerts; rejected as the contract (ADR-058).

## Accessibility

Findings surface as GitHub Code Scanning annotations and as plain-text CLI output;
no colour-only or image-only signal, consistent with RAC's plain-text, viewer-
agnostic model (ADR-014).

## Open Questions

- Publish to the GitHub Marketplace now, or ship the `action.yml` for direct
  `uses:` reference first?
- Pin `rac` to a released version in the action, or track the repo's own version?

## Related Decisions

- adr-058
- adr-054
- adr-049

## Related Requirements

- rac-growth-adoption

## Related Roadmaps

- v0.17.2-ci-action-and-dx
