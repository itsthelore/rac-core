---
schema_version: 1
id: RAC-KTR62H90ND2A
type: requirement
---
# REQ-Trust-Transparency (Optics)

## Status

Proposed

## Problem

RAC is a requirements validator.

For RAC, determinism is not a supporting feature. Determinism is the product.

A tool that validates requirements must itself appear boring, reliable, testable, and automation-friendly. If the repository does not visibly demonstrate tests, fixtures, CI, and deterministic outputs, users may experience cognitive dissonance: the product claims to enforce trust, but the repository does not immediately prove trustworthiness.

## Requirements

- [REQ-001] RAC shall make its reliability and determinism obvious from the repository structure, documentation, and automation setup.

- [REQ-002] The repository shall clearly expose tests, fixtures, documentation, CI workflow, deterministic output examples, golden output tests, and project planning artifacts.

## Goals

* Improve trust optics before broader launch.
* Make RAC feel like reliable infrastructure.
* Demonstrate that RAC output is deterministic and tested.
* Reduce perceived risk for early users, contributors, and evaluators.
* Align repository presentation with RAC’s core product promise.

## Non-Goals

* Redesign RAC’s core product positioning.
* Add new validation semantics.
* Expand artifact types.
* Introduce hosted infrastructure.
* Replace the existing CLI workflow.

## Required Repository Shape

The repository should make the following structure visible at the top level:

```text
/
├── tests/
├── fixtures/
├── docs/
├── .github/
│   └── workflows/
│       └── ci.yml
├── rac/
│   ├── adr/
│   ├── requirements/
│   └── roadmap/
```

## Functional Requirements

### FR-1: Visible Test Suite

RAC shall include a visible top-level `tests/` directory.

The test suite shall cover core CLI and validation behavior.

### FR-2: Visible Fixtures

RAC shall include a visible top-level `fixtures/` directory.

Fixtures shall include representative valid and invalid RAC artifacts.

### FR-3: Deterministic Fixtures

Fixtures shall be stable and suitable for repeatable validation.

Running RAC against the same fixture shall produce the same result unless the relevant validation rules intentionally change.

### FR-4: Golden Output Tests

RAC shall include golden output tests for important commands.

Golden tests should cover outputs where determinism matters, including validation results, diffs, stats, and schema-related output.

### FR-5: CI Workflow

RAC shall include a GitHub Actions workflow at:

```text
.github/workflows/ci.yml
```

The CI workflow shall run the test suite on pull requests and pushes to the main branch.

### FR-6: CI Badge

The README shall include a visible CI badge.

The badge shall reflect the status of the main CI workflow.

### FR-7: Coverage Badge

The README shall include a visible coverage badge once coverage reporting is available.

If coverage reporting is not yet configured, the README shall not display a misleading badge.

### FR-8: Documentation Visibility

RAC shall include a visible top-level `docs/` directory.

Documentation shall explain how to run validation, tests, fixtures, and deterministic examples.

### FR-9: RAC Dogfood Artifacts

RAC shall include dogfooded planning artifacts under:

```text
rac/
├── adr/
├── requirements/
└── roadmap/
```

These artifacts shall be validated by RAC itself where practical.

### FR-10: README Trust Section

The README shall include a short trust-oriented section explaining that RAC is tested against deterministic fixtures and intended for CI-safe validation.

## Acceptance Criteria

* A new user can identify tests, fixtures, docs, CI, and RAC dogfood artifacts within 30 seconds of opening the repository.
* Pull requests automatically run the test suite.
* The README displays CI status.
* Core deterministic behavior is covered by fixtures or golden output tests.
* RAC dogfood artifacts are stored under `rac/`.
* The repository presentation reinforces that RAC is reliable infrastructure.

## Risks

* Trust work may delay feature development.
* Golden output tests may create maintenance overhead when output formats change.
* Badges may create false confidence if not backed by meaningful tests.

## Mitigations

* Keep the first implementation narrow.
* Start with the highest-value CLI paths.
* Treat golden output changes as intentional product changes.
* Only add badges that reflect real automated checks.

## Dependencies

* Existing test framework.
* GitHub Actions.
* Stable CLI outputs for core commands.
* Existing RAC artifact structure.

## Success Measures

* CI runs consistently on pull requests.
* README communicates reliability immediately.
* Fixtures become reusable examples for users and contributors.
* Golden output tests catch accidental output drift.
* RAC’s repository presentation matches its product promise.

## Related Artifacts

* ADRs defining RAC as Markdown-first infrastructure.
* Roadmap items for repository structure, CI, fixtures, and test coverage.
* Requirements covering validation, diffing, stats, and schema behavior.
