# CLI Reference

RAC ships a single command, `rac`, with twenty-two subcommands. This page documents each
one: its purpose, inputs, outputs, and exit codes.

```bash
rac <command> [arguments] [options]
rac --version
rac <command> --help
```

## Conventions

These apply across every command.

- **`--json`** — most commands accept `--json` to emit machine-readable output
  instead of the human-readable report. JSON output is a stable contract intended
  for tools, IDEs, CI, and agents.
- **Standard input** — `validate`, `inspect`, and `improve` accept `-` in place of a
  file to read Markdown from stdin (e.g. `cat file.md | rac validate -`).
- **Recursion** — directory commands (`validate`, `stats`, `inspect`,
  `relationships`, `review`, `portfolio`, `index`, `explorer`) recurse into
  subdirectories by default. Pass `--top-level`
  to scan only the immediate directory. `--recursive` is accepted explicitly for
  clarity but is already the default.
- **Exit codes** — every command follows the same convention:

  | Code | Meaning |
  | --- | --- |
  | `0` | Success |
  | `1` | Validation or relationship check failed |
  | `2` | Usage or I/O error (bad arguments, file not found, not a directory) |

---

## validate

Validate an artifact — or every artifact in a directory — for structural and
content issues.

- **Input:** `rac validate <path>` — a Markdown file, a directory, or `-` for stdin.
- **Options:** `--json` · `--top-level` · `--recursive` (directory mode) ·
  `--corpus DIR` (stdin / single-file mode — see below)
- **Exit codes:** `0` no errors · `1` validation errors · `2` path not found / unreadable

```bash
rac validate login-flow.md
```

```text
PASS  login-flow.md
  warning [missing-risks] login-flow.md
          No ## Risks section (optional, but recommended).

0 error(s), 1 warning(s).
```

Warnings do not fail the run; only errors return exit `1`. Use `--json` for the
structured form (`valid`, `errors[]`, `warnings[]` with stable `code` fields).

Given a directory, `validate` classifies every `*.md` file and validates each
against its own artifact schema:

```bash
rac validate rac/
```

```text
PASS  rac/ — 66 artifact(s) checked: 66 valid, 24 skipped (unknown type).
```

