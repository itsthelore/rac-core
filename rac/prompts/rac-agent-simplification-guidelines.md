# Module Simplification Refactor Contract

## Context

RAC has grown quickly through roadmap-led implementation. Some modules now risk accumulating additive paths faster than they are simplified.

This prompt is for behavior-preserving module simplification.

## Prompt

We are simplifying the Python modules in `requirements-as-code`.

Goal:
Reduce implementation complexity without changing user-facing behavior.

Target area:
`<module or command area>`

Before editing:

- Refresh from `origin/main`.
- Create a new branch named `<branch-name>`.
- Read the relevant roadmap item, ADRs, tests, and fixtures for this area.
- Do not implement until I approve the plan.

Analysis required:

- Identify the current responsibilities of the target module.
- List public functions/classes and who calls them.
- List CLI behavior, JSON output, validation rules, exit codes, and fixtures that must not change.
- Identify duplicated logic, mixed responsibilities, dead branches, or logic that belongs in `ArtifactSpec`.
- Identify one simplification seam that can be changed safely.

Constraints:

- No user-facing behavior changes.
- No output shape changes unless explicitly approved.
- No new feature work.
- No broad rewrites.
- No formatting-only churn.
- No README changes unless needed to preserve existing docs accuracy.
- No model attribution in commits.
- Prefer deleting branches and moving existing rules into existing data structures over inventing new abstractions.

Return an implementation contract only.

## Expected Output

```markdown
## Current behavior to preserve

- ...

## Complexity found

- File/function:
- Problem:
- Why it matters:

## Proposed simplification

- Move/extract/delete:
- Files touched:
- Behavior preserved:

## Safety checks

- Tests to run:
- Fixtures to add or reuse:
- CLI commands to verify:

## Commit plan

Use step-based commits, not per-file commits:

- `refactor(<area>): <behavior-preserving simplification> [roadmap/refactor:<name>]`
- `test(<area>): cover preserved behavior around <case> [roadmap/refactor:<name>]`
```

Stop after the plan and wait for approval.