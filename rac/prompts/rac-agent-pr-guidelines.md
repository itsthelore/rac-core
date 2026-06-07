````markdown
# Pull Request Documentation Generator

## Context

RAC development follows a roadmap-contract workflow.

Features are planned through explicit Roadmap artifacts, architectural decisions are captured through ADRs, and implementation happens through small scoped changes.

Pull requests act as durable repository memory after implementation conversations, AI sessions, and local context disappear.

A PR should preserve:

- what changed
- why decisions were made
- what was intentionally excluded
- what user-facing contract was introduced
- how correctness was verified

The PR is not a commit message.

Commits describe individual changes.

Pull requests document the accepted product and architecture contract.

## User Need

As a maintainer reviewing RAC changes,
I need pull requests to capture implementation scope, decisions, verification evidence, and release traceability,
so that future contributors can understand why the system behaves the way it does without needing the original planning conversation.

## Prompt

Generate a pull request description for a RAC change.

Use the implementation details, roadmap item, ADRs, commits, and code changes provided.

Structure the PR as a release-contract record.

Use the following format:

---

# Summary

Implements `<roadmap item / issue>`.

Adds:

- `<user-visible behavior>`
- `<CLI/API/schema behavior>`
- `<tests, fixtures, documentation included>`

# Roadmap / ADR Trace

Roadmap:

- `rac/roadmap/vX.Y.Z-<name>.md`

Relevant ADRs:

- `rac/adr/<adr-file>.md`
- `rac/adr/<adr-file>.md`

# Scope

## Included

- `<specific behavior shipped>`
- `<specific command/output/schema/test coverage>`

## Excluded

- `<explicitly deferred behavior>`
- `<nearby tempting capability intentionally avoided>`
- `<future roadmap boundary>`

Be aggressive about documenting exclusions.

Prefer:

- what RAC does now
- what RAC deliberately does not do yet

# Product / Architecture Decisions

Document accepted implementation decisions.

Include:

- naming decisions
- schema decisions
- JSON contract decisions
- validation behavior
- exit-code behavior
- architecture boundaries

Example:

- Chose `validation_issues` instead of `broken_relationships` because validation now covers multiple failure modes beyond missing links.

# User-Facing Contract

## CLI

Commands added or changed:

```bash
<command example>
````

## Human Output

Describe visible terminal behavior:

* `<output summary>`

## JSON Output

Document fields or shape changes:

```json
{
  "<field>": "<meaning>"
}
```

## Exit Codes

* `0`: `<meaning>`
* `1`: `<meaning>`
* `2`: `<meaning>`

# Verification

## Ran

Include exact verification commands.

Examples:

```bash
pytest
rac <command>
rac <command> --json
```

## Covered

Document tested scenarios:

* `<positive case>`
* `<negative case>`
* `<boundary case>`

Avoid:

"Tests pass."

Preserve the evidence.

# Review Path

Suggested review order:

1. `<core implementation files>`
2. `<schema / artifact changes>`
3. `<CLI interface changes>`
4. `<tests and fixtures>`
5. `<documentation>`

Explain the implementation story through the review order.

# Notes For Reviewer

Include:

* files worth extra attention
* known limitations
* deferred follow-ups

Do not repeat commit history.

# Implementation Process (Optional)

If relevant:

Implemented with AI assistance under the roadmap contract.

Final scope, review, and acceptance decisions were made by the maintainer.

## Constraints

* Do not create generic release notes.
* Do not summarize only commits.
* Do not omit intentional exclusions.
* Do not replace verification evidence with "tests pass".
* Do not introduce scope that was not accepted in the roadmap.
* Do not invent ADRs or decisions.
* Keep implementation rationale in the PR, not individual commits.
* Keep commit messages concise and separate from PR documentation.
* Prioritize future maintainability over marketing language.

## Related Requirements

* Pull requests must preserve architectural decisions after implementation context is lost.
* Pull requests must provide enough information for future contributors to understand behavioral contracts.

## Related Decisions

* Markdown remains the canonical artifact format.
* Roadmaps define implementation contracts before code changes.
* ADRs capture long-lived architecture decisions.

## Style Guidance

Write like a maintainer documenting a system contract.

Prefer:

"Relationship failures are reported as validation issues because validation covers duplicate identifiers, ambiguous targets, and missing references."

Avoid:

"Added relationship validation. Tests pass."

```
```
