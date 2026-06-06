# RAC (Requirements-as-Code)

> Lint, diff, and analyse product requirements from the command line

Product requirements are often trapped in documents, making them difficult to review, validate, and track over time.

RAC brings software engineering workflows to product requirements.

Write requirements in Markdown. Store them in Git. Validate them, compare versions, and analyse change over time.

```text
Markdown
    ↓
Product Model
    ↓
Validation
    ↓
Diffing
    ↓
Portfolio Analysis
    ↓
AI Review (future)
```

## Why RAC?

Engineers have mature tooling for code:

- Linters
- Code review
- Diffs
- Static analysis
- Version control

Product requirements typically have none of these.

RAC applies the same principles to product requirements.

### Validate

```bash
rac validate bond_dashboard.md
```

### Compare

```bash
rac diff bond_dashboard_v1.md bond_dashboard_v2.md
```

### Analyse

```bash
rac stats ./features
```

---

# Example

Create a requirement file:

```markdown
# Bond Dashboard

## Problem

Retail investors struggle to understand interest-rate exposure.

## Requirements

- [REQ-001] User can view portfolio holdings
- [REQ-002] User can view portfolio duration
- [REQ-003] User can view portfolio yield

## Success Metrics

- Monthly Active Users
- Dashboard Views

## Risks

- Inaccurate market data
```

Validate it:

```bash
rac validate bond_dashboard.md
```

Output:

```text
PASS
```

Now compare two versions:

```bash
rac diff bond_dashboard_v1.md bond_dashboard_v2.md
```

Output:

```text
Added Requirements

+ REQ-004 View projected yield forecast

Modified Requirements

~ REQ-002

Before:
User can view portfolio duration

After:
User can view and compare portfolio duration
```

RAC compares **product changes**, not just text changes.

---

# Installation

## Using pip

```bash
pip install requirements-as-code
```

## Using uv

```bash
uv tool install requirements-as-code
```

Verify installation:

```bash
rac --help
```

---

# Quick Start

Create a file:

```bash
touch feature.md
```

Add requirements:

```markdown
# Trade Alerts

## Problem

Investors miss important market movements.

## Requirements

- [REQ-001] User can create a trade alert
- [REQ-002] User can edit a trade alert
- [REQ-003] User can delete a trade alert
```

Validate:

```bash
rac validate feature.md
```

Compare versions:

```bash
rac diff old.md new.md
```

---

# Philosophy

RAC follows a few simple principles.

## Markdown First

Requirements should remain easy to write and review.

RAC uses Markdown as the source format.

No proprietary editors.

No custom file formats.

## Git Native

Requirements should work naturally inside:

- GitHub
- GitLab
- VS Code
- Cursor
- Claude Code

## AI Optional

RAC should be useful without AI.

The foundation is:

- structure
- validation
- diffing
- analysis

AI is an enhancement, not a dependency.

## Product Model

Internally, RAC converts Markdown into a structured Product Model.

```text
Markdown
    ↓
Parser
    ↓
Feature Model
    ↓
Validation
    ↓
Diffing
    ↓
Stats
```

This enables reliable analysis without relying on fragile text processing.

---

# Markdown Specification

Every feature is represented by a single Markdown file.

Example:

```markdown
# Feature Title

## Problem

Problem statement.

## Requirements

- [REQ-001] Requirement text
- [REQ-002] Requirement text

## Success Metrics

- Metric 1

## Risks

- Risk 1
```

## Required Sections

Required:

- `# Title`
- `## Problem`
- `## Requirements`

Optional (recommended):

- `## Success Metrics`
- `## Risks`

---

# Commands

## Validate

Validate a requirement file.

```bash
rac validate feature.md
```

Checks:

- Required sections exist
- Requirement IDs are valid
- Requirement IDs are unique
- Requirement text is not empty

Warnings:

- Missing risks
- Missing success metrics
- Duplicate requirement text
- Ambiguous wording

---

## Diff

Compare two versions of a feature.

```bash
rac diff old.md new.md
```

