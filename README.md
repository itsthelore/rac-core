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

Counts span all parsed files; a feature with only *warnings* (e.g. no metrics)
still counts as valid. Invalid files are listed at the end so they are never
silently skipped.

Add `--json` for machine-readable output. `stats` exits `0` when the directory
has at least one valid feature, `1` if none are valid, and `2` if the path is
not a directory. (A `--strict` flag for failing on *any* invalid file — handy in
CI — is planned.)

---

## Ingest

Convert an existing document into Markdown so it can enter the RAC workflow.
Ingestion only **converts and preserves structure** — it does not decide whether
the result is a valid RAC artifact (that is the job of future `inspect` /
`normalize` commands).

```bash
rac ingest spec.docx              # print converted Markdown (preview)
rac ingest spec.docx -o spec.md   # write it to a file
rac ingest spec.docx -o spec.md --force   # overwrite an existing file
rac ingest spec.docx --json       # { source, converter, output, markdown }
```

Conversion is powered by [MarkItDown](https://github.com/microsoft/markitdown),
installed via the optional `ingest` extra:

```bash
pip install "requirements-as-code[ingest]"
```

Supported today: **DOCX** and **Markdown** (pass-through). HTML and PDF are
planned for v0.3.x. Converters live behind a `DocumentConverter` abstraction, so
new sources can be added without changing the CLI.

`ingest` exits `0` on success, `1` if a recognized document fails to convert, and
`2` for usage errors (file not found, unsupported type, missing `ingest` extra,
or an existing output file without `--force`).

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