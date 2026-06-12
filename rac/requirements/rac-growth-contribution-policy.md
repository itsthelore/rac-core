---
schema_version: 1
id: RAC-KTYBCCTFG5JW
type: requirement
---
# Contribution Policy — Proposal-Gated Substantial Changes

## Status

Proposed
Blocked: GATE-2 (CLA not yet in place)

## Problem

RAC accepts external pull requests, but the project has no recorded policy
for when a contribution needs design agreement before code review. Today
`CONTRIBUTING.md` asks that behaviour changes "should trace to an artifact
under `rac/`", which is advisory: a contributor can open a large PR that
changes CLI behaviour or JSON contracts with no prior alignment, and the
maintainer's only options are to review the whole change cold or reject
work the contributor has already done.

Spec-driven projects have converged on a proposal-before-code model.
OpenSpec, for example, requires a change proposal for new features,
significant refactors, or architectural changes, while letting bug fixes
and typo corrections go directly to pull requests; proposals live as files
in the repository (`openspec/changes/`) and are archived after
implementation.
<!-- Source: https://github.com/Fission-AI/OpenSpec (README, retrieved 2026-06-12) -->

RAC is positioned to adopt the same gate more cheaply than most projects:
the corpus under `rac/` is already validated in CI, so a proposal does not
need a separate format or directory — the proposal IS a corpus change. The
difference from OpenSpec's model is deliberate: where OpenSpec archives a
proposal once it is consumed, a RAC proposal lands as a durable artifact
(roadmap initiative, ADR, or requirement) that remains part of the
project's governed knowledge after the change ships.
<!-- OpenSpec archival behaviour per https://github.com/Fission-AI/OpenSpec (README, retrieved 2026-06-12) -->

This policy cannot go live until a CLA is in place (GATE-2): inviting
substantial external contributions without one creates licensing exposure.

## Requirements

- [REQ-001] A substantial pull request — one that adds new user-visible behaviour, changes a CLI or JSON output contract, changes exit codes, or adds or alters artifact types or validation rules — shall be preceded or accompanied by a change to the `rac/` corpus (a roadmap initiative, an ADR, or a requirement artifact) that records the intent of the change.
- [REQ-002] The proposal shall itself be a corpus change: it is submitted as a pull request touching `rac/`, it must keep `rac validate rac/`, `rac relationships rac/ --validate`, and `rac review rac/` green, and no separate proposal format or directory shall be introduced.
- [REQ-003] Trivial changes shall be exempt from the proposal gate: bug fixes that restore already-specified behaviour, typo and documentation corrections, test-only changes, and dependency or CI chores may be submitted directly as pull requests.
- [REQ-004] Classification of borderline cases shall rest with the maintainer; a reviewer may ask for a proposal artifact before continuing review of a PR judged substantial.
- [REQ-005] Once this requirement is accepted and GATE-2 clears, the policy text shall live in `CONTRIBUTING.md` (draft section below); until then neither `CONTRIBUTING.md` nor `README.md` shall advertise the policy or solicit substantial contributions under it.

## Success Metrics

- Every substantial PR merged after the policy goes live traces to a
  corpus artifact created or amended before or alongside it.
- Trivial fixes are not slowed: exempt PRs require no artifact and no
  extra review round attributable to this policy.
- Zero substantial PRs rejected after full implementation for reasons
  that a proposal review would have caught earlier.

## Risks

- The gate can read as gatekeeping and deter first-time contributors if
  the exemption list is not prominent in the policy text.
- Borderline classification disputes consume maintainer time; REQ-004
  mitigates by making the call explicit and early.
- Going live before a CLA exists creates licensing exposure; the GATE-2
  block on this artifact exists to prevent that.

## Assumptions

- The corpus validation commands remain the CI gate for `rac/` changes,
  so proposal quality is enforced mechanically, not by convention.
- Contribution volume stays low enough for single-maintainer
  classification of borderline PRs.
- A CLA mechanism (GATE-2) will be selected by the maintainer; this
  artifact does not choose one.

## Draft CONTRIBUTING.md Section

The following is DRAFT text only. It does not go live, and
`CONTRIBUTING.md` is not modified, until GATE-2 (CLA) clears and this
requirement is accepted.

```markdown
## Proposing substantial changes

RAC manages its own product knowledge as a validated corpus under `rac/`.
Substantial changes go through that corpus before code review:

- **Needs a proposal first:** new user-visible behaviour, changes to CLI
  or JSON output contracts or exit codes, new artifact types or
  validation rules. Open a PR that adds or amends a `rac/` artifact — a
  roadmap initiative, an ADR, or a requirement — describing the intent.
  The proposal is a normal corpus change: it must keep `rac validate
  rac/`, `rac relationships rac/ --validate`, and `rac review rac/`
  green. Once the proposal is agreed, implement against it.
- **No proposal needed:** bug fixes that restore documented behaviour,
  typo and documentation corrections, test-only changes, dependency and
  CI chores. Submit these directly as pull requests.

If you are unsure which side a change falls on, open the PR and say so —
the maintainer will classify it, and may ask for a proposal artifact
before reviewing further.

Unlike tools that archive proposals once implemented, your proposal
remains in the corpus as a durable record of why the change exists.
```

## Related Decisions

- ADR-012
- ADR-022

## Related Requirements

- rac-documentation-structure
