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

Decision artifacts are aggregated **separately** so they never distort the
requirement totals or averages. When a directory contains decisions, a
`Decisions` section reports the count plus a status and category breakdown:

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

Add `--json` for machine-readable output (a `decisions` block is included only
when decisions are present). `stats` exits `0` when the directory has at least
one valid feature or decision, `1` if none, and `2` if the path is not a
directory. (A `--strict` flag for failing on *any* invalid file — handy in CI —
is planned.)

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
confidence score. v0.4 recognizes **Requirement** and **Decision** artifacts;
anything that doesn't fit well is reported as **Unknown** (a valid, successful
result — not an error). `--json` emits `{ type, confidence, present_sections,
missing_sections }`.

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
Unknown: 13
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
coverage. Today that means **Requirement** and **Decision** artifacts. Unknown
documents return a short explanatory message instead. Future artifact types do
not become improvable until their schemas define guidance for every required and
recommended section.

Guidance is informational metadata only: it does not influence classification,
validation, confidence scoring, statistics, or repository analysis.

`improve` is advisory: it exits `0` for any completed analysis (with or without
suggestions) and `2` for usage errors. The presence of suggestions never changes
the exit code.

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