Files that match no known schema are **skipped**, not failed — being a plain
document is a valid outcome (see [ADR-010](artifacts.md#documents-vs-artifacts)).
Only validation *errors* in recognized artifacts fail the run. The `--json` form
reports `summary` counts plus a per-file `files[]` list with `status`
(`valid` / `invalid` / `skipped`) and issues.

### Corpus-aware single-document validation (`--corpus`)

Plain `rac validate -` is single-document: it cannot resolve cross-artifact
references, so it cannot tell that a *proposed* edit introduces a reference to a
decision the team has retired. Pass `--corpus DIR` (with stdin `-` or a single
file) to validate the proposed document **and** resolve its outbound references
against the live corpus at `DIR`:

```bash
cat proposed-roadmap.md | rac validate - --corpus rac/
```

```text
FAIL  -

Corpus references
  Related Decisions:
  ✗ adr-014-legacy-auth superseded

0 error(s), 0 warning(s), 1 corpus reference finding(s).
```

- **Input:** the proposed document on stdin (`-`) or a single file; `--corpus`
  points at the corpus directory.
- **What it checks:** the document's own structural validation (exactly as
  without `--corpus`), **plus** the document's references resolved against the
  corpus — references to **retired** (superseded/deprecated) or **missing**
  decisions, and other reference findings (wrong target type, etc.). Only the
  proposed document's *own* outbound references are reported; pre-existing corpus
  findings are not.
- **Exit codes:** `0` clean · `1` any structural error **or** any corpus
  reference finding · `2` usage (`--corpus` with a directory target, or a
  `--corpus` path that is not a directory).
- **Editing an existing artifact:** when the proposed document carries the same
  canonical identity as an on-disk artifact (its frontmatter `id` or `## ID`),
  that on-disk counterpart is excluded from the corpus index, so the edit is
  validated as a *replacement* — no spurious duplicate-identity or
  self-reference finding. A stdin document identified only by path (`-`) does not
  collide and is validated against the whole corpus as-is.

This is the engine seam the generated Claude Code pre-edit hook pipes proposed
content into; see [Agent integration](governance.md#agent-integration-context-supply-and-enforcement).
Validation stays in `rac` — the hook computes nothing
([ADR-067](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-067-agent-integration-boundary.md),
[ADR-063](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-063-non-python-clients-are-thin.md)).

---

## diff

Compare two versions of a requirement file and report what changed.

- **Input:** `rac diff <old> <new>` — two Markdown files.
- **Options:** `--json`
- **Exit codes:** `0` success · `2` file not found / unreadable

```bash
rac diff examples/example_dashboard_v1.md examples/example_dashboard_v2.md
```

```text
Added Requirements

+ REQ-004 User can schedule a weekly usage summary email

Removed Requirements

- REQ-003 User can export the current chart as a CSV file

Modified Requirements

~ REQ-002
  Before: User can filter usage charts by date range
  After:  User can filter usage charts by date range and by team
```

---

## stats

Summarize a directory of artifacts: counts, quality signals, and per-type breakdowns.

- **Input:** `rac stats <directory>` — scanned recursively for `*.md`.
- **Options:** `--json`
- **Exit codes:** `0` analyzable content found, or an empty corpus (day-one is
  not a failure) · `1` files exist but none are valid known artifacts · `2` not
  a directory

On an empty corpus, `stats` (like `validate`, `review`, and `portfolio`) exits 0
and prints a next-step line pointing at `rac quickstart`. The summary JSON
carries an additive `empty` boolean.

```bash
rac stats rac/
```

Reports feature/requirement/decision/roadmap/design counts, missing recommended
sections, and a list of files that matched no schema (not errors — see
[ADR-010](artifacts.md#documents-vs-artifacts)).

---

## ingest

Convert a document (DOCX, PDF, HTML, PPTX, XLSX, or Markdown) into RAC-compatible
Markdown.

- **Input:** `rac ingest <file>` — the source document.
- **Options:** `-o, --output <path>` (write to a file; errors if it exists unless
  `--force`) · `--stdout` (explicit stdout, the default) · `--force` · `--json`
- **Exit codes:** `0` success · `1` conversion failed · `2` unsupported type / file not found / output exists without `--force`

```bash
rac ingest spec.docx                 # preview Markdown on stdout
rac ingest spec.docx -o spec.md      # write to a file
rac ingest report.pdf -o report.md --force
```

Conversion uses optional extras. Install the readers you need:
`pip install 'requirements-as-code[ingest]'` (DOCX/HTML), `[ingest-pdf]`,
`[ingest-office]` (PPTX/XLSX), or `[ingest-all]`.

---

## inspect

Identify a document's artifact type and which sections are present or missing. Works
on a single file or a whole directory.

- **Input:** `rac inspect <file|directory>` — or `-` for stdin (single file only).
- **Options:** `--json` · `--verbose` (classification breakdown and score, single
  file only) · `--top-level` · `--recursive`
- **Exit codes:** `0` (a completed inspection always succeeds — `Unknown` is a valid result)

```bash
rac inspect login-flow.md
rac inspect . --json            # aggregate type counts for a directory
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

---

## improve

Suggest the sections an artifact is missing, optionally as ready-to-paste templates.

- **Input:** `rac improve <file>` — or `-` for stdin.
- **Options:** `--json` *or* `--template` (mutually exclusive)
- **Exit codes:** `0` (suggestions are advice, not failure)

```bash
rac improve login-flow.md             # list missing sections
rac improve login-flow.md --template  # emit Markdown stubs to paste in
```

---

## schema

Show registered artifact schemas and starter templates.

- **Input:** `rac schema [name]` — `requirement`, `decision`, `roadmap`, `prompt`, or `design`.
- **Options:** `--list` (list all schema names) · `--json` *or* `--template`
  (mutually exclusive) · `--list` cannot be combined with a schema name
- **Exit codes:** `0` success · `2` unknown schema name or flag misuse

```bash
rac schema --list                  # the five artifact types
rac schema requirement             # required / recommended / optional sections
rac schema decision --template     # starter Markdown for a decision
rac schema roadmap --json          # machine-readable schema
```

---

## relationships

Inspect — and optionally validate — explicit references between artifacts in a file
or directory.

- **Input:** `rac relationships <path>` — a directory or a single Markdown file.
- **Options:** `--validate` (resolve every reference; exit `1` on any broken,
  ambiguous, self-referencing, or duplicate-identifier finding) · `--json` ·
  `--top-level` · `--recursive`
- **Exit codes:** `0` relationships found / all references valid · `1` validation
  issues · `2` path not found

```bash
rac relationships rac/              # list the references RAC discovered
rac relationships rac/ --validate   # check that every reference resolves
```

Finding no relationships is **not** an error. See [relationships.md](relationships.md)
for the issue codes `--validate` reports.

---

## rename

Safely rename an artifact id across the whole corpus. Renaming an id by hand
corrupts links — every inbound reference to the old id silently dangles. `rac
rename` computes the corpus-wide edit set deterministically and reversibly, so the
references and the artifact's own identity move together. The engine owns the edit
set; editors and other clients preview and invoke it, never computing references
themselves (ADR-063).

- **Input:** `rac rename <old-id> <new-id> <directory>` — the existing id (or one
  of its aliases), the new human id (e.g. `ADR-099`), and the corpus to scan.
- **Options:** `--apply` (write the edits; default is a dry-run preview) · `--json`
  (the stable plan/result contract, ADR-007) · `--top-level`
- **Exit codes:** `0` a valid plan was previewed (dry run) or applied · `1` the
  rename was **refused** (`old-id` not found or ambiguous, `new-id` invalid or
  colliding, or `old-id` is only a filename-derived alias) — nothing is written ·
  `2` not a directory

```bash
rac rename ADR-001 ADR-099 rac/            # dry run — preview the edit set
rac rename ADR-001 ADR-099 rac/ --apply    # apply it; references + identity move together
rac rename ADR-001 ADR-099 rac/ --json     # the plan as a stable dict
```

**What it rewrites.** Two things, deterministically:

1. **Inbound references** — every `## Related X` / `## Supersedes` list line whose
   reference token equals `old-id`. Only the token is replaced; surrounding text is
   preserved verbatim, so `- ADR-001 (blocked)` becomes `- ADR-099 (blocked)` (the
   raw reference text is the source of truth, ADR-016). A line that names a
   *different* alias of the same target is left untouched — the rename operates on
   the `old-id` token specifically.
2. **The target's own identity** — the one declared, editable identity field that
   equals `old-id`: the canonical frontmatter `id`, a `## ID` section value, or the
   type's declared id section. The file is **not** renamed and the canonical
   frontmatter `id` is changed only when `old-id` *is* that value.

**When it refuses.** If `old-id` resolves only through a filename-derived alias
(the filename prefix or stem) there is no in-file token to rewrite without renaming
the file, which is out of scope — so the rename refuses rather than leave `new-id`
dangling. It also refuses an `old-id` that is unknown or ambiguous, and a `new-id`
that is malformed or already names another artifact (which would create a duplicate
identity). Every refusal leaves the corpus untouched and exits `1`.

**Guarantees.**

- **Deterministic** — the same inputs produce a byte-identical plan; edits are
  ordered by path then line (ADR-002).
- **Reversible** — applying `rename <new> <old>` after a rename restores the
  original bytes. No semantic inference happens anywhere.
- **Clean afterwards** — after `--apply`, `rac relationships <dir> --validate` is
  clean: every inbound reference resolves to the renamed artifact.

The `--json` plan is `{ ok, reason, old_ref, new_ref, target_path,
identity_field, files_changed, reference_edits, identity_edits, edits[] }`, where
each edit is `{ path, line, old_line, new_line, kind }` (`kind` is `"reference"` or
`"identity"`). On refusal, `ok` is `false` and `reason` is one of the stable codes
`old-ref-not-found`, `old-ref-ambiguous`, `new-ref-invalid`, `new-ref-collides`,
`old-ref-filename-only`. The `--apply` result is `{ applied, old_ref, new_ref,
target_path, files_changed, reference_edits, identity_edits }`.

In the editor, **RAC: Rename artifact id** runs this dry run, shows the affected
files and lines as a preview, and on confirm applies it — the extension previews
and invokes the engine plan, it never computes references (ADR-063). The
**add relationship** code action inserts a resolvable reference into the right
`## Related X` section, and the missing-section quick-fix bodies are sourced from
`rac schema <type>` so they cannot drift from the canonical schema.

---

## review

Review an entire repository in one command: validate every artifact, check
every relationship, and report what needs attention — worst problems first.

- **Input:** `rac review <directory>` — scanned recursively for `*.md`.
- **Options:** `--json` · `--top-level` · `--recursive` · `--stale-after [DAYS]`
- **Exit codes:** `0` no blocking issues · `1` invalid artifacts or broken
  relationships found · `2` not a directory

```bash
rac review rac/
rac review rac/ --stale-after        # nudge if nothing written in 14 days
rac review rac/ --stale-after 30     # custom window
```

`--stale-after [DAYS]` adds an advisory **write-cadence** finding when no
artifact has been committed within the window (default 14 days when the flag is
given without a value). It is informational and **never** changes the exit code,
so it is safe in CI; it needs git history and is silent outside a git repository
or on an empty corpus. The framing is capture cadence, not work tracking
(ADR-017).

```text
Repository Review
=================

Directory:  rac/
Artifacts:  90

  Requirement    19
  Decision       27
  Roadmap        11
  Design         9
  Unknown        24

Validation
----------

  Valid:    66
  Invalid:  0
...
```

Findings are grouped by priority, highest impact first:

| Priority | Finding | Blocks (exit `1`) |
| --- | --- | --- |
| 1 | Invalid artifacts (validation errors) | yes |
| 2 | Broken relationships (unresolvable references) | yes |
| 3 | Unrecognized artifacts (no schema matched) | no — advisory |
| 4 | Missing recommended information | no — advisory |

Every finding carries a concrete suggested action (`rac validate <file>`,
`rac relationships <dir> --validate`, `rac improve <file> --template`, …) and
an `impact` sentence explaining why it matters (additive in v0.8.11), and
the report ends with the same health score `portfolio` computes. The `--json`
form is a stable contract (`schema_version: "1"`) with `ok`, `artifacts`,
`validation`, `relationships`, `health`, `issues[]` (each with `priority`,
`severity`, `path`, `identifier`, `code`, `message`, `action`, `impact`),
and `actions[]`.

`review` composes the same analysis `portfolio` runs; use `portfolio` for a
one-screen summary and `review` when you want the prioritized worklist.

---

## gate

Enforce a corpus in one command: run validation, relationships, and review, then
classify every finding as **blocking** or **advisory** under the corpus
enforcement policy. The single enforcement entry point — one exit code, one SARIF
document — used by the PR-gate Action.

- **Input:** `rac gate <directory>` — scanned recursively for `*.md`.
- **Options:** `--json` · `--sarif` (mutually exclusive) · `--top-level`
- **Exit codes:** `0` nothing blocking · `1` a blocking finding (or malformed
  `.rac/config.yaml`) · `2` not a directory

```bash
rac gate rac/                # human summary
rac gate rac/ --json         # stable JSON contract (schema_version "1")
rac gate rac/ --sarif        # one SARIF 2.1.0 document over all findings
```

Which findings block versus merely annotate is governed by an optional
`enforcement:` section in `.rac/config.yaml` (`blocking` / `advisory` / `off`
lists of finding codes). With no policy, the gate's verdict is exactly
`validate ∧ relationships ∧ review`. The `--json` envelope carries `ok`,
`blocking_count`, `advisory_count`, and `findings[]` (each with `source`, `code`,
`severity`, `enforcement`, `path`, `line`, `message`); `--sarif` emits one
combined document for GitHub Code Scanning. See
[Governance](governance.md) for the policy shape and fleet-readiness guidance.

---

## watchkeeper

Review product knowledge *changes* between two repository states: what was
added, modified, or removed, and how validation, relationships, and repository
statistics moved. `review` answers "what needs attention now?"; `watchkeeper`
answers "what changed, and how did it move the repository?".

- **Input:** `rac watchkeeper [directory]` — the corpus to compare (default:
  `rac/` when present, else the current directory). The working tree is the
  head state.
- **Options:** `--base REF` (default `main`) · `--head REF` ·
  `--format human|json|github` · `--json` (alias for `--format json`) ·
  `--fail-on error|warning|none` (default `error`) · `--no-annotate`
- **Exit codes:** `0` nothing requiring attention under the chosen policy
  (always, with `--fail-on none`) · `1` review recommended (`--fail-on
  error`) or any warning finding (`--fail-on warning`) · `2` not a
  directory, unknown revision, or not inside a git repository

`--base` and `--head` each accept a git revision (`main`,
`origin/some-branch`, a commit SHA) **or** an existing directory path —
directories are compared as-is, with no git involved. Revisions are
materialized read-only via `git archive` (ADR-043): nothing mutates your
repository, and only the corpus subpath is extracted.

```bash
rac watchkeeper rac --base main
```

```text
RAC Watchkeeper
===============

Directory:  rac
Comparing:  main → rac

Changed Artifacts
-----------------

  + requirements/billing.md  (requirement)
  ~ requirements/checkout.md  (requirement)
  - requirements/legacy-upload.md  (requirement)

Validation
----------

  Valid:    5 → 4
  Invalid:  0 → 1

  Newly invalid:
    ✗ requirements/payouts.md

Relationships
-------------

  Total:    3 → 3
  Broken:   0 → 1

  New issues:
    ! decisions/adr-001-payment-provider.md — Related Requirements reference 'legacy-upload' (relationship-target-not-found)

Repository Changes
------------------

  Requirement    3 → 3
  Total          5 → 5
```

Artifacts are matched by corpus-relative path, so a renamed artifact reports
as removed plus added. A base revision that predates the corpus directory
compares against an empty base — a brand-new corpus is a valid
"everything added" review.

The report ends with deterministic **intent findings** (v0.12.1) — changes
that reduce product clarity, flagged for human attention without judging
correctness:

| Code | Fires when | Severity |
| --- | --- | --- |
| `specificity_regression` | a measurable requirement loses its numbers | warning |
| `ambiguity_introduced` | an ambiguous term (easy, intuitive, simple, seamless, user-friendly, scalable, fast, quickly, robust, flexible) newly appears in a requirement | warning |
| `constraint_weakened` | mandatory wording (must, shall) becomes hedged (should, may, could) | warning |
| `constraint_removed` | a requirement with mandatory wording is removed | warning |
| `acceptance_criteria_removed` | a filled Acceptance Criteria section disappears or empties | warning |
| `success_measures_removed` | a filled Success Measures/Metrics section disappears or empties | warning |
| `unlinked_scope` | a new artifact declares no relationships and nothing references it | warning |
| `relationship_impact` | a modified or removed artifact is referenced by others | info |

Every check is token-boundary, casefolded, and explainable: each finding
carries a one-sentence `detail` and the triggering text as diff-style
`evidence`.

```text
Findings (2)
--------

  ! [specificity_regression] requirements/checkout.md
      Measurable requirement REQ-001 became vague.
      - Payment confirmation must complete within 2 seconds
      + Payment confirmation should complete quickly

  · [relationship_impact] requirements/checkout.md
      Modified artifact is referenced by 1 artifact(s).
      adr-001
```

The report ends with a deterministic **review verdict** (v0.12.2). Review
is recommended when artifacts become invalid, relationship references
break, or a clarity-regression finding fires (`specificity_regression`,
`constraint_weakened`, `constraint_removed`, `acceptance_criteria_removed`,
`success_measures_removed`). Ambiguity, unlinked scope, and relationship
impact inform but never recommend on their own. `--fail-on` turns the
verdict into CI policy: `error` (default) fails when review is recommended,
`warning` also fails on any warning finding, `none` never fails but still
prints the full report.

`--format github` renders for GitHub workflows with no GitHub API
dependency: **stdout** is a Markdown report for `$GITHUB_STEP_SUMMARY`
(change table, delta tables, findings, verdict); **stderr** carries
workflow-command annotations (`::error` for recommendation triggers,
`::warning` / `::notice` for the rest) with repository-relative file paths,
which the runner turns into inline annotations. `--no-annotate` suppresses
the stderr stream:

```bash
rac watchkeeper rac --base "origin/$GITHUB_BASE_REF" --format github > "$GITHUB_STEP_SUMMARY"
```

The `--json` form is a stable contract (`schema_version: "1"`) with `base`,
`head`, `directory`, `changes[]` (each with `change`, `type`, `id`, `title`,
`path`, `base_status`, `head_status`, and a requirement-level `diff` for
modified artifacts), `validation` (per-side counts plus `newly_invalid` /
`newly_valid`), `relationships` (per-side summaries plus `new_issues` /
`resolved_issues`), `stats` (per-type and total counts for both sides),
`findings[]` (each with `code`, `severity`, `path`, `identifier`, `detail`,
`evidence`; additive in v0.12.1), and `review` (`recommended` plus
`reasons[]` with `code` and `reason`; additive in v0.12.2).

To run Watchkeeper on pull requests with the bundled GitHub Action and
reusable workflow, see **[watchkeeper.md](watchkeeper.md)**.

---

## portfolio

A one-screen repository intelligence summary: artifact counts by type, validity,
completeness, relationship coverage, an attention list, and a health score.

- **Input:** `rac portfolio <directory>` — scanned recursively for `*.md`.
- **Options:** `--json` · `--top-level` · `--recursive`
- **Exit codes:** `0` success · `2` not a directory

```bash
rac portfolio rac/
```

---

## index

Produce a flat inventory of every artifact — id, type, title, and path — so other
tools can build navigation without re-scanning files.

- **Input:** `rac index [directory]` — defaults to the current directory; scanned
  recursively for `*.md`.
- **Options:** `--json` · `--top-level` · `--recursive`
- **Exit codes:** `0` success · `2` not a directory

```bash
rac index rac/
rac index rac/ --json
```

```json
{
  "schema_version": "1",
  "directory": "rac/requirements/",
  "recursive": true,
  "artifact_count": 4,
  "artifacts": [
    {
      "id": "rac-documentation-structure",
      "type": "unknown",
      "title": "REQ-Documentation-Structure",
      "path": "rac/requirements/rac-documentation-structure.md"
    }
  ]
}
```

---

## export

Project the corpus into a derived view. One walk, several mutually-exclusive
modes; the default writes the viewer JSON payload to stdout. Exports are build
artifacts — existing output is overwritten.

- **Input:** `rac export [directory]` — scanned recursively for `*.md` (default: current directory).
- **Modes:** *(default)* viewer JSON to stdout · `--html` (self-contained Portal file) · `--okf` (OKF v0.1 Markdown bundle) · `--documents` (JSONL for memory/RAG backends) · `--graph` (typed node+edge JSON for graph backends) · `--agent-rules` (per-client agent-context files; see its own behaviour)
- **Options:** `--out <path>` (only `--html`/`--okf`/`--agent-rules`; the stdout modes are pipeable) · `--json` (no-op for the default mode)
- **Exit codes:** `0` success · `2` not a directory, or `--out` given to a stdout mode

```bash
rac export rac/                      # viewer JSON to stdout
rac export rac/ --documents          # JSONL, one record per artifact
rac export rac/ --graph              # typed node+edge graph
rac export rac/ --html --out lore.html
```

### Exporting to external memory / RAG / graph backends

`--documents` and `--graph` exist to feed RAC's recorded decisions into the tools
teams already run, so an agent can recall fuzzily there and then **verify in
Lore**. They are additive (ADR-007): the default viewer JSON is unchanged, and
nothing here computes embeddings — that stays in the consuming backend (ADR-002,
ADR-066). The connectors themselves live in the separate `lore-connectors`
companion, one module per backend rather than a repo per provider (ADR-073).

**What it exports to, by name.** The shapes are deliberately the common
ingestion denominators, so most targets need no bespoke code:

- **`--documents` (JSONL, one record per artifact)** — memory layers
  (**Supermemory**, **Mem0**, **Zep**, **Letta**, **Cognee**) and vector stores
  (**Pinecone**, **Weaviate**, **Qdrant**, **Chroma**, **Milvus**, **pgvector**,
  **LanceDB**). Each line is `{schema_version, id, type, status, title, text,
  metadata{path, aliases, tags, source}}`, where `text` is the artifact's
  Markdown body. The first shipped connector targets Supermemory:
  each line maps to `add({ content: text, containerTag: source, metadata })`.
- **`--graph` (one node+edge JSON object)** — graph / GraphRAG backends
  (**Neo4j**, **Zep Graphiti**, **Cognee**, **Microsoft GraphRAG**). Nodes are
  `{id, type, status, title}`; edges carry the real relationship kind
  (`supersedes`, `related_*`) and direction, so the backend gets RAC's validated
  decision graph instead of one inferred from prose.

**How the answer is then validated (verify-in-Lore).** The backend gives
*recall*; Lore gives the *authoritative answer*. After a backend surfaces a
candidate, the agent:

1. reads the canonical `id` from the record's metadata (or the node/edge);
2. re-fetches the current artifact from Lore by that `id` (the `get_artifact`
   MCP tool, or `rac resolve`);
3. uses Lore's lifecycle status to drop a retired or superseded decision
   (`find_decisions` filters these);
4. acts on **Lore's verbatim text**, never the backend's possibly-rewritten copy.

RAC does not validate or sync the backend's store — verification happens on
read, in Lore. The exported copy is a pointer, kept fresh by re-running the
export; the canonical `id` is what makes the round-trip reliable.

---

## explorer

Launch the interactive terminal Explorer — browse every artifact, read it in
full, assess repository health, and reach anything through the `/` command
palette, without memorizing RAC commands. One persistent workspace frame: a
navigation sidebar of type-tagged artifacts on the left, a context panel
that swaps views on the right, and a status line of key hints with the
health chip — under the rac-lantern theme by default. Pressing `/` summons
the palette (v0.8.8): an input with a live, navigable suggestion menu below
it. The workspace is live (v0.8.9): Explorer watches the repository and
reloads itself when artifacts change on disk.

Explorer is a presentation layer over the same services the CLI uses: everything
it shows is also available through `rac portfolio`, `rac index`, `rac resolve`,
`rac find`, and friends (ADR-015). It never edits artifacts (ADR-024).

- **Input:** `rac explorer [directory]` — defaults to `rac/` when present
  (ADR-018), else the current directory; scanned recursively for `*.md`.
- **Options:** `--top-level` · `--recursive` (no `--json`: the surface is interactive)
- **Keys:** `/` summons the command palette from anywhere · `↑ ↓` navigate ·
  `Enter` select · `Tab` cycle panels · `Esc` back (palette → dismiss;
  context → view history; otherwise → home) · `h` health · `r` reload ·
  `f` filter results by type · `?` help · `q` quit. Single-letter shortcuts
  are suspended while you type in the palette.
- **Palette (`/`):** empty input offers the artifacts you opened most
  recently in this repository (Enter reopens one) above the full command
  list; a command prefix filters them (Enter completes argument-taking
  commands into the input); any other text shows live artifact matches —
  Enter quick-opens the highlighted one — plus a "search all results" row.
  Commands: `open <ref>` · `find <query> [type]` · `browse [type]` ·
  `list [type]` · `health` · `stats` · `recommendations` · `new <type> <path>` ·
  `import <source> [target]` · `relationships <ref>` · `resume` ·
  `schema [type]` · `settings` · `home` · `help` · `quit` — anything else is
  a search, resolved with `rac resolve` / `rac find` semantics. Full results render in the context panel (the layout
  never jumps), where `f` narrows artifact results by type — all → each type
  present → all. `/browse <type>` lists that type in the results panel in
  every grouping mode; bare `/browse` focuses the sidebar. `/schema` lists
  the registered artifact types; `/schema decision` renders the type's
  expected sections, the same facts `rac schema` reports.
- **Sidebar:** every artifact under "Artifacts", mirroring the repository's
  directory structure by default — directories as collapsible nodes (name
  with a trailing `/` and an artifact count), nested exactly as on disk.
  The `artifact_grouping` setting cycles `folders` | `type` | `flat`. Rows
  carry a colour-coded type tag (`REQ` `ADR` `RMP` `PRM` `DSG`) beside the
  title, invalid artifacts are marked `✗`, and the highlighted artifact's
  status chip shows in the panel border. `e` opens the highlighted artifact
  in your editor. Expansion and cursor survive reloads — nested directories
  included — and opening an artifact reveals it along its filesystem path;
  the sidebar hides below 80 columns.
- **Artifact context:** opening an artifact shows four tabs — **Content**
  (the document's rendered Markdown, read-only — the default; it takes the
  keyboard, scrolls with `j`/`k`/PgUp/PgDn, and artifact references inside
  the text open in place, so the corpus reads like a wiki), **Inspection**
  (status, completeness, and the artifact's validation diagnostics — the
  same issues `rac validate` reports), **Links** (the knowledge graph as
  text — a dependency chain to what the artifact relates to, an Impact
  Analysis block naming what a change may affect, and a lineage chain;
  connected artifacts open on Enter, so the graph traverses one hop at a
  time and `Esc` unwinds), and **Findings** (the artifact's
  recommendations, plus an Improvement group from the improve service —
  one suggestion per missing section, with the schema's guidance question
  as the action). Inspection, Links, and Findings carry count badges; `g`
  jumps to Links; `←`/`→` switch tabs.
- **Health:** `h` or `/health` opens the health view — Core's score with a text
  label, the Completeness / Relationships / Validation / Coverage areas, and a
  prioritized attention list whose items open the affected artifact on its
  Inspection tab, where the diagnostics explain the finding.
- **Recommendations:** `/recommendations` (or `r` from the health view) presents
  Core's review findings grouped by category (Validation, Relationships,
  Repository Health, Quality), each with its impact, a suggested `rac` command,
  and navigation to the affected artifact's Findings tab. Advisory only —
  Explorer applies nothing. `x` exports them to a Markdown file (preview,
  then confirm).
- **Actions:** `e` opens the current artifact in your editor — the `editor`
  setting, then `$VISUAL` / `$EDITOR`; terminal editors (vim, nvim, emacs,
  nano, …) run with the Explorer suspended and resume it on exit; guidance
  is shown when nothing is configured (Explorer never edits, ADR-024).
  `/import <source> [target]` converts a document via the ingest service,
  previews the Markdown, and writes it only after you confirm with `y`
  (never overwriting). Long conversions report progress.
  `/new <type> <path>` starts an artifact from its canonical template: the
  preview shows the sections with the ID noted as assigned on write, `y`
  confirms, and the write goes through the same Core service as `rac new` —
  the ID is minted against the repository index, existing files refuse,
  missing directories refuse, and an uninitialized repository points you at
  `rac init`. On success the Explorer reloads and opens the new artifact,
  ready for `e`; bare `/new` lists the creatable types.
- **Stats:** `/stats` opens a portfolio dashboard — per-type counts with
  validity, requirement/metric/risk totals, decision status and category
  breakdowns, and relationship counts — the same facts `rac stats` reports,
  collected off the UI thread on request.
- **Portfolio list:** `/list` opens a sortable table of every artifact — type
  tag, id, status, link count, recency, and title. `/list <type>` (for example
  `/list decision`) scopes it to one artifact type, and `/list <text>` (anything
  that is not a type) runs a fuzzy name search; `s` cycles the sort (type,
  recency, links, status, id), `f` the status filter (all, invalid, valid), and
  `ctrl+f` focuses the same name search live in the box. Enter opens the
  highlighted artifact. The type scope, status filter, and name search compose,
  and the header names whichever are active. Recency is git-derived (ADR-045),
  so the column fills from a worker after the table is on screen.
- **Live reload:** Explorer compares the corpus files on disk every two
  seconds (paths and mtimes only — no parsing) and reloads when something
  changed: the sidebar keeps its expansion and cursor, the open artifact
  keeps its tab and scroll position, and the health chip updates. The
  watcher holds while a terminal editor owns the screen and rescans the
  moment Explorer resumes, so a saved edit shows immediately; an open
  artifact that disappears falls back home. `r` still reloads on demand.
- **First run:** onboarding derives from repository content (existing, empty, or
  invalid repository) and is skipped for returning users; a lantern-carrying
  mascot animates in the welcome, empty, and loading states (static with
  `animations = off`, hidden with `mascot = off` — no information is lost).
  Selecting the mascot (a click, or keyboard focus then Enter) returns a small
  response inline — an acknowledgement, an occasional reminder, gentle guidance
  toward existing commands, and one rare line — with no popup and nothing
  hidden behind it; turn it off independently with `mascot_interaction = off`.
  One optional editor step follows the welcome: Enter accepts (an empty
  value keeps the `$VISUAL`/`$EDITOR` fallback), typing sets the `editor`
  preference, Esc skips — `/settings` can change it any time.
- **Settings & continuity:** `/settings` changes everything in place — theme
  (three curated RAC themes ship: `rac-lantern`, the dark default;
  `rac-parchment`, a light companion — warm paper, dark ink, the lantern amber
  deepened to read on light; and `rac-high-contrast` — pure-white ink on true
  black for maximum legibility. Enter cycles them and every other Textual theme
  with live preview; all meaning survives any palette, and the artifact type
  tags re-tune their hue to the active theme so they stay legible on light or
  dark), mascot, animations, mascot interaction, artifact grouping
  (`folders` default), workspace layout (`frame` default — the tree sidebar plus
  a swapping context region — or `split`, a master-detail layout where the
  portfolio list drives a persistent reading pane; switching applies live), and
  the editor command —
  persisted to `$XDG_CONFIG_HOME/rac/explorer.json` (no login, cloud, or
  sync). Explorer remembers recently opened repositories plus the last
  artifact and view per repository (under `$XDG_STATE_HOME/rac/`); `.` or
  `/resume` takes you back to where you were.
- **Exit codes:** `0` session quit · `2` not a directory, or the `explorer` extra is
  not installed

The TUI dependency ships as an optional extra, so the core install stays light:

```bash
pip install 'requirements-as-code[explorer]'
rac explorer rac/
```

Without the extra, `rac explorer` prints the install hint above and exits `2`.

---

## mcp

Serve RAC repository knowledge to coding agents over MCP (stdio). The four
read-only tools, client configuration, and team setup are documented in the
[MCP server guide](mcp.md).

```bash
rac mcp --root /path/to/repo
rac mcp --root /path/to/repo --telemetry
```

- **`--root PATH`** — repository root to serve (default: current directory)
- **`--telemetry`** — record tool-call counts and metadata (never arguments
  or content) to a local log under `$XDG_STATE_HOME/rac/` (default
  `~/.local/state/rac/guide-telemetry.jsonl`); off by default, announced on
  stderr when on
- **Exit codes:** `0` server shutdown on client disconnect · `2` `--root` is
  not a directory

---

## mcp-stats

Summarize the local Guide telemetry log: events, sessions, first and last
timestamps, and per-tool calls, errors, truncation, and average duration.
An empty or missing log is a valid answer — telemetry is opt-in and off by
default.

```bash
rac mcp-stats           # human summary
rac mcp-stats --json    # the same summary as JSON (the shareable export)
rac mcp-stats --share   # prefilled GitHub usage-report issue URL
```

`--share` prints a URL that opens a prefilled usage-report issue containing
only counts and timestamps; you review and submit it in your own browser —
RAC sends nothing itself. `--json` and `--share` are mutually exclusive.

- **Exit codes:** `0` summary produced (including from an empty or missing
  log) · `2` usage error

---

## telemetry

Show or change anonymous usage-sharing consent (ADR-041). With consent on,
`rac mcp` sends at most one anonymous daily ping — a random install id, the
version, and an active-repo count; never paths, queries, or repository
content. Sharing is independent of the local `rac mcp --telemetry` flag.

```bash
rac telemetry           # status (default): what is shared, and whether sending is possible
rac telemetry on        # opt in; mints a random install id
rac telemetry off       # opt out; nothing else changes
```

`status` also reports when the build has no endpoint key configured — in
that state nothing is sent even with consent. Consent lives at
`~/.config/rac/telemetry.json`.

- **Exit codes:** `0` consent shown or changed · `2` invalid action

---

## new

Create a new artifact from its canonical bundled template, with a
system-assigned opaque ID written as YAML frontmatter. The generated file uses
the same structure the validators expect: edit the `TODO` placeholders and it
passes `rac validate`.

- **Input:** `rac new <type> <output-path>` — type is `requirement`,
  `decision`, `roadmap`, `prompt`, or `design`; the output path is taken
  literally (no filename derivation, no extension magic).
- **Options:** `--json`
- **Exit codes:** `0` created · `1` packaged template missing or malformed
  repository config · `2` unsupported type, output file already exists, output
  directory missing, or repository not initialized (run `rac init` first)

`rac new` never overwrites an existing file and never creates directories. The
repository key comes from the nearest `.rac/config.yaml` (see [`init`](#init));
the assigned ID is permanent — it survives renames, moves, and type changes.

```bash
rac init
rac new requirement rac/requirements/user-authentication.md
rac new decision rac/decisions/adr-029-example.md --json
```

```json
{
  "schema_version": "1",
  "created": true,
  "type": "decision",
  "path": "rac/decisions/adr-029-example.md",
  "id": "RAC-01JY4M8X2QZ7"
}
```

A generated artifact begins with the canonical metadata envelope:

```markdown
---
schema_version: 1
id: RAC-01JY4M8X2QZ7
type: decision
---
# Title
...
```

---

## templates

List the canonical artifact templates available to `rac new`. The set is the
artifact spec registry itself — the same source that drives classification and
validation.

- **Input:** `rac templates`
- **Options:** `--json`
- **Exit codes:** `0` success

```bash
rac templates
rac templates --json
```

```json
{
  "schema_version": "1",
  "templates": ["requirement", "decision", "roadmap", "prompt", "design"]
}
```


---

## init

Establish the repository identity namespace: a `.rac/config.yaml` holding the
`repository_key` that prefixes every ID assigned by `rac new`. The key is
configuration, not artifact meaning — it never dictates folder structure.

- **Input:** `rac init [directory]` — defaults to the current directory.
- **Options:** `--key KEY` (default `RAC`; 2–10 uppercase alphanumeric
  characters starting with a letter) · `--json`
- **Exit codes:** `0` initialized, or already initialized with the same key
  (idempotent) · `1` a different key is already established (never silently
  rewritten) · `2` invalid key or not a directory

After a successful init on a real terminal, `rac init` asks one one-time
question — "Share anonymous usage to help shape Lore? [y/N]" — defaulting to
No. Either answer is persisted, so it is asked at most once per machine; it
never appears with `--json`, in pipes, or in CI. See `rac telemetry`.

```bash
rac init
rac init --key PROJ
rac init docs/ --json
```

```json
{
  "schema_version": "1",
  "repository_key": "PROJ",
  "config_path": ".rac/config.yaml",
  "created": true
}
```


---

## quickstart

Guided first run: establish the repository identity **and** scaffold a first
artifact in one step. It is `rac init` followed by `rac new`, collapsed into a
single command, so a new user reaches a validatable artifact without assembling
the sequence. It writes one starter artifact (the canonical template, with a
system-assigned id) under `rac/<family>/`, and only into an empty corpus — a
corpus that already holds an artifact is refused, untouched (ADR-044).

- **Input:** `rac quickstart [directory]` — defaults to the current directory.
- **Options:** `--key KEY` (default `RAC`) · `--type TYPE` (default
  `requirement`; any name from `rac templates`) · `--json`
- **Exit codes:** `0` identity established and starter artifact created · `1`
  the corpus already has artifacts, or a different key is established (nothing
  written) · `2` invalid key, unknown type, or not a directory

Like `rac init`, on a real terminal it asks the one-time usage-sharing question
(never with `--json`, in pipes, or in CI).

```bash
rac quickstart
rac quickstart --type decision
rac quickstart docs/ --key PROJ --json
```

```json
{
  "schema_version": "1",
  "repository_key": "RAC",
  "config_path": "./.rac/config.yaml",
  "created": true,
  "artifact": {
    "type": "requirement",
    "path": "rac/requirements/first-requirement.md",
    "id": "RAC-..."
  }
}
```


---

## resolve

Resolve an artifact ID to its type, title, and path. Matching is
case-insensitive and covers canonical IDs and legacy aliases (`## ID` values,
filename prefixes, stems), so lookups survive renames, moves, and identity
migration.

- **Input:** `rac resolve <ID> [directory]` — directory defaults to the
  current directory.
- **Options:** `--json` · `--top-level` · `--recursive`
- **Exit codes:** `0` resolved · `1` not found, or duplicate ID (paths listed
  on stderr; never silently resolved by path order) · `2` not a directory

```bash
rac resolve RAC-01JY4M8X2QZ7 rac/
rac resolve adr-015 rac/ --json
```

```json
{
  "schema_version": "1",
  "id": "RAC-01JY4M8X2QZ7",
  "type": "decision",
  "title": "Markdown Is the Canonical Source Format",
  "path": "rac/decisions/markdown-first.md"
}
```

---

## find

Search artifacts by ID, title, filename, or path — a deterministic,
case-insensitive substring match (no ranking heuristics). Results are ordered
by match field (ID, then title, then filename/path) with sorted path as the
tiebreak. An empty result is a valid outcome, not an error.

- **Input:** `rac find <query> [directory]` — directory defaults to the
  current directory.
- **Options:** `--type TYPE` (only match one artifact type) · `--json` ·
  `--top-level` · `--recursive`
- **Exit codes:** `0` search completed (matches or none) · `2` not a directory

```bash
rac find markdown rac/
rac find explorer rac/ --type decision
rac find "canonical format" rac/ --json
```

```json
{
  "schema_version": "1",
  "query": "markdown",
  "type": null,
  "match_count": 1,
  "matches": [
    {
      "id": "RAC-01JY4M8X2QZ7",
      "type": "decision",
      "title": "Markdown Is the Canonical Source Format",
      "path": "rac/decisions/markdown-first.md"
    }
  ]
}
```


---

## migrate

Bring existing artifacts onto canonical frontmatter identity. Every
recognized artifact without a frontmatter block gains the canonical envelope
(`schema_version`, a system-assigned ID, its classified `type`); the Markdown
body is preserved byte-for-byte. Idempotent — re-running changes nothing, and
a document repaired to classify is picked up by the next run.

- **Input:** `rac migrate metadata <directory>` — requires an initialized
  repository (`rac init`).
- **Options:** `--dry-run` (report without writing) · `--json` ·
  `--top-level` · `--recursive`
- **Exit codes:** `0` completed, including nothing to migrate · `1`
  malformed repository config or ID generation failure · `2` not a
  directory, or repository not initialized

Artifacts that already carry frontmatter — valid or broken — are never
touched; documents that do not classify are listed, never guessed at.

```bash
rac migrate metadata rac/ --dry-run   # preview
rac migrate metadata rac/             # migrate
rac migrate metadata rac/ --json
```

```json
{
  "schema_version": "1",
  "directory": "rac/",
  "recursive": true,
  "dry_run": false,
  "summary": {
    "total_files": 95,
    "migrated": 28,
    "already_canonical": 67,
    "skipped_unknown": 0
  },
  "files": [
    {
      "path": "rac/decisions/adr-001-markdown-first.md",
      "status": "migrated",
      "id": "RAC-01JY4M8X2QZ7",
      "type": "decision"
    }
  ]
}
```

---

## skill

Install or list the bundled Claude Code agent skills. Three skills are
bundled: `rac-artifacts` (author and maintain artifacts), `rac-review`
(corpus review and triage), and `rac-ingest` (legacy document conversion).
Skill content ships with the distribution as package resources, so
installation works from an installed wheel without this repository, network
access, or AI involvement.

- **Input:** `rac skill install [name]` — with no name, every bundled skill;
  with a name, exactly that skill. `rac skill list` — enumerate the bundle.
- **Options:** `--dir PATH` (target project directory; default: current
  directory; install only) · `--json`
- **Exit codes:** `0` installed / listed · `1` a target skill file already
  exists (never overwritten), or a packaged skill resource is missing
  (broken installation) · `2` `--dir` is not a directory, or an unknown
  skill name (the available skills are listed)

`rac skill install` writes each skill to
`.claude/skills/<name>/SKILL.md` under the target directory — the documented
Claude Code project-level discovery path — creating parent directories as
needed. An existing skill file is never overwritten. The no-name form is
all-or-nothing: every target path is checked first, and if any exists the
command refuses with exit `1`, reports the existing path(s), and writes
nothing. To add a single missing skill alongside ones already installed,
name it: `rac skill install rac-review`.

```bash
rac skill install                       # all bundled skills, current project
rac skill install rac-review            # one skill by name
rac skill install --dir ../app --json   # into another project
rac skill list                          # what is bundled
```

```text
Bundled agent skills:

- rac-artifacts  Author and maintain RAC Markdown artifacts with the rac CLI.
- rac-review     Review a RAC corpus and work findings worst-first.
- rac-ingest     Convert legacy documents into valid, linked RAC artifacts.
```

The install `--json` form reports one entry per installed skill:

```json
{
  "schema_version": "1",
  "installed": true,
  "skills": [
    {
      "skill": "rac-artifacts",
      "path": ".claude/skills/rac-artifacts/SKILL.md"
    },
    {
      "skill": "rac-review",
      "path": ".claude/skills/rac-review/SKILL.md"
    },
    {
      "skill": "rac-ingest",
      "path": ".claude/skills/rac-ingest/SKILL.md"
    }
  ]
}
```

---

## hook

Install or list the bundled git hooks. Two hooks are bundled: `post-commit`
(an advisory write-cadence nudge that prints when the corpus has gone quiet and
**never blocks** a commit) and `pre-commit` (validates staged Markdown
artifacts and blocks the commit on errors). Hook scripts ship with the
distribution as package resources, so installation works from an installed
wheel without this repository.

- **Input:** `rac hook install` — install one hook. `rac hook list` —
  enumerate the bundle.
- **Options:** `--style post-commit|pre-commit` (default: `post-commit`;
  install only) · `--dir PATH` (target git repository; default: current
  directory) · `--json`
- **Exit codes:** `0` installed / listed · `1` the target hook file already
  exists (never overwritten), or a packaged hook resource is missing (broken
  installation) · `2` `--dir` is not a directory, has no `.git`, or an unknown
  `--style`

`rac hook install` writes the script to `<dir>/.git/hooks/<style>` and makes it
executable. An existing hook file is never overwritten. The default
`post-commit` hook is non-blocking by design — the nudge builds the write habit
without punishing it; choose `--style pre-commit` only when you want validation
enforced at commit time. Because `.git/hooks` is not version-controlled, run the
install once per clone (or manage `core.hooksPath` yourself).

```bash
rac hook install                       # post-commit advisory nudge
rac hook install --style pre-commit    # blocking artifact validation
rac hook list                          # what is bundled
```

```json
{
  "schema_version": "1",
  "installed": true,
  "hook": {
    "style": "post-commit",
    "path": ".git/hooks/post-commit"
  }
}
```
