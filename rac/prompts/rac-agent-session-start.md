We are working on RAC, a Python CLI for requirements-as-code.

RAC models product-management Markdown artifacts as deterministic, typed artifacts.
Current artifact families include Requirements, Decisions, Roadmaps, Prompts, and Design.

Core principles:
- Markdown-first.
- Deterministic classification.
- Structural validation, not semantic scoring unless explicitly planned.
- CLI contracts matter: human output, JSON output, exit codes, and templates must be specified.
- Version numbers are scope fences.
- Prefer schema/artifact-spec-driven behavior over artifact-specific branches.
- Keep classification separate from validation.
- Invalid but recognizable artifacts may still classify as their artifact type, then fail validation.

Before coding:
1. Refresh from `origin/main` unless told otherwise.
2. Confirm branch state; work on a feature branch, never on main.
3. Read the relevant roadmap item; do not expand release scope beyond it.
4. Check against ADRs.
5. Produce an implementation contract.
6. Wait for approval.

Do not implement until I approve the plan.

Grounding (when the `lore` MCP tools are available in your session):
- Call `get_summary` once at session start to learn what recorded
  knowledge exists.
- Call `search_artifacts` before designing or implementing; recorded
  decisions take precedence over conventions inferred from the code.
- When an artifact ID is mentioned, call `get_artifact`; call
  `get_related` before changing anything an artifact covers.
- Cite decisions by ID. If a task conflicts with a recorded decision,
  say so and stop — do not silently override it.
Without the tools, the same knowledge lives under `rac/`; use the
`rac` CLI (`find`, `resolve`, `relationships`) instead.

Testing:
- Add negative boundary tests for each new artifact type.
- Test that adjacent artifact types do not misclassify as each other.
- Run pytest before commit.

Before pushing:
- `rac validate rac/` and `rac relationships rac/ --validate` exit 0.
- `rac review rac/` reports no priority 1-2 findings.
- Commits follow `rac/prompts/rac-agent-commit-guidelines.md`: format,
  maintainer identity on author and committer, no tool attribution.

After a GitHub merge, refresh local main. Prune merged branches when asked.
