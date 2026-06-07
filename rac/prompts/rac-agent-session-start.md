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
- Invalid but recognizable artifacts may still classify as their artifact type, then fail validation.

Before coding:
1. Refresh from `origin/main`.
2. Confirm branch state.
3. Read the relevant roadmap item.
4. Check against ADRs.
5. Produce an implementation contract.
6. Wait for approval.

Do not implement until I approve the plan.