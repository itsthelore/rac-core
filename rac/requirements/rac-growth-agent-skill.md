---
schema_version: 1
id: RAC-KTYB6R0DM280
type: requirement
---
# RAC Growth — Claude Code Agent Skill

## Status

Accepted

## Problem

Coding agents are a primary audience for RAC, but there is no agent-native
entry point. An agent working in a host project that adopts RAC has to
rediscover the CLI surface and the artifact conventions from scratch in
every session. Claude Code skills are the documented mechanism for giving
an agent a reusable, discoverable procedure: a `SKILL.md` file under
`.claude/skills/<skill-name>/` in the project is loaded automatically
(per Anthropic's Claude Code skills documentation,
code.claude.com/docs/en/skills). RAC should ship one.

## Requirements

- [REQ-001] A Claude Code skill ships in this repository at the documented project-level discovery path `.claude/skills/<skill-name>/SKILL.md`, with YAML frontmatter (`name`, `description`) and Markdown instructions in the format the Claude Code skills documentation specifies.

- [REQ-002] Following the skill, an agent in a host project can create RAC artifact files (`rac new`), read and classify them (`rac inspect`), validate them (`rac validate`, `rac relationships --validate`), and update them (edit plus `rac improve` to find missing sections) using only the published `rac` CLI.

- [REQ-003] The skill instructs the agent never to write outside the host project's RAC artifact directory (`rac/` by default), and never to hand-write or alter artifact ids, frontmatter identity, or `.rac/config.yaml`.

- [REQ-004] The skill describes only released CLI behaviour; it contains no instructions that depend on unreleased commands, flags, or RAC core changes.

- [REQ-005] The skill content ships with the distribution as a package resource (under `rac.skills`), loadable from an installed wheel without this repository, network access, or AI involvement.

- [REQ-006] `rac skill install [--dir PATH]` writes the bundled skill to `.claude/skills/rac-artifacts/SKILL.md` in the target project, creating parent directories and never overwriting an existing file, with human and `--json` output and exit codes following the established CLI convention.

- [REQ-007] The repository's dogfood copy at `.claude/skills/rac-artifacts/SKILL.md` and the packaged resource are byte-identical, enforced by a test.

- [REQ-008] Every bundled skill is installable by name (`rac skill install <name>`), all bundled skills install together when no name is given (refusing all-or-nothing if any target exists), `rac skill list` enumerates them, and each skill carries its own packaged-resource/dogfood byte-equality test.

- [REQ-009] A bundled single-document import skill (`rac-import`) reshapes one existing document into one valid RAC artifact: it reads the real schema with `rac schema`, drafts only from source content (flagging required sections the source does not cover, never fabricating), requires explicit human confirmation of the artifact type, title, and any relationships before any file is written, scaffolds with `rac new` (which mints the id), and closes on `rac validate`. It is single-document by scope (refusing batch/directory/wiki import and pointing to `rac-ingest`), proposes relationships only from links the source itself names, and adds no AI to RAC core.

## Success Metrics

- The skill file exists at the documented path and is valid per the
  Claude Code skills format (frontmatter parses; description states when
  to use it).
- A Claude Code session in a project containing the skill can complete
  the create → validate → update loop on a requirement artifact without
  consulting documentation outside the skill.
- No file outside the host project's RAC directory is written when the
  skill's instructions are followed.

## Risks

- The skill format is defined by Anthropic and may change; the skill
  should be re-checked against the published documentation when Claude
  Code releases note skill changes.
- Skill instructions drift from CLI behaviour as RAC evolves; the skill
  must be updated alongside CLI contract changes.
- There is no corpus mechanism to link this requirement to the skill
  file that satisfies it; traceability is by convention only (recorded
  as a schema gap).

## Assumptions

- The host project has the `rac` CLI installed and on the path; the
  skill does not manage installation.
- Project-level skills (`.claude/skills/`) remain the documented
  discovery path for repository-shipped skills.

## Related Roadmaps

- v1.4-claude-skills
- v0.10.5-bundled-agent-skill
- v0.10.5-review-and-ingest-skills
- v0.17.0-single-document-import-skill

## Related Requirements

- rac-growth-adoption
