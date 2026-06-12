# RAC schema — extracted from the live codebase (v0.10.3, 2026-06-12)

Source of truth: `docs/artifacts.md`, `docs/relationships.md`, `src/rac/`,
`rac new` output. Do not invent fields beyond what is listed here.

## Artifact model

Five types, all plain Markdown. Type is **inferred from `##` section
headings** (deterministic, case/whitespace-insensitive, 50% confidence
threshold) — never declared. Frontmatter carries identity only:

```yaml
---
schema_version: 1
id: RAC-XXXXXXXXXXXX   # machine-generated, opaque (ADR-026)
type: requirement       # requirement|decision|roadmap|prompt|design
---
```

**Never hand-write an id.** Create artifacts with:

```bash
/tmp/racenv/bin/rac new <type> <output-path>
```

(The repo identity namespace `.rac/config.yaml` already exists; `rac new`
mints the id and writes the canonical template.)

## Sections per type

| Type | Required | Recommended | Optional |
| --- | --- | --- | --- |
| Requirement | Problem · Requirements | Success Metrics · Risks · Assumptions | Related Decisions · Related Roadmaps · Related Prompts · Related Designs · Related Requirements |
| Decision | Context · Decision · Consequences | Status · Category · Alternatives Considered | Supersedes · Related Requirements · Related Roadmaps · Related Designs |
| Roadmap | Outcomes · Initiatives | Success Measures · Assumptions · Risks | Related Decisions · Related Requirements · Related Prompts · Related Designs |
| Prompt | Objective · Input · Instructions · Output | Constraints · Examples · Evaluation | Related Requirements · Related Decisions · Related Roadmaps · Related Designs |
| Design | Context · User Need · Design · Constraints | Rationale · Alternatives · Accessibility · Style Guidance · Open Questions | Related Requirements · Related Decisions · Related Roadmaps · Related Prompts |

Validated decision metadata values:
- `Status`: Proposed | Accepted | Superseded | Deprecated
- `Category`: Architecture | Product | Process | Technical | Other

Requirements convention in this repo: a `## Status` section (Proposed /
Accepted style) and testable `[REQ-NNN]` statements under `## Requirements`.

## Identity and relationships

Id resolution order: explicit `## ID` section → `<letters>-<digits>`
filename prefix (`adr-004-…` → `adr-004`) → filename stem. Case-insensitive.

The ONLY linking mechanism is the `## Related <Type>` sections (one id per
line) plus `## Supersedes` on decisions. Links are corpus-internal, by id.
There is no mechanism for: links to non-artifact files (README sections,
code, skills), typed edge semantics (derived-from, satisfies, applies-to),
or machine-readable gate/blocked status. If you need one of these, record
it as a gap (see BRIEF) — do not improvise frontmatter fields.

## Directory layout (this repo's dogfood corpus)

- `rac/requirements/` — long-lived capabilities (ADR-020), slug `rac-<area>.md`.
  Existing: rac-agent-context-guide, rac-documentation-structure,
  rac-product-intent-ci-watchkeeper, rac-product-knowledge-navigator-explorer,
  rac-repository-review-mode, rac-trust-transparency.
- `rac/decisions/` — `adr-NNN-slug.md` (next free number: adr-039).
- `rac/roadmaps/<series>/` — `vX.Y.Z-slug.md`; `rac/roadmaps/future/` for unscheduled.
- `rac/prompts/`, `rac/designs/` — descriptive slugs.
- `docs/` — user documentation layer (ADR-022); `README.md` — entry point only.
- `examples/guide/` — runnable MCP grounding example.

## Validation commands (run before reporting done)

```bash
/tmp/racenv/bin/rac validate rac/                    # must exit 0
/tmp/racenv/bin/rac relationships rac/ --validate    # must exit 0
/tmp/racenv/bin/rac review rac/                      # no priority 1-2 findings
```
