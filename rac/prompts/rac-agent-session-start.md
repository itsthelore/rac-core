---
schema_version: 1
id: RAC-KV2J31Z1EV4T
type: prompt
---
# RAC Agent Session Start

## Objective

Establish the working frame for an agent session on RAC, so changes stay
correctly scoped, respect recorded decisions, and pass the corpus gates
before they are pushed.

RAC is a Python CLI for requirements-as-code. It models product-management
Markdown artifacts as deterministic, typed artifacts. Current artifact
families include Requirements, Decisions, Roadmaps, Prompts, and Design.

## Input

- The RAC repository and its corpus under `rac/` — requirements, decisions
  (ADRs), roadmaps, prompts, and designs.
- The roadmap item relevant to the task, and the ADRs it touches.
- The `lore` MCP tools when available in the session; without them, the
  same knowledge via the `rac` CLI (`find`, `resolve`, `relationships`).

## Instructions

### Core principles

- Markdown-first.
- Deterministic classification.
- Structural validation, not semantic scoring unless explicitly planned.
- CLI contracts matter: human output, JSON output, exit codes, and templates must be specified.
- Roadmaps are identified by codename, not a version; release versions are CalVer dates (ADR-094, ADR-076).
- Prefer schema/artifact-spec-driven behavior over artifact-specific branches.
- Keep classification separate from validation.
- Invalid but recognizable artifacts may still classify as their artifact type, then fail validation.
- Durable thinking lives in the corpus, not in ephemeral tool scratch space.
  Record plans, designs, and decisions as RAC artifacts under `rac/` — a
  Design for the *how*, a Roadmap for the *what/why* (a non-versioned
  `rac/roadmaps/future/` item when unscheduled), an ADR for a decision —
  where the gates validate them. A tool's plan or scratch file is working
  memory only; it has no authority and does not persist.

### Before coding

1. Refresh from `origin/main` unless told otherwise.
2. Confirm branch state; work on a feature branch, never on main.
3. Read the relevant roadmap item; do not expand release scope beyond it.
4. Check against ADRs.
5. Produce an implementation contract.
6. Wait for approval.

### Grounding (when the `lore` MCP tools are available in your session)

- Call `get_summary` once at session start to learn what recorded
  knowledge exists.
- Call `search_artifacts` before designing or implementing; recorded
  decisions take precedence over conventions inferred from the code.
- When an artifact ID is mentioned, call `get_artifact`; call
  `get_related` before changing anything an artifact covers.
- Cite decisions by ID. If a task conflicts with a recorded decision,
  say so and stop — do not silently override it.

Without the tools, the same knowledge lives under `rac/`; use the `rac` CLI
(`find`, `resolve`, `relationships`) instead.

### Testing

- Add negative boundary tests for each new artifact type.
- Test that adjacent artifact types do not misclassify as each other.
- Run pytest before commit.

## Output

A correctly scoped, approved change that passes the gates in Evaluation.
After a GitHub merge, refresh local main; prune merged branches when asked.

## Constraints

- Do not implement until the plan is approved.
- Never work on main; always use a feature branch.
- Do not expand release scope beyond the roadmap item.
- If a task conflicts with a recorded decision, say so and stop — do not
  silently override it.

## Evaluation

Before pushing:

- `rac validate rac/` and `rac relationships rac/ --validate` exit 0.
- `rac review rac/` reports no priority 1-2 findings.
- Commits follow `rac/prompts/rac-agent-commit-guidelines.md`: format,
  maintainer identity on author and committer, no tool attribution.

## Related Decisions

- ADR-047
