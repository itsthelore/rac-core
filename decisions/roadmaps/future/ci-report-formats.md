---
schema_version: 1
id: RAC-KWGMTBJEQFMM
type: roadmap
---
# CI Report Formats Beyond SARIF

## Status

Planned

Unscheduled member of the `agnostic-surfaces` programme, Track 1
(distribution and CI reach). SARIF shipped under ADR-054 and serves
GitHub Code Scanning; GitLab and JUnit-consuming platforms need their
own native shapes.

## Outcomes

- GitLab merge requests render `rac` findings in the code-quality
  widget from a natively emitted report, with no translation glue.
- Any dashboard or CI system that consumes JUnit XML (Jenkins, GitLab,
  Bitbucket plugins, test-report tooling) can display `rac` gate
  results as test outcomes.
- The report surface stays one deterministic engine output away from
  every finding-producing command, exactly as SARIF is today.

## Initiatives

- Add a GitLab code-quality JSON renderer and a JUnit XML renderer in
  the output layer beside the SARIF renderer, reusing its shared
  finding-collection path and its deterministic ordering discipline
  (sorted results, no timestamps, version from the installed package).
- Expose them with flags mirroring `--sarif` on the same commands —
  `validate` (directory), `relationships --validate`, `review`, and
  `gate` — with the same exit-code semantics.
- Pin both formats with golden output tests alongside the existing
  SARIF and JSON goldens.
- Document both formats and per-platform wiring snippets (GitLab
  `codequality` report artifact, JUnit report ingestion) in the CLI
  docs; the snippets pair with the official OCI image.

## Constraints

- Additive only (ADR-007): new flags and outputs; no change to existing
  JSON, SARIF, or exit-code contracts.
- Deterministic and offline (ADR-002, ADR-066): byte-stable output for
  a given corpus and version; no wall-clock timestamps.
- Renderers translate the engine's existing findings; they compute no
  new findings and hold no policy (policy stays in the engine commands,
  as with the shipped actions).
- Fidelity limits are documented, not papered over: JUnit's
  test-case model and GitLab's severity set are narrower than SARIF;
  the mapping is fixed and recorded in the docs.

## Success Measures

- A GitLab pipeline shows `rac` findings in the merge-request
  code-quality widget using only documented flags and snippets.
- A JUnit consumer renders a `rac gate` run as pass/fail test cases.
- Golden tests pin both formats byte-for-byte; `rac validate rac/` and
  the full test battery stay green.

## Assumptions

- The existing shared finding-collection path used by SARIF exposes
  everything both formats need; no new engine-side finding fields are
  required.
- GitLab's code-quality schema and JUnit XML remain stable consumer
  contracts.

## Risks

- Severity/level mapping disagreements between platforms invite ad-hoc
  per-platform tweaks; mitigated by one fixed, documented mapping table
  shared by both renderers.
- Format sprawl: every new platform requests its own shape; mitigated
  by holding the line at these two widely-consumed formats and pointing
  the long tail at the stable JSON contract (ADR-007), the pattern
  ADR-073 set for backends.

## Related Decisions

- ADR-002
- ADR-007
- ADR-054
- ADR-066

## Related Roadmaps

- agnostic-surfaces
- oci-image
- rac-ci
