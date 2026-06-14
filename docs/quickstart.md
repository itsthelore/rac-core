# Quickstart

Try RAC in about five minutes. You will install the tool, scaffold your first
artifact, and run the three commands you'll use most: `validate`, `inspect`, and
`improve`.

## 1. Install

RAC is a Python package (requires Python 3.11+). Install it with `pip`:

```bash
pip install requirements-as-code
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install requirements-as-code
```

This puts a single command on your path: `rac`. Check it:

```bash
rac --version
```

## 2. Create your first artifact

The fastest path is one command. From your repository root:

```bash
rac quickstart
```

That establishes your repository identity (`.rac/config.yaml`) and scaffolds a
first requirement under `rac/requirements/first-requirement.md`, then prints the
single next step — `rac validate <path>`. Edit the `TODO` placeholders and you
have a valid artifact. Use `--type decision` (or any name from `rac templates`)
to start with a different artifact type.

> Prefer the steps explicitly? `rac init` establishes the identity namespace and
> `rac new <type> <path>` scaffolds one artifact; `rac quickstart` just does both
> at once for an empty corpus. See [cli.md](cli.md).

If you would rather hand-author the file, scaffold the body from a schema
template instead:

```bash
rac schema requirement --template > login-flow.md
```

That writes a starter file with the sections a requirement should have. Open it and
replace the `TODO` placeholders with your own content. For this walkthrough, use:

```markdown
# Login Flow

## Problem

Users need a secure, reliable way to sign in to their account. Today there is no
first-class authentication flow, so access control is inconsistent across the app.

## Requirements

- [REQ-001] Users can authenticate with an email address and password.
- [REQ-002] Invalid credentials show a clear, non-revealing error message.
- [REQ-003] A successful sign-in redirects the user to their dashboard.

## Success Metrics

- 95% of sign-in attempts complete in under 2 seconds.
- Authentication-related support tickets drop by half within one quarter.
```

> RAC classifies artifacts by their `##` section headings — no front matter to
> memorize. (Identity ids in frontmatter are assigned for you by `rac new` and
> `rac quickstart`.) See [artifacts.md](artifacts.md).

## 3. Validate it

`validate` checks a file (or a whole directory) for structural problems:

```bash
rac validate login-flow.md
```

```text
PASS  login-flow.md
  warning [missing-risks] login-flow.md
          No ## Risks section (optional, but recommended).

0 error(s), 1 warning(s).
```

The file passes (exit code `0`). The warning is advisory — `## Risks` is recommended
but not required.

## 4. Inspect it

`inspect` tells you what RAC thinks the file is and how complete it is:

```bash
rac inspect login-flow.md
```

```text
Artifact Type: Requirement
Confidence: 71%

Present Sections:
  ✓ Problem
  ✓ Requirements
  ✓ Success Metrics

Missing Sections:
  ✗ Risks
  ✗ Assumptions
```

## 5. Improve it

`improve` suggests what to add next:

```bash
rac improve login-flow.md
```

```text
Artifact Type: Requirement

Missing Required:
  (none)

Missing Recommended:
  - Risks
      • What could prevent successful delivery?
      • What dependencies or unknowns exist?
  - Assumptions
      • What are you assuming to be true?
      • What would change the approach if it turned out false?
```

Add a `## Risks` and `## Assumptions` section and run `rac inspect` again to watch
the confidence climb.

## Where to go next

- [cli.md](cli.md) — every command, its flags, and its exit codes.
- [artifacts.md](artifacts.md) — the five artifact types and their sections.
- [relationships.md](relationships.md) — link artifacts together and validate the links.
- [repo-workflow.md](repo-workflow.md) — organize a whole repository with RAC.
