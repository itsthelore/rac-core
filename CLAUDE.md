# RAC — agent session context

This file is a router. Canonical agent guidance lives in `rac/prompts/`,
where the RAC corpus gates validate it. Do not add rules here — add them
to the corpus artifact and they load through the imports below.

## Loaded every session

@rac/prompts/rac-agent-session-start.md
@rac/prompts/rac-agent-commit-guidelines.md

## Situational prompts — read when the task calls for it, do not import

- Pull request preparation: `rac/prompts/rac-agent-pr-guidelines.md`
- Minor release gate: `rac/prompts/rac-agent-release-gate-minor.md`
- Major release gate: `rac/prompts/rac-agent-release-gate-major.md`
- Refactoring and simplification: `rac/prompts/rac-agent-simplification-guidelines.md`
- Context compression: `rac/prompts/rac-agent-compression.md`

## Working corpus

- Current series: `rac/roadmaps/v0.10.x-guide/` (next up: v0.10.3)
- Previous series: `rac/roadmaps/v0.8.x-explorer/` (complete through v0.8.10)
- Decisions (ADRs): `rac/decisions/`
