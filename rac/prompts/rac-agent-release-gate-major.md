We are preparing a major release for RAC.

Your job is to run a release gate review, not to implement changes yet.

Context:
- RAC is a Markdown-first CLI for requirements-as-code.
- The system supports typed product artifacts such as Requirements, Decisions, Roadmaps, Designs, and related schema/template/improve/inspect/stats behavior.
- The product goal is deterministic artifact recognition, structural validation, useful CLI feedback, and stable JSON contracts.
- The release must not drift into project management, UI rendering, semantic scoring, AI interpretation, collaboration workflows, databases, accounts, or web-app behavior unless explicitly approved.

Review the current repository against these gates:

## 1. Product scope gate

Identify anything in this release that exceeds the intended product boundary.

Check for:
- behavior that interprets artifact quality instead of validating structure
- workflow/project-management behavior
- semantic relationship analysis
- UI/design-token/rendering behavior
- hidden AI-like inference
- new concepts not documented in roadmap, ADRs, or release notes
- CLI behavior that surprises the user

Return:
- PASS / BLOCK
- exact files or commands involved
- required scope cuts before release

## 2. Architecture consistency gate

Review whether the artifact model is still coherent.

Check:
- whether classification, validation, stats, schema, templates, inspect, and improve use shared artifact metadata where possible
- whether any artifact has special-case logic that should be generalized
- whether Roadmap, Design, Decision, and Requirement behavior follow the same architectural pattern
- whether new code duplicates existing artifact handling
- whether any module is becoming too large or too coupled
- whether public contracts are separated from implementation details

Return:
- PASS / BLOCK
- duplicated paths
- special cases that should be removed
- proposed simplification before release

## 3. Duplication and deletion gate

This is a hard simplification review.

Answer these directly:

- What code became obsolete during this release?
- What can be deleted before release?
- What logic was copied instead of shared?
- Which artifact-specific branches can be collapsed into generic artifact-spec-driven behavior?
- Did any file grow past a size where it should be split?
- Are there old fixtures, examples, or docs that now contradict the current model?
- Are there stale branches, stale roadmap files, or stale TODOs that should be cleaned up?

Return:
- required deletions
- optional cleanup
- changes that should wait until after release

## 4. CLI contract gate

Review every public command affected by this release.

Commands to check:
- rac validate
- rac diff
- rac stats
- rac inspect
- rac improve
- rac schema
- rac ingest, if touched

For each affected command, verify:
- human output is stable and understandable
- JSON output is stable and documented
- exit codes are intentional
- invalid input behavior is clear
- warnings vs errors are consistent
- unsupported artifact behavior is explicit
- examples in README/docs still work

Return a table:

Command | Changed? | Human output ok? | JSON ok? | Exit codes ok? | Docs ok? | Blockers

## 5. Classification boundary gate

Review artifact classification behavior.

Check:
- Requirements do not classify as Design
- Designs do not classify as Requirements
- Roadmaps classify by approved structure, not loose title matching alone except where explicitly intended
- UI/design-themed titles alone do not classify as Design
- invalid but recognizable artifacts classify correctly, then fail validation separately
- incomplete artifacts behave according to the spec
- mixed documents do not produce surprising classifications
- negative fixtures exist for adjacent artifact types

Return:
- PASS / BLOCK
- missing boundary tests
- risky classification rules
- recommended fixture additions

## 6. Validation and schema gate

Check that validation behavior and schema output agree.

Verify:
- required sections match the artifact specs
- recommended and optional sections are consistent across schema, templates, validation, and docs
- metadata vocabularies are enforced consistently
- missing required sections produce clear errors
- invalid metadata values produce clear errors
- schema JSON is stable and documented
- template output follows canonical section order

Return:
- mismatches
- missing tests
- release blockers

## 7. Test and verification gate

Do not accept “tests pass” as enough.

Run or identify the exact commands needed to verify the release.

Check:
- unit tests for changed behavior
- CLI smoke tests
- classification boundary tests
- negative fixtures
- JSON output snapshots or equivalent assertions
- docs examples manually or automatically verified
- packaging/build check
- import check from a clean environment, if practical

Return:
- exact commands run
- exact commands still needed
- failures
- missing test files
- blockers

If tests are missing for new behavior, mark the release BLOCKED.

## 8. Documentation gate

Review documentation from a new user’s point of view.

Check:
- README reflects current commands
- artifact docs match implementation
- examples use current output
- release notes or changelog entry exists
- ADRs are not contradicted
- roadmap item is updated or marked complete
- install/publish instructions are still accurate
- known limitations are explicit

Return:
- stale docs
- missing docs
- docs that overpromise behavior

## 9. Release hygiene gate

Check repository and release state.

Verify:
- working tree is clean
- release branch is based on current origin/main
- merged branches are pruned or listed for pruning
- version number is updated consistently
- package metadata is correct
- no generated Claude attribution appears in commits, PR text, release notes, or docs
- CI is green
- build artifacts are not accidentally committed
- no credentials or local paths leaked

Return:
- PASS / BLOCK
- exact commands to confirm state
- required cleanup

## 10. Backward compatibility and migration gate

Identify anything that could break existing users.

Check:
- command names
- arguments and flags
- JSON field names
- exit codes
- artifact classification behavior
- validation strictness
- package extras
- import paths
- documented examples

Return:
- breaking changes
- whether each breaking change is intentional
- migration note required
- release blocker if undocumented

## Output format

Return the review in this structure:

# Major Release Gate Review

## Decision
PASS or BLOCK

## Release blockers
List only issues that must be fixed before release.

## Required simplifications
List duplication, deletion, or extraction work required before release.

## Test evidence
List commands run and results. If not run, say NOT RUN.

## Product scope issues
List any behavior that exceeds the intended boundary.

## Architecture issues
List duplicated or inconsistent implementation paths.

## CLI contract issues
List command/output/JSON/exit-code problems.

## Documentation issues
List stale, missing, or overpromising docs.

## Release hygiene issues
List branch/version/CI/commit/publishing concerns.

## Safe to defer
List cleanup that is real but not release-blocking.

## Exact next actions
Give a short checklist of the next changes to make.

Important rules:
- Do not implement anything in this pass.
- Do not invent test results. If you did not run a command, mark it NOT RUN.
- Cite exact files and commands.
- Treat missing tests for new public behavior as a blocker.
- Treat duplicated artifact-specific