Detects:

- Added requirements
- Removed requirements
- Modified requirements
- Added metrics
- Removed metrics
- Added risks
- Removed risks

Requirements are matched by ID.

---

## Stats

Portfolio-level analysis. Recursively scans a directory for `*.md` files
(skipping dotted folders like `.git`), parses and validates each one, and
aggregates the totals. Files that fail validation are still counted and are
listed separately rather than skipped silently.

```bash
rac stats ./features
```

Example output:

```text
Portfolio Overview
==================

Features: 12
Requirements: 87
Metrics: 24
Risks: 18

Quality
=======

Features Missing Metrics: 2
  - Trade Alerts
  - Watchlists
Features Missing Risks: 3
  - Trade Alerts
  - Watchlists
  - Onboarding
Average Requirements Per Feature: 7.3
Largest Feature: Bond Dashboard (16 requirements)

Requirements by Feature
=======================

Bond Dashboard      16
Trade Alerts        11
Watchlists           8
Onboarding           3

Invalid Features (1)
  ./features/draft.md — missing-title, missing-requirements
```

Counts span all parsed requirement files; a feature with only *warnings* (e.g. no
metrics) still counts as valid. Invalid files are listed at the end so they are
never silently skipped.

Non-requirement artifacts are aggregated **separately** so they never distort the
requirement totals or averages. Decisions report metadata breakdowns; Roadmaps,
Prompts, and Designs use lightweight count/valid/invalid summaries.

When a directory contains decisions, a `Decisions` section reports the count plus
a status and category breakdown:

```text
Decisions
=========

Total: 17

Status
  - Accepted: 12
  - Proposed: 3
  - Superseded: 2

Category
  - Architecture: 8
  - Product: 5
  - Process: 4
```

When a directory contains Design artifacts, a lightweight section is shown:

```text
Designs
=======

Total: 4
Valid: 3

Invalid Designs (1)
  ./planning/design/draft.md — missing-constraints
```

