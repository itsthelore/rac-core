---
schema_version: 1
id: RAC-KV4134WXK6KW
type: decision
tags: [ci, distribution, sarif, dx]
---
# ADR-058: Distribute Validation as a Thin GitHub Action with SARIF Upload

## Status

Proposed

## Category

Architecture

## Context

`rac validate --sarif` (v0.15.2, ADR-054) emits SARIF, and ADR-049 names
write-time CI enforcement as RAC's product — but there is no turnkey way to run
RAC in CI and surface findings where review happens. GitHub Code Scanning ingests
SARIF and annotates findings inline on a pull request; the missing piece is the
*distribution surface* that connects `rac validate` to it.

The OKF-grain invariant matters here: validation must stay a CLI over a Git
checkout, with no required server or SDK to read artifacts. Any CI surface must
be a thin wrapper that adds no logic the CLI does not already own (ADR-005:
CLI-first; ADR-002: determinism).

## Decision

RAC ships a **composite GitHub Action** in this repository that wraps the CLI:

1. **Thin wrapper, CLI is the source of truth.** The action installs `rac`, runs
   `rac validate <path> --sarif`, and uploads the result with
   `github/codeql-action/upload-sarif`. It contains no validation logic of its
   own; the CLI's exit code is the check's result.
2. **Inputs:** the corpus path and a fail policy; **output:** the SARIF file and
   the exit code. Errors fail the check; warnings (including findings downgraded
   via `.rac/config.yaml`, ADR-053) annotate without failing — warnings-first
   onboarding by construction.
3. **Deterministic and offline-by-default.** The only network step is the SARIF
   upload to GitHub; validation itself is offline and deterministic (ADR-002), so
   the same corpus state yields the same annotations.
4. **A derived distribution surface, not a new contract.** The action is versioned
   alongside the CLI and the SARIF contract (ADR-007/ADR-054); it is replaceable
   and adds no obligation beyond "run the CLI in CI".
5. **DX docs ship with it,** including the warnings-first onboarding walkthrough
   and the honest "custom types and custom relationships are deferred; the
   code-defined registries are the supported surface" note (ADR-052, ADR-055).

## Consequences

### Positive

- RAC's write-time gate becomes visible on the PR diff via Code Scanning, with a
  copy-paste workflow — the distribution the enforcement product needs.
- The OKF-grain invariant holds: the action is a thin CLI wrapper, nothing more.

### Negative

- A second distribution surface (the action) to keep in step with the CLI and the
  SARIF contract. Mitigated: it shells the CLI and owns no logic.
- Code Scanning requires `security-events: write` permission; documented.

### Neutral

- Marketplace publishing and a Dockerized variant are packaging choices fenced to
  the implementation; a composite action is the default for being lightest.

## Alternatives Considered

- **Workflow-command annotations (`::error file=…`) only.** Rejected as the
  contract: ephemeral, log-scoped, not stored as code-scanning alerts. SARIF is the
  durable, reviewable surface.
- **A Docker container action.** Deferred: heavier and slower than a composite
  action for what is a `pip install` + one CLI call.
- **No first-party action (leave CI wiring to users).** Rejected: a turnkey action
  is the adoption on-ramp the brief calls for; hand-rolled SARIF upload is friction.

## Related Decisions

- adr-054
- adr-049
- adr-007

## Related Requirements

- rac-cross-artifact-enforcement
- rac-growth-adoption

## Related Roadmaps

- v0.17.2-ci-action-and-dx

## Related Designs

- ci-action-and-dx
