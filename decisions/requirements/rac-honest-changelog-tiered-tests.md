---
schema_version: 1
id: RAC-KV6KFQ0J1TEM
type: requirement
tags: [internal, changelog, testing, release]
---
# Requirement: Honest Changelog and Tiered Tests

## Status

Accepted

Classification: `[internal]`. Scoped to the v0.23.0 hardening release (WS10).
Delivered as the **Test tiers** section of `docs/testing.md` (the three tiers
mapped to their real CI jobs and copy-paste local commands — documenting the
existing ADR-027 topology, no new markers or taxonomy) and one honest v0.23.0
CHANGELOG entry (What shipped / What is deferred / Known limits, headlining
user-facing items only). REQ-005 — cutting the single `v0.23.0` git tag from
which setuptools-scm derives the version — is the maintainer's release action,
not performed here (the same human-only release-tail pattern as the v0.10.2
guide demo); this workstream ships only after every other v0.23.0 workstream has
landed.

## Problem

A hardening release needs trust signals and fast feedback loops. RAC's CI test
topology already runs in three concrete layers (ADR-027) — a PR pre-merge tier,
a merge-gated full grid, and a release gate — but those layers are an emergent
property of the workflow YAML, not something a developer can map to a local
command. WS10 documents the tiers as they actually run, adds an honest CHANGELOG
entry for a release with significant deferred scope, and tags the single
`v0.23.0` release. The documentation must describe what runs today; it MUST NOT
restructure the suite, add batteries, or change the trigger policy recorded in
ADR-027.

This requirement is the packaging workstream: it ships only after every other
v0.23.0 workstream has landed, because the CHANGELOG entry and the tag describe
the whole release. It is `[internal]` plumbing and is the first Tier 2 item cut
if the week runs short (the obey-demo is the non-cuttable anchor above it).

## Requirements

- [REQ-001] The release MUST document the three test tiers defined in **Test Tiers** below, each mapped to the concrete test group and CI job that runs it and given a copy-paste local command.
- [REQ-002] Documentation MUST describe the existing topology only — no new pytest markers, no new taxonomy, and no change to the ADR-027 trigger policy; any added command is a thin convenience wrapper over the file lists already in the workflows.
- [REQ-003] The release MUST add ONE CHANGELOG entry under the next version heading covering, honestly, the **What shipped**, **What is deferred**, and **Known limits** content specified in **Changelog Contract** below.
- [REQ-004] The CHANGELOG headline MUST lead only with the user-facing items (explainable retrieval, `rac doctor`, provenance, the trust model) plus "provably works"; internal plumbing (WS6, WS8, WS10) MUST NOT be headlined.
- [REQ-005] The release MUST be cut as a single `v0.23.0` git tag — one PyPI version, no source edit — from which setuptools-scm derives the version (`pyproject.toml` declares `dynamic = ["version"]`; there is no VERSION file). It MUST NOT be split across multiple tags or versions.

## Test Tiers

The tiers below document the topology ADR-027 already runs; they are a reading of
the workflows, not a new structure.

1. **Inner loop (smoke)** — the smoke set run pre-merge by the `smoke` job in
   `.github/workflows/pr-checks.yml` (`core` + `golden` + `dogfood` on py3.11).
   Local: `pytest -q` over that file list. Fastest signal; catches
   output-contract drift and corpus damage.
2. **Pre-push (PR tier)** — what a pull request actually runs: `pr-checks.yml`'s
   `lint` (`ruff check`, `ruff format --check`, `mypy src/`) plus the smoke job,
   plus the dogfood actions (watchkeeper, validate, agent-rules, pr-gate). Local
   equivalent: `rac gate rac/` plus the lint trio plus the smoke set.
3. **Full local CI (merge grid)** — the complete per-service battery × Python
   grid from the reusable `.github/workflows/tests.yml` (every `tests/test_*.py`
   belongs to exactly one battery, enforced by `tests/test_ci_batteries.py`).
   Local: `pytest -q` over the whole suite. This is the grid that gates `main`
   (`ci.yml`) and releases (`python-publish.yml`, `needs: test`).

## Changelog Contract

The single entry MUST cover, honestly:

- **What shipped** — the user-facing workstreams (WS1 grounding benchmark +
  `rac eval --check`, WS2 explainable retrieval, WS3 `rac doctor`, WS5
  provenance, WS11 trust model + `SECURITY.md`) and that they are
  regression-guarded ("provably works").
- **What is deferred** — the Tier 3 carve-outs and the named Non-Goals: no
  multi-agent CI harness (the obey-demo is a manual smoke, not a gate), no
  schema-migration framework, no resumability, no multi-hop traversal.
- **Known limits** — explicitly that the MCP server is pull-based / read-only
  (the agent must consult it; nothing is pushed) and that full CI enforcement of
  code-vs-decision conflicts is a future release.

## Acceptance Criteria

- The three tiers are documented, each mapped to its real CI job
  (`pr-checks.yml` smoke, `pr-checks.yml` lint+smoke+dogfood, `tests.yml` grid)
  with a copy-paste local command; no new pytest markers or taxonomy introduced.
- ONE CHANGELOG entry names the shipped user-facing workstreams, the deferrals
  (Tier 3 + Non-Goals), and the two known limits (pull-based MCP server;
  code-vs-decision enforcement deferred), with the headline leading on
  user-facing items only.
- A single `v0.23.0` tag is cut; the build version derives from it via
  setuptools-scm with no source edit.

## Success Metrics

- A developer can run the right tier for the change at hand from the documented
  command without reading workflow YAML.
- A reader of the CHANGELOG understands exactly what `v0.23.0` does and does not
  deliver, including the pull-based-server and deferred-enforcement limits.

## Risks

- Headlining internal items would misrepresent the release as feature-heavy.
  Mitigation: the narrative discipline is encoded in REQ-004.
- Documenting tiers that diverge from the workflows would mislead developers and
  rot on the next CI edit. Mitigation: REQ-001/REQ-002 bind the docs to the
  existing `pr-checks.yml` / `tests.yml` jobs rather than a parallel taxonomy.
- Splitting the work into more than one version would break the one-release
  scope fence. Mitigation: REQ-005 fixes a single `v0.23.0` tag.

## Assumptions

- The existing per-service battery grid (ADR-027) and `pr-checks.yml` smoke tier
  can be *documented* as three developer tiers without restructuring the tests
  or changing the trigger policy.
- All other v0.23.0 workstreams have landed before this one runs, so the
  CHANGELOG and tag describe the complete release.

## Out of Scope

- Restructuring the suite, adding or renaming batteries, or introducing pytest
  markers (the grid is an explicit static enumeration per ADR-027).
- Changing the ADR-027 trigger policy (no new `pull_request` full-grid trigger,
  no coverage threshold gate).
- Any second version or tag; CI enforcement of code-vs-decision conflicts (a
  future release, only *noted* here).

## Related Decisions

- adr-027
- adr-007

## Related Requirements

- rac-grounding-eval-benchmark

## Related Roadmaps

- v0.23.0-hardening