When artifacts declare [relationship metadata](#relationship-metadata), a
`Relationships` section reports **declared-presence counts** — how many artifacts
contain each relationship section with at least one reference. These are presence
counts, not resolved links or edge totals:

```text
Relationships
=============

Artifacts with Related Decisions: 6
Artifacts with Related Requirements: 4
Artifacts with Supersedes: 2
```

Add `--json` for machine-readable output. Artifact-specific blocks such as
`decisions`, `roadmaps`, `prompts`, `designs`, and `relationships` are included
only when those artifacts (or relationship sections) are present. `stats` exits `0` when the directory has at least one
valid known artifact, `1` if none, and `2` if the path is not a directory. (A
`--strict` flag for failing on *any* invalid file — handy in CI — is planned.)

---

## Ingest

Convert an existing document into Markdown so it can enter the RAC workflow.
Ingestion only **converts and preserves structure** — it does not decide whether
the result is a valid RAC artifact (that is the job of future `inspect` /
`normalize` commands).

```bash
rac ingest spec.docx              # print converted Markdown (preview)
rac ingest spec.docx --stdout     # same, explicit (handy in pipelines)
rac ingest spec.docx -o spec.md   # write it to a file
rac ingest spec.docx -o spec.md --force   # overwrite an existing file
rac ingest spec.docx --json       # { source, converter, output, markdown }
```

Conversion is powered by [MarkItDown](https://github.com/microsoft/markitdown),
installed via optional extras — split by format so you only pull the readers you
need:

| Extra | Adds | Formats |
|-------|------|---------|
| `ingest` | `markitdown[docx]` | DOCX, HTML, Markdown |
| `ingest-pdf` | `markitdown[pdf]` | + PDF |
| `ingest-office` | `markitdown[pptx,xlsx,xls]` | + PPTX, XLSX, XLS |
| `ingest-all` | everything above | all supported formats |

```bash
pip install "requirements-as-code[ingest]"       # DOCX + HTML + Markdown
pip install "requirements-as-code[ingest-all]"    # everything
```

HTML and Markdown need no extra (HTML is built into MarkItDown; Markdown is a
pass-through). If a file's reader isn't installed, `rac ingest` tells you exactly
which extra to install. Converters live behind a `DocumentConverter` abstraction,
so new sources can be added without changing the CLI.

`ingest` exits `0` on success, `1` if a recognized document fails to convert, and
`2` for usage errors (file not found, unsupported type, missing `ingest` extra,
or an existing output file without `--force`).

---

## Inspect

Identify what kind of artifact a Markdown document is, and report which expected
sections are present or missing. Inspection is **read-only and observational** —
it answers *"what is this?"*, not *"how should I improve it?"* (that's a future
`improve` command).

```bash
rac inspect bond-dashboard.md
rac inspect bond-dashboard.md --json
cat decision.md | rac inspect -          # read from stdin
rac ingest prd.docx --stdout | rac inspect -   # ingest then inspect
```

Output:

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

RAC classifies the document against known artifact schemas (no AI) and reports a
confidence score. RAC recognizes **Requirement**, **Decision**, **Roadmap**,
**Prompt**, and **Design** artifacts; anything that doesn't fit well is reported
as **Unknown** (a valid, successful result — not an error). `--json` emits
`{ type, confidence, present_sections, missing_sections }`, plus an additive
`relationships` object when the artifact declares relationship sections (see
[Relationship metadata](#relationship-metadata)).

### Inspect a directory

Point `inspect` at a directory to get a summary across many files (recursive by
default; `--top-level` limits it to the directory's own files):

```bash
rac inspect planning/
rac inspect planning/ --top-level
rac inspect planning/ --json        # versioned summary + per-file array
```

```text
Files Inspected: 23

Requirements: 7
Decisions: 3
Roadmaps: 2
Prompts: 4
Designs: 1
Unknown: 6
```

### Explain a classification (`--verbose`)

```bash
rac inspect bond-dashboard.md --verbose
```

```text
Artifact Type: Requirement
Confidence: 71%

Required Matches:
  ✓ Problem
  ✓ Requirements

Recommended Matches:
  ✓ Success Metrics

Missing:
  ✗ Risks
  ✗ Assumptions

Score: 2 + 0.5 × 1 = 2.5 / 3.5 = 0.71
```

### Decision metadata

Decision artifacts (ADRs) may carry lightweight, optional metadata. When present,
`inspect` extracts it and `validate` checks the values:

```markdown
## Status

Accepted

## Category

Architecture

## Supersedes

ADR-012
```

| Field | Supported values | Validated? |
|------------|--------------------------------------------------------------|------------|
| Status | Proposed, Accepted, Superseded, Deprecated | yes |
| Category | Architecture, Product, Process, Technical, Other | yes |
| Supersedes | any reference (free text) | no — metadata only |

`inspect` surfaces these under a **Decision Metadata** block (and in `--json` as
`status` / `category` / `supersedes`, present only when declared). Metadata is
**optional**: a decision without it is still valid. Only an *unsupported* Status
or Category value fails validation (`invalid-decision-status` /
`invalid-decision-category`); values are matched case-insensitively.

### Relationship metadata

Artifacts can reference each other with explicit Markdown sections (v0.7.0). RAC
extracts these as **metadata only** — it records the references but does **not**
resolve, validate, or graph them (those come in a later v0.7.x release).

```markdown
## Related Decisions

- ADR-004
- ADR-012

## Related Roadmaps

- ROADMAP-Q3-PLATFORM
```

Each artifact type recognizes the relationship sections that make sense for it:

| Artifact | Relationship sections |
|-------------|--------------------------------------------------------------------------|
| Requirement | Related Decisions, Related Roadmaps, Related Prompts, Related Designs |
| Decision | Supersedes, Related Requirements, Related Roadmaps, Related Designs |
| Roadmap | Related Decisions, Related Requirements, Related Prompts, Related Designs |
| Prompt | Related Requirements, Related Decisions, Related Roadmaps, Related Designs |
| Design | Related Requirements, Related Decisions, Related Roadmaps, Related Prompts |

Relationship sections are **optional**: they are never scored, never reported as
missing, and never appear in starter templates — an artifact without them stays
valid. `inspect` surfaces them under a **Relationships** block, and in `--json`
as an additive `relationships` object (snake_case keys, string arrays, present
only when at least one reference is declared):

```json
{
  "type": "requirement",
  "present_sections": ["problem", "requirements"],
  "relationships": {
    "related_decisions": ["ADR-004", "ADR-012"],
    "related_roadmaps": ["ROADMAP-Q3-PLATFORM"]
  }
}
```

References are kept verbatim (an `ADR-004`, a `REQ-001`, or a relative path are
all valid) — RAC does not parse out IDs or check that the targets exist.

**`supersedes` is a backwards-compatible exception:** it remains a top-level
scalar (`"supersedes": "ADR-012"`) rather than moving into `relationships`, so the
existing Decision contract is unchanged.

### Synonyms

Common heading variants are recognized automatically (case-insensitive,
deterministic) — e.g. `Success Criteria` and `KPIs` both count as Success Metrics,
and `Alternatives` counts as Alternatives Considered.

`inspect` exits `0` for any completed inspection (including Unknown) and `2` for
usage errors (file not found, or a non-Markdown file — convert it with
`rac ingest` first).

---

## Improve

Where `inspect` tells you *what an artifact is*, `improve` tells you *what to add
next* and how to think about completing it. It reports the required and
recommended sections an artifact is missing, plus schema-defined guidance for
those sections — **deterministically, from the schema, with no AI** (ADR-002).
`improve` is **advisory and read-only**: it never modifies your files and never
generates content beyond `_TODO_` placeholders and guidance comments.

```bash
rac improve requirement.md
rac improve requirement.md --template     # Markdown skeletons for missing sections
rac improve requirement.md --json
cat requirement.md | rac improve -        # stdin
rac ingest prd.docx --stdout | rac improve -
```

Default output:

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

`--template` turns the gaps into a ready-to-paste skeleton (required sections
first, then recommended), with deterministic guidance comments per section:

```markdown
## Risks

_TODO_

<!-- What could prevent successful delivery? -->
<!-- What dependencies or unknowns exist? -->
```

So you can go straight from `rac inspect requirement.md` to
`rac improve requirement.md --template` without consulting any documentation.

`--json` returns a stable contract (ADR-007):

```json
{
  "type": "requirement",
  "missing_required": [],
  "missing_recommended": ["risks", "assumptions"],
  "guidance": {
    "risks": [
      "What could prevent successful delivery?",
      "What dependencies or unknowns exist?"
    ],
    "assumptions": [
      "What are you assuming to be true?",
      "What would change the approach if it turned out false?"
    ]
  }
}
```

`improve` generates suggestions for artifact types with complete schema guidance
coverage. Today that means **Requirement**, **Decision**, **Roadmap**, **Prompt**,
and **Design** artifacts. Unknown documents return a short explanatory message
instead. Future artifact types do not become improvable until their schemas
define guidance for every required and recommended section.

Guidance is informational metadata only: it does not influence classification,
validation, confidence scoring, statistics, or repository analysis.

`improve` is advisory: it exits `0` for any completed analysis (with or without
suggestions) and `2` for usage errors. The presence of suggestions never changes
the exit code.

---

## Schema

Inspect RAC's registered artifact schemas without creating a file.

```bash
rac schema --list
rac schema --list --json
rac schema requirement
rac schema decision --json
rac schema design
rac schema requirement --template
rac schema design --template
```

`rac schema <type>` shows the full schema reference: required, recommended, and
optional sections; descriptions; guidance; and metadata values where applicable.
Supported schemas are `requirement`, `decision`, `roadmap`, `prompt`, and
`design`.

```text
Artifact Type: Decision

Required Sections:
  - Context
  - Decision
  - Consequences

Recommended Sections:
  - Status
  - Category
  - Alternatives Considered

Optional Sections:
  - Supersedes

Metadata Fields:
  - Status: Proposed | Accepted | Superseded | Deprecated
  - Category: Architecture | Product | Process | Technical | Other
```

`--json` returns the same schema data as grouped arrays and maps:

```json
{
  "type": "requirement",
  "required": ["problem", "requirements"],
  "recommended": ["success_metrics", "risks", "assumptions"],
  "optional": [],
  "descriptions": {},
  "guidance": {},
  "metadata": {}
}
```

`--template` emits a structurally valid Markdown starter. Templates are useful
starting points, not finished artifacts: users still replace TODO text with
meaningful product knowledge.

```bash
rac schema requirement --template > requirement.md
rac schema decision --template > decision.md
rac schema design --template > design.md
```

Generated templates are validation-safe:

```bash
rac schema requirement --template | rac validate -
rac schema decision --template | rac validate -
rac schema design --template | rac validate -
```

Unknown schemas fail with exit code `2` and list available schemas. Only
registered schemas are supported; custom schemas are out of scope.

---

## Relationships

Inspect the explicit [relationship metadata](#relationship-metadata) declared
across a repository — a deterministic, read-only view of how artifacts reference
one another, without opening every file.

```bash
rac relationships planning/
rac relationships planning/ --json
rac relationships planning/ --top-level     # don't recurse into subdirectories
rac relationships requirements/search.md    # a single file works too
```

```text
Relationships

Files Inspected: 24
Artifacts With Relationships: 8
Relationships Found: 14

By Type:
- Related Requirements: 4
- Related Decisions: 6
- Related Roadmaps: 2
- Related Prompts: 1
- Supersedes: 1

requirements/search.md
  Related Decisions:
  - ADR-004
```

`--json` returns structured data for automation and future viewers (ADR-015 —
relationship intelligence lives in RAC Core, not the UI):

```json
{
  "directory": "planning",
  "recursive": true,
  "total_files": 24,
  "artifacts_with_relationships": 8,
  "relationship_count": 14,
  "counts": { "related_decisions": 6, "related_requirements": 4 },
  "artifacts": [
    {
      "path": "requirements/search.md",
      "type": "requirement",
      "relationships": { "related_decisions": ["ADR-004"] }
    }
  ]
}
```

Notes:

- **Counts are individual references.** `relationship_count` equals
  `sum(counts.values())`; an artifact listing two decisions contributes two.
- **`total_files`** counts every Markdown file considered — including files with
  no relationships and Unknown artifacts.
- **Supersedes is a relationship here.** Unlike `rac inspect` (where `supersedes`
  is a top-level scalar), this command reports it alongside the `related_*`
  sections, in both `counts` and per-artifact `relationships`.
- **Spec-driven.** Extraction is keyed off each artifact type's declared sections.
  Unknown artifacts are counted but contribute no relationships (and never appear
  in `artifacts`); RAC does not scan arbitrary Markdown.
- **Read-only and exit `0`.** The command never modifies files and exits `0`
  whether or not relationships are found (`2` only for a missing path or a
  non-Markdown file). It does **not** resolve or validate targets — broken-link
  detection is a later release.

---

## Review (Planned)

AI-assisted product review.

```bash
rac review feature.md
```

Potential checks:

- Missing requirements
- Missing risks
- Ambiguity
- Product concerns
- Engineering concerns

RAC will use the user's configured AI provider rather than requiring hosted infrastructure.

---

# Roadmap

## v0.1

- Markdown parser
- Product Model (AST)
- Validation
- Diffing
- CLI

## v0.2

- Portfolio statistics
- Quality metrics
- Repository-wide analysis

## v0.3

- AI review
- Provider abstraction
- Git-aware workflows

## v1.0

- Product intelligence
- Daily product briefs
- VS Code integration

---

# Contributing

Contributions, ideas, and feedback are welcome.

The project is intentionally focused on one goal:

> Treat product requirements like code.

---

# License

MIT
