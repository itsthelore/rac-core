---
name: rac-ingest
description: Convert legacy documents (DOCX, PDF, HTML, PPTX, XLSX, Markdown) into valid, linked RAC (requirements-as-code) artifacts using the rac CLI. Use when asked to add, import, convert, or migrate existing documents into Lore (a project's rac/ directory).
---

# RAC legacy document conversion

Turn an existing document into a valid, linked RAC artifact in five steps:
convert, classify, restructure, mint identity, validate — then link it
into the corpus.

## Hard constraints

- Write artifact files only inside the host project's RAC directory
  (`rac/` by default; if the project keeps artifacts elsewhere, confirm
  the path before writing). Never create or edit RAC artifacts outside
  that directory, and never modify files elsewhere in the project on
  this skill's behalf.
- Never hand-write or alter an artifact `id` or its frontmatter
  identity block. `rac migrate` mints identity for converted documents.
  Do not edit `.rac/config.yaml`.
- Do not invent sections or frontmatter fields. Use `rac schema <type>`
  to see what a type expects.
- Validation must pass before the work is done: `rac validate` exits 0
  and, if the project uses relationship links,
  `rac relationships <dir> --validate` exits 0.

## Convert

```bash
rac ingest spec.docx                              # preview Markdown on stdout
rac ingest spec.docx -o rac/requirements/spec.md  # write into the RAC directory
```

`rac ingest <file>` converts DOCX, PDF, HTML, PPTX, XLSX, and Markdown
(pass-through) to Markdown, preserving structure. It does not judge
whether the result is a valid artifact — that comes next. `-o` never
overwrites an existing file unless `--force` is passed. Rich formats need
the optional ingest extras (`pip install 'rac-core[ingest]'`
for DOCX/HTML, `[ingest-pdf]`, `[ingest-office]`, or `[ingest-all]`); the
command names the missing extra when one is needed.

## Classify

```bash
rac inspect <file>          # type, confidence, present/missing sections
```

Type is inferred from `##` section headings, never declared. An invalid
but recognisable file still classifies as its type; Unknown means no
schema matched well enough yet.

## Restructure

Compare the converted file against the intended type's schema and rework
the `##` headings until classification matches:

```bash
rac schema <type>              # required / recommended / optional sections
rac schema <type> --template   # the canonical starter, for reference
```

Rename headings to the schema's section names and move the converted
content under them; keep the original wording where it fits. Re-run
`rac inspect` after each pass until the intended type reports with solid
confidence.

## Mint identity

```bash
rac migrate metadata <dir> --dry-run   # preview what would gain identity
rac migrate metadata <dir>             # assign canonical frontmatter
```

`rac migrate` writes the canonical frontmatter envelope (schema version,
a system-assigned id, the classified type) onto recognised artifacts that
lack one; the Markdown body is preserved byte-for-byte. It requires an
initialised repository — run `rac init` once at the project root if
`.rac/config.yaml` does not exist. Files that already carry frontmatter
are never touched, and documents that do not classify are listed, never
guessed at.

## Validate

```bash
rac validate <file>
```

Treat errors as blocking. Warnings are advisory (commonly a missing
recommended section); use `rac improve <file> --template` for stubs when
the content exists to fill them.

## Link

Linking uses `## Related <Type>` sections (for example
`## Related Decisions`), one artifact id per line. Check a link target
resolves before adding it:

```bash
rac resolve <id> <dir>
rac find <text> <dir>
```

After adding links, run `rac relationships <dir> --validate`.

## Output for automation

Most commands accept `--json` for machine-readable output, and exit
codes follow the documented contract (0 pass, non-zero failure). Prefer
`--json` when a result feeds a script or a decision.
