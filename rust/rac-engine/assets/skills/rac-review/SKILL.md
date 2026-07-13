---
name: rac-review
description: Review and triage a RAC (requirements-as-code) corpus using the rac CLI — work prioritised findings worst-first until validation and relationship checks pass. Use when asked to review, triage, or fix findings across a project's Lore corpus (the rac/ directory).
---

# RAC corpus review

`rac review <dir>` validates every artifact, checks every relationship, and
reports findings grouped by priority, worst first. This skill is the
procedure for working that report down: blocking findings first, then
advisory ones, re-validating after each fix.

## Hard constraints

- Write artifact files only inside the host project's RAC directory
  (`rac/` by default; if the project keeps artifacts elsewhere, confirm
  the path before writing). Never create or edit RAC artifacts outside
  that directory, and never modify files elsewhere in the project on
  this skill's behalf.
- Never hand-write or alter an artifact `id` or its frontmatter
  identity block. Do not edit `.rac/config.yaml`.
- Do not invent sections or frontmatter fields. Use `rac schema <type>`
  to see what a type expects.
- The work is done only when `rac validate <dir>` and
  `rac relationships <dir> --validate` both exit 0.

## Run the review

```bash
rac review <dir>            # findings grouped by priority, worst first
rac review <dir> --json     # stable contract for scripted triage
```

Exit 1 means blocking findings exist; exit 0 with findings means only
advisory items remain. Findings are grouped by priority:

1. Invalid artifacts — validation errors (blocking)
2. Broken relationships — unresolvable references (blocking)
3. Unrecognized artifacts — no schema matched (advisory)
4. Missing recommended information (advisory)

Work strictly in priority order. Each finding carries a suggested action;
start from it.

## Mechanical findings — missing sections

Missing recommended sections are mechanical: the fix is adding the section
with real content.

```bash
rac improve <file>             # missing sections, with guidance prompts
rac improve <file> --template  # Markdown stubs for the missing sections
```

Paste the stub, then replace its placeholder text with real content. Do
not add a section purely to silence a finding — when no real content
exists, an advisory finding may stand.

## Judgement findings — broken or ambiguous references

A reference under a `## Related ...` section that points at nothing, at
more than one artifact, or at a duplicated identifier needs investigation,
not a template. Check what the reference actually resolves to:

```bash
rac resolve <id> <dir>    # resolved, not found, or duplicate
rac find <text> <dir>     # locate the artifact the reference meant
```

- Not found: the target was renamed, moved, or never existed. Find the
  intended artifact with `rac find` and correct the reference to an
  identifier that resolves.
- Ambiguous or duplicate identifier: more than one artifact answers to
  the same identifier. Fix the duplicated identity — typically a repeated
  `## ID` value or two files sharing an aliased filename — never by
  editing a frontmatter `id`.
- Self-reference: an artifact lists itself; remove the entry.

## Re-validate after each fix

```bash
rac validate <dir>
rac relationships <dir> --validate
```

Run both after every fix, not once at the end — a fix can introduce a new
finding. Finish by re-running `rac review <dir>` to confirm the blocking
findings are gone.

## Output for automation

Most commands accept `--json` for machine-readable output, and exit
codes follow the documented contract (0 pass, non-zero failure). Prefer
`--json` when a result feeds a script or a decision.
