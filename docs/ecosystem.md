# Ecosystem

Things that consume RAC artifacts or the RAC engine. Every entry is
real and verified at the time of listing: it exists at the cited
location and works against a released engine version. There are no
planned or placeholder entries.

| Name | What it is | Where |
| --- | --- | --- |
| RAC dogfood corpus | This repository's own product knowledge — requirements, decisions, roadmaps, prompts, designs — validated in CI by the engine it specifies | [`rac/`](https://github.com/itsthelore/rac-core/tree/main/rac/) |
| `rac-artifacts` Claude Code skill | A project-level agent skill that teaches Claude Code to create, validate, and update RAC artifacts using the `rac` CLI | [`.claude/skills/rac-artifacts/`](https://github.com/itsthelore/rac-core/blob/main/.claude/skills/rac-artifacts/SKILL.md) |
| MCP grounding example | A runnable demo showing an agent connected to RAC Guide over MCP respecting a recorded decision that an unconnected agent violates | [`examples/guide/`](https://github.com/itsthelore/rac-core/blob/main/examples/guide/demo.md) |
| Amp setup | A worked setup connecting Sourcegraph's Amp to RAC — it reads the generated `AGENTS.md` natively and queries the `lore` MCP server | [`examples/amp/`](https://github.com/itsthelore/rac-core/blob/main/examples/amp/README.md) |
| Claude Code setup | A worked setup connecting Claude Code to RAC — the generated `CLAUDE.md`, the `lore` MCP server, the `rac-artifacts` skill, and the optional pre-edit veto hook | [`examples/claude-code/`](https://github.com/itsthelore/rac-core/blob/main/examples/claude-code/README.md) |
| Codex setup | A worked setup connecting OpenAI Codex to RAC — it reads the generated `AGENTS.md` and queries the `lore` MCP server via `config.toml` | [`examples/codex/`](https://github.com/itsthelore/rac-core/blob/main/examples/codex/README.md) |

## Adding an entry

An entry is one row in the table above. The criteria:

- The thing exists — on disk in this repository or at a stated
  external location — and can be inspected; intentions and
  works-in-progress are not listed.
- It consumes RAC artifacts or the RAC engine against a released
  version.
- The row states what it is and where it lives, in one line.

Entries are added by a pull request changing the single table row.
The project's contribution policy is pending; until it is published,
external additions cannot yet be accepted.
