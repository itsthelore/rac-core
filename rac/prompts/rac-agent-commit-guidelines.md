# Prompt: Standardize RAC Commit Messages

## Status

Approved

## Context

RAC development follows a roadmap-driven workflow:

Roadmap artifact → scoped implementation → branch → commit → pull request → release.

Commit history should tell the product story of RAC.

A reader should be able to scan:

```bash
git log --oneline
```

and understand:

- what changed
- where it changed
- why the change exists
- how the release evolved

Unstructured commits make the repository harder to inspect, automate, review, and maintain.

## Goal

Create commit messages that provide:

- consistent change classification
- clear ownership areas
- roadmap-level traceability
- readable release history

Commits should become a lightweight historical record of RAC's evolution.

## Commit Format

Use:

```text
<type>(<area>): <imperative summary> [reference]
```

Example:

```text
feat(relationships): add validation CLI [roadmap:v0.7.2]
```

This provides:

- type — what kind of change happened
- area — where the change landed
- reference — why the change exists

## Allowed Types

Use only:

| Type | Purpose |
| --- | --- |
| feat | New user-visible behavior |
| fix | Bug fix or incorrect behavior |
| test | Tests, fixtures, regression coverage |
| docs | README, ADR, roadmap, examples |
| refactor | Internal restructuring without behavior change |
| chore | Packaging, releases, branches, dependencies |

Avoid adding new types unless necessary.

## RAC Areas

Prefer capability areas rather than file names.

Recommended:

- validate
- inspect
- stats
- ingest
- improve
- schema
- relationships
- artifacts
- roadmap
- design
- prompt
- release

Examples:

```text
feat(schema): add template output [roadmap:v0.5.2]

fix(relationships): preserve invalid references [roadmap:v0.7.2]

docs(readme): clarify installation workflow [roadmap:v0.7.3]
```

## Roadmap Implementation Commit Sequence

For roadmap-driven releases, prefer commits that mirror the lifecycle of the work.

Default sequence:

```text
docs(roadmap): refine vX.Y.Z implementation contract [roadmap:vX.Y.Z]

feat(core-area): add core model/schema support [roadmap:vX.Y.Z]

feat(command): expose behavior in CLI [roadmap:vX.Y.Z]

test(core-area): add boundary and fixture coverage [roadmap:vX.Y.Z]

docs(command): update user-facing usage notes [roadmap:vX.Y.Z]

chore(release): prepare vX.Y.Z branch for PR [roadmap:vX.Y.Z]
```

This reflects the preferred RAC delivery flow:

1. Define the contract
2. Build the capability
3. Expose the interface
4. Validate behavior
5. Document usage
6. Prepare release

Not every roadmap item requires every commit type.

Small releases may only need:

```text
docs(roadmap): define v0.7.3 scope [roadmap:v0.7.3]

feat(relationships): add JSON validation output [roadmap:v0.7.3]

test(relationships): cover validation output contract [roadmap:v0.7.3]

chore(release): prepare v0.7.3 release [roadmap:v0.7.3]
```

The goal is not commit quantity.

The goal is preserving the implementation story.

## References

### Roadmap Work

Use:

```text
[roadmap:vX.Y.Z]
```

Example:

```text
feat(relationships): add validation command [roadmap:v0.7.2]
```

When useful, include the artifact path in the commit body:

```text
Implements rac/roadmaps/v0.7.2-relationship-validation.md.

Adds:
- rac relationships --validate
- validation issue reporting
- missing target detection
- ambiguous target detection
```

### Issue Work

Use:

```text
[issue:#number]
```

Example:

```text
fix(release): align package metadata version [issue:#12]
```

### Release Maintenance

Use:

```text
[release:vX.Y.Z]
```

Example:

```text
chore(release): publish v0.7.2 package [release:v0.7.2]
```

## Commit Summary Rules

Commit summaries should:

- use imperative language
- describe the change introduced
- remain specific
- avoid implementation noise

Good:

```text
feat(relationships): add target validation service [roadmap:v0.7.2]
```

Bad:

```text
relationship work

fix stuff

updates

final changes
```

## AI Contribution Rules

When commits are produced with AI assistance:

Do:

- follow the same commit standard
- describe the actual product change
- preserve human-readable history

Do not add:

- generated-by footers
- AI assistant attribution
- tool-specific signatures

The commit belongs to the project history, not the tool used to create it.

## Success Criteria

A healthy RAC commit history should read like:

```text
docs(roadmap): refine v0.7.2 implementation contract [roadmap:v0.7.2]

feat(relationships): add validation service [roadmap:v0.7.2]

feat(relationships): expose validation CLI flag [roadmap:v0.7.2]

test(relationships): add missing target fixtures [roadmap:v0.7.2]

docs(relationships): document validation workflow [roadmap:v0.7.2]

chore(release): prepare v0.7.2 branch for PR [roadmap:v0.7.2]
```

A future maintainer should understand the release journey without needing external context.