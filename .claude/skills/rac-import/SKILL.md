---
name: rac-import
description: Reformat ONE existing document (a decision, requirement, design, roadmap, or prompt) into ONE valid RAC (requirements-as-code) artifact, with a mandatory human-review step before any file is written and `rac validate` as the deterministic close. Use when a user wants to import a single existing decision or document into a project's rac/ directory. Single-document only — for multi-format or bulk conversion use the rac-ingest skill.
---

# RAC single-document import

Reshape one existing document into one valid RAC artifact. You propose; the
human ratifies; `rac validate` is the deterministic check. This skill never
adds AI to the RAC core — it runs in the coding agent and uses the `rac` CLI.

## Hard constraints

- **One document in, one artifact out.** If asked to import a directory, a
  whole wiki, or several documents at once, stop and explain that this skill
  handles exactly one document → one artifact by design. For multi-format or
  bulk conversion, point the user to the `rac-ingest` skill.
- **The schema is not yours to invent.** Read the real shape with
  `rac schema <type>` (and `rac schema` for the list of recognised types).
  Use the real section names, the real five artifact types, and the real
  `## Related <Type>` relationship sections. Never guess or hard-code a field,
  type, or relationship kind. If you cannot run `rac schema`, stop and say so.
- **Human review is mandatory and explicit (before any file is written).**
  Present the draft and require the user to confirm or correct **(a) the
  artifact type, (b) the title, and (c) each relationship** before you write
  anything. Relationships are *suggestions to confirm*, never silently
  asserted. The `id` is minted by `rac new` (opaque, system-assigned) — never
  hand-write or choose it; show it after.
- **Close on deterministic validation.** After writing, run `rac validate`.
  If it fails, show the errors and offer to fix them, then re-validate. Never
  leave an invalid artifact behind.
- **No invention.** Reformat only what the source says. Do not invent context,
  consequences, rationale, or requirements. Where a required section has no
  source material, flag the gap and ask the user — do not fill it with
  plausible-sounding text.

## 1. Get the source

Ask the user for the one document — pasted text or a file path — and, if it is
not obvious, what kind of decision or requirement it represents. If they offer
more than one document or a directory, apply the single-document constraint
above before going further.

## 2. Convert (only if not already Markdown)

```bash
rac ingest decision.docx          # preview Markdown on stdout
```

`rac ingest <file>` converts DOCX / PDF / HTML / PPTX / XLSX / Markdown to
Markdown text, preserving structure — it does not judge whether the result is a
valid artifact. Pasted Markdown needs no conversion. Rich formats need the
optional extras (`pip install 'requirements-as-code[ingest]'`, `[ingest-pdf]`,
`[ingest-office]`); the command names the missing extra when one is needed.

## 3. Choose the type and read its real schema

Pick the type with the user (or cross-check with `rac inspect <file>`, which
infers type from `##` headings and reports confidence). Then read the actual
contract:

```bash
rac schema                     # the recognised artifact types
rac schema decision            # required / recommended / optional sections, and
                               # any controlled values (e.g. Status, Category)
rac schema decision --json     # the same, machine-readable
```

Map the source onto *these* section names. Do not introduce sections the schema
does not define.

## 4. Draft the artifact

Reshape the source content under the type's real headings. Keep the author's
own wording where it fits. For each **required** section the source does not
cover, leave it clearly marked as a gap to raise with the user — do not invent
content. (Requirements use testable `- [REQ-001] ...` lines under
`## Requirements`; a `## Status` value, when present, must be one of the
controlled values `rac schema` lists for that type.)

> Normative language: writing requirements with BCP-14 keywords (MUST / SHOULD /
> MAY) is good practice, but note that `rac validate` does not yet enforce them.
> It does warn on vague verbs (support, handle, allow, enable) in requirements.

## 5. Review gate — confirm before writing

Present, in the conversation (not as a file yet):

- the **draft** artifact;
- a short summary: the **chosen type**, the **proposed title**, and any
  **relationships the source explicitly names** (never relationships inferred by
  scanning the repository — that is out of scope);
- every **gap** where a required section had no source material.

Ask the user to confirm or correct the type, the title, and each relationship.
Verify any relationship target actually resolves before proposing it:

```bash
rac resolve <id> rac/
rac find "<text>" rac/
```

Do not write a file until the user has confirmed.

## 6. Write, then validate

On confirmation, scaffold the file (this mints the id and writes the canonical
template — it never overwrites an existing file), then replace the template body
with the confirmed content:

```bash
rac new decision rac/decisions/<slug>.md
```

Write artifacts only inside the host project's RAC directory (`rac/` by default;
confirm the path if the project keeps them elsewhere) under the matching
subfolder (`rac/decisions/`, `rac/requirements/`, `rac/roadmaps/`,
`rac/prompts/`, `rac/designs/`). If the project has no `.rac/config.yaml`, run
`rac init` once at the project root first. Keep the `##` headings and the
frontmatter block intact; never edit the minted `id`.

Then close on validation:

```bash
rac validate rac/decisions/<slug>.md
```

Treat errors as blocking — show them, offer fixes, and re-run until it exits 0.
`rac improve <file> --template` prints section stubs when the content exists to
fill a missing recommended section. If the artifact links to others, finish with
`rac relationships rac/ --validate`.

## Out of scope

- Bulk or batch import, directory crawling, or "migrate my whole wiki" (one
  document → one artifact only; use `rac-ingest` for broader conversion).
- Inferring relationships by scanning the repository — only the links the source
  document itself names, each confirmed by the user.
- Auto-committing the new artifact without the human-review step.
- Inventing facts, context, or rationale not present in the source.
