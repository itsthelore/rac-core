---
schema_version: 1
id: RAC-KV3SME4ESBPA
type: decision
tags: [validation, ci, interop, output]
---
# ADR-054: SARIF as a Derived Validation Output for CI Code Scanning

## Status

Proposed

## Category

Architecture

## Context

RAC's enforcement is the product (ADR-049), but its only machine output is the
JSON validation contract (ADR-007), which GitHub's PR review surface does not
render natively. The Static Analysis Results Interchange Format (SARIF 2.1.0) is
the format GitHub Code Scanning ingests to annotate findings inline on a pull
request diff — the distribution surface a CI-enforced validator needs to be
visible where review happens.

RAC's findings are already SARIF-shaped: a core `Issue` carries a stable `code`,
a `severity`, a `message`, and an optional `line`, anchored to a file path; OKF
conformance findings carry a code, path, message, and (after ADR-053) a severity.
What is missing is a renderer and a CLI surface.

## Decision

1. **`rac validate <dir> --sarif`** emits a SARIF 2.1.0 document for the corpus,
   covering both core validation findings and OKF conformance findings in one
   run (`tool.driver.name = "rac"`). It is mutually exclusive with `--json`.
   SARIF is a repository-scan artifact; there is no single-file SARIF surface
   (single-file `--sarif` is a usage error).

2. **A derived contract, parallel to JSON (ADR-007).** SARIF is a presentation of
   the same `DirectoryValidation` result, never a new source of truth. Severity
   maps to SARIF `level` (`error`/`warning`); a finding's `line` becomes a
   `region` when present, omitted for file-level findings; suppressed (`off`)
   findings — already dropped by the override pass (ADR-053) — never appear.

3. **Deterministic and offline (ADR-002).** Results are sorted by
   `(uri, startLine, ruleId, message)`, the declared `rules` are the sorted set
   of observed codes, and no timestamps are emitted, so the same corpus state
   yields a byte-identical document. The only build-derived field is the tool
   version, which reflects the installed package.

4. **Emission here, upload later.** This decision delivers valid SARIF emission.
   Wrapping it in a GitHub Action that uploads the file and annotates the PR is a
   later, separately scoped piece of work; relationship-validation SARIF is
   likewise deferred (the relationship report is a distinct model).

## Consequences

### Positive

- RAC findings can be surfaced inline on a PR by GitHub Code Scanning, making the
  write-time gate visible where reviewers work.
- Reuses existing finding data with no model change beyond ADR-053's severity on
  OKF findings; no new dependency.

### Negative

- SARIF is a second machine-output surface to keep stable as findings evolve.
  Mitigated: it is a thin, derived projection with deterministic ordering and
  structural tests.

### Neutral

- Relationship-validation findings and the GitHub Action wrapper are out of scope
  here and tracked separately.

## Alternatives Considered

- **GitHub workflow-command annotations (`::error file=...`) instead of SARIF.**
  Rejected as the contract: ephemeral, not stored as code-scanning alerts, and
  log-scoped. RAC already has a workflow-annotation path for watchkeeper; SARIF
  is the durable, reviewable surface.
- **Extend the JSON contract instead of adding SARIF.** Rejected: GitHub does not
  ingest RAC's JSON; SARIF is the lingua franca for code scanning.
- **A single combined output for validate + relationships.** Deferred: the
  relationship report is a separate model; folding it in is future work.

## Related Decisions

- ADR-049
- ADR-007
- ADR-053
- ADR-002
- ADR-048

## Related Requirements

- rac-cross-artifact-enforcement
- rac-growth-adoption
