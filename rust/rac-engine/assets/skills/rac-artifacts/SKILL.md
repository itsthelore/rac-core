---
name: rac-artifacts
description: Author and maintain RAC (requirements-as-code) Markdown artifacts — requirements, decisions, roadmaps, prompts, designs — using the rac CLI. Use when asked to create, read, validate, update, or link Lore (RAC) artifacts in a project's rac/ directory.
---

# RAC artifacts

RAC models product artifacts as typed, deterministic Markdown files. Five
types exist: requirement, decision, roadmap, prompt, design. Type is
inferred from `##` section headings, never declared. Frontmatter carries
identity only and is machine-generated.

## Hard constraints

- Write artifact files only inside the host project's RAC directory
  (`rac/` by default; if the project keeps artifacts elsewhere, confirm
  the path before writing). Never create or edit RAC artifacts outside
  that directory, and never modify files elsewhere in the project on
  this skill's behalf.
- Never hand-write or alter an artifact `id` or its frontmatter
  identity block. `rac new` mints ids. Do not edit `.rac/config.yaml`.
- Do not invent sections or frontmatter fields. Use `rac schema <type>`
  to see what a type expects.
- Validation must pass before the work is done: `rac validate` exits 0
  and, if the project uses relationship links,
  `rac relationships <dir> --validate` exits 0.

## Create an artifact

```bash
rac new requirement rac/requirements/<slug>.md
```

`rac new <type> <path>` writes the canonical template with a minted id.
It never overwrites an existing file. Then edit the file and replace
every TODO placeholder with real content, keeping the `##` headings
intact. Requirements use testable statements of the form
`- [REQ-001] ...` under `## Requirements`.

If the project has no `.rac/config.yaml` yet, run `rac init` once at the
project root first (optionally `--key <PREFIX>` for the id prefix).

## Read and classify

```bash
rac inspect <file>          # type, confidence, present/missing sections
rac schema                  # list registered types
rac schema <type>           # sections for one type; --template prints a starter
```

An invalid but recognisable file still classifies as its type and then
fails validation — classification and validation are separate.

## Validate

```bash
rac validate <file-or-dir>              # structural checks; exit 0 = pass
rac relationships <dir> --validate      # link integrity across the corpus
```

Treat errors as blocking. Warnings are advisory (commonly a missing
recommended section); fix them when the content exists to fill them.

## Update and improve

```bash
rac improve <file>          # missing required/recommended sections, with prompts
```

Edit the Markdown directly, preserving the heading structure and the
frontmatter block untouched. Re-run `rac validate` after every edit.

## Link artifacts

Linking uses `## Related <Type>` sections (for example
`## Related Decisions`), one artifact id per line. Ids resolve from an
explicit `## ID` section, a `<letters>-<digits>` filename prefix (for
example `adr-004`), or the filename stem. Check a link target resolves
before adding it:

```bash
rac resolve <id> <dir>
rac find <text> <dir>
```

After adding links, run `rac relationships <dir> --validate`.

## Output for automation

Most commands accept `--json` for machine-readable output, and exit
codes follow the documented contract (0 pass, non-zero failure). Prefer
`--json` when a result feeds a script or a decision.
