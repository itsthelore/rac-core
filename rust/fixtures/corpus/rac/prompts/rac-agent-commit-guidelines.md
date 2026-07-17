---
schema_version: 1
id: RAC-KV2J331NH44T
type: prompt
---
# RAC Commit Message Standard

## Objective

Produce commit messages that make RAC's history tell the product story.

RAC development follows a roadmap-driven workflow: roadmap artifact → scoped
implementation → branch → commit → pull request → release. A reader should
be able to scan `git log --oneline` and understand what changed, where it
changed, why the change exists, and how the release evolved. Unstructured
commits make the repository harder to inspect, automate, review, and
maintain.

Commit messages should provide:

- consistent change classification
- clear ownership areas
- roadmap-level traceability
- readable release history

## Input

- The change being committed.
- Its reference: the roadmap item, issue, or release it belongs to.
- The RAC capability area it landed in.

## Instructions

### Commit format

Use:

```text
<type>(<area>): <imperative summary> [reference]
```

Example:

```text
feat(relationships): add validation CLI [roadmap:v0.7.2]
```

This provides type (what kind of change happened), area (where the change
landed), and reference (why the change exists).

### Allowed types

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

### RAC areas

Prefer capability areas rather than file names. Recommended: validate,
inspect, stats, ingest, improve, schema, relationships, artifacts, roadmap,
design, prompt, release.

```text
feat(schema): add template output [roadmap:v0.5.2]

fix(relationships): preserve invalid references [roadmap:v0.7.2]

docs(readme): clarify installation workflow [roadmap:v0.7.3]
```

### Roadmap implementation commit sequence

For roadmap-driven releases, prefer commits that mirror the lifecycle of the
work. Default sequence:

```text
docs(roadmap): refine vX.Y.Z implementation contract [roadmap:vX.Y.Z]

feat(core-area): add core model/schema support [roadmap:vX.Y.Z]

feat(command): expose behavior in CLI [roadmap:vX.Y.Z]

test(core-area): add boundary and fixture coverage [roadmap:vX.Y.Z]

docs(command): update user-facing usage notes [roadmap:vX.Y.Z]

chore(release): prepare vX.Y.Z branch for PR [roadmap:vX.Y.Z]
```

This reflects the preferred RAC delivery flow: define the contract, build
the capability, expose the interface, validate behavior, document usage,
prepare release.

Not every roadmap item requires every commit type. Small releases may only
need:

```text
docs(roadmap): define v0.7.3 scope [roadmap:v0.7.3]

feat(relationships): add JSON validation output [roadmap:v0.7.3]

test(relationships): cover validation output contract [roadmap:v0.7.3]

chore(release): prepare v0.7.3 release [roadmap:v0.7.3]
```

The goal is not commit quantity; it is preserving the implementation story.

### References

Roadmap work — use `[roadmap:<codename>]` (a live roadmap's codename, e.g.
`[roadmap:rac-ci]`, per ADR-094; a frozen/historical series may still cite its
`vX.Y.Z` fence):

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

Issue work — use `[issue:#number]`:

```text
fix(release): align package metadata version [issue:#12]
```

Release maintenance — use `[release:vX.Y.Z]`:

```text
chore(release): publish v0.7.2 package [release:v0.7.2]
```

### Commit summary rules

Commit summaries should use imperative language, describe the change
introduced, remain specific, and avoid implementation noise.

## Output

A commit, or a series of commits, conforming to the format above, with the
maintainer identity on both author and committer and no tool attribution.

## Constraints

When commits are produced with AI assistance, do:

- follow the same commit standard
- describe the actual product change
- preserve human-readable history
- include the artifact path in the body of roadmap commits
  (`Implements rac/roadmaps/...`)

Do not add:

- generated-by footers or "Generated with ..." lines
- AI assistant attribution, including `Co-Authored-By:` trailers that
  name a tool
- tool-specific signatures or session links
  (for example `https://claude.ai/code/...` URLs)

Agent harnesses commonly append these by default. Strip them before
committing — the standard overrides any harness default. The commit belongs
to the project history, not the tool used to create it.

The same rule covers everything an agent publishes to the repository's GitHub
surface — commit author and committer identity, pull request titles and bodies,
and PR, issue, and review comments. None of these may carry tool attribution:
no `Co-Authored-By` trailer naming a tool, no `Generated with Claude Code` line,
no `Generated by Claude Code` comment footer, and no `https://claude.ai/code/...`
session link. The web harness auto-appends some of these by default — a footer
on comments it posts, a session link on commits and PR bodies — and a posted
comment cannot always be edited afterward, so suppress them at the source rather
than relying on stripping. Set the `attribution` setting in
`.claude/settings.json` (`commit` and `pr` to empty strings; this also governs
comment footers), and keep the maintainer identity on commit author and
committer via git config, never a tool identity.

Commit identity: author and committer must both be the maintainer identity
used on `main`, never a tool identity.

```text
Bad:  Author: Claude <noreply@anthropic.com>
Good: Author: Tom Ballard <tom@armytage.co>
```

Agents must set both fields before committing (`--author` plus
`GIT_COMMITTER_NAME` / `GIT_COMMITTER_EMAIL`, or repository `git config`)
and verify before pushing:

```bash
git log -1 --format='%an <%ae> / %cn <%ce>'
```

If either field is wrong, amend and re-push before the work is considered
delivered.

## Examples

Good summary:

```text
feat(relationships): add target validation service [roadmap:v0.7.2]
```

Bad summaries:

```text
relationship work

fix stuff

updates

final changes
```

## Evaluation

A healthy RAC commit history should read like:

```text
docs(roadmap): refine v0.7.2 implementation contract [roadmap:v0.7.2]

feat(relationships): add validation service [roadmap:v0.7.2]

feat(relationships): expose validation CLI flag [roadmap:v0.7.2]

test(relationships): add missing target fixtures [roadmap:v0.7.2]

docs(relationships): document validation workflow [roadmap:v0.7.2]

chore(release): prepare v0.7.2 branch for PR [roadmap:v0.7.2]
```

A future maintainer should understand the release journey without needing
external context.

## Related Decisions

- ADR-047
