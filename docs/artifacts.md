# Artifacts

RAC understands five artifact types, all written in plain Markdown:

| Type | Captures | Typical filename |
| --- | --- | --- |
| **Requirement** | What needs to exist | `login-flow.md` |
| **Decision** | Why a choice was made | `adr-001-markdown-first.md` |
| **Roadmap** | Where the product is heading | `v0.7.6-document-structure.md` |
| **Prompt** | A reusable AI collaboration pattern | `requirement-review.md` |
| **Design** | Product experience thinking | `checkout-flow.md` |

You never declare a type. RAC infers it from the `##` section headings in the file.

## How classification works

Classification is **deterministic** — no AI, no scoring model. RAC reads the `##`
headings, normalizes them (case- and whitespace-insensitive, so `## Problem` and
`## problem` are the same), and matches them against each schema's expected sections.

- The best-matching type wins, and `inspect` reports a confidence percentage.
- If no type reaches a **50% confidence** match, the file is reported as `Unknown`.
  That is a valid, expected outcome — not an error.

```bash
decided inspect login-flow.md      # Artifact Type: Requirement (71%)
decided schema --list              # the five registered types
```

## Documents vs. artifacts

A Markdown file is a *document*; an *artifact* is a recognized, structured piece of
knowledge. Plenty of useful documents (notes, guides, planning files) won't match a
schema, and that's fine — `stats` and `portfolio` list them as "unrecognized" rather
than failing. RAC reports them, it doesn't reject them.

## Artifact identity

Most commands refer to artifacts by an **id**. RAC resolves an id in this order:

1. An explicit `## ID` section, if present.
2. A `<letters>-<digits>` prefix on the filename (e.g. `adr-004-...` → `adr-004`).
3. The filename stem (e.g. `login-flow.md` → `login-flow`).

Ids are compared case-insensitively. Identity is what
[relationships](relationships.md) resolve against.

---

## The five types

For each type, scaffold a starter file with `decided schema <type> --template` and read
the full section guidance with `decided schema <type>`.

### Requirement

What the system must do.

- **Required:** Problem · Requirements
- **Recommended:** Success Metrics · Risks · Assumptions
- **Optional:** Related Decisions · Related Roadmaps · Related Prompts · Related Designs · Related Requirements
- **Naming:** a descriptive slug, e.g. `login-flow.md`. Write requirements as
  testable `[REQ-001]` statements.

### Decision

Why a choice was made — typically as an ADR (Architecture Decision Record). **ADRs
are Decisions written in ADR format**, not a separate type.

- **Required:** Context · Decision · Consequences
- **Recommended:** Status · Category · Alternatives Considered
- **Optional:** Supersedes · Related Requirements · Related Roadmaps · Related Designs · Related Decisions
- **Metadata values (validated when present):**
  - `Status`: `Proposed` | `Accepted` | `Superseded` | `Deprecated`
  - `Category`: `Architecture` | `Product` | `Process` | `Technical` | `Other`
- **Naming:** `adr-NNN-slug.md` (e.g. `adr-001-markdown-first.md`), which gives the
  id `adr-001`.

### Roadmap

Where the product is heading — outcomes and the work that supports them.

- **Required:** Outcomes · Initiatives
- **Recommended:** Success Measures · Assumptions · Risks
- **Optional:** Related Decisions · Related Requirements · Related Prompts · Related Designs · Related Roadmaps
- **Naming:** `vX.Y.Z-slug.md` (e.g. `v0.7.6-document-structure.md`), which gives the
  id `v0.7.6`.

### Prompt

A reusable pattern for collaborating with an AI model.

- **Required:** Objective · Input · Instructions · Output
- **Recommended:** Constraints · Examples · Evaluation
- **Optional:** Related Requirements · Related Decisions · Related Roadmaps · Related Designs
- **Naming:** a descriptive slug, e.g. `requirement-review.md`.

### Design

Product experience thinking — flows, interactions, and the constraints around them.

- **Required:** Context · User Need · Design · Constraints
- **Recommended:** Rationale · Alternatives · Accessibility · Style Guidance · Open Questions
- **Optional:** Related Requirements · Related Decisions · Related Roadmaps · Related Prompts
- **Naming:** a descriptive slug, e.g. `checkout-flow.md`.

---

## See also

- [relationships.md](relationships.md) — connect artifacts with `## Related …` sections.
- [cli.md](cli.md#schema) — the `schema`, `inspect`, and `improve` commands.
