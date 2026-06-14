# Lore

<!-- mcp-name: io.github.tcballard/lore -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/tcballard/requirements-as-code/main/rac/assets/images/lore-header-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/tcballard/requirements-as-code/main/rac/assets/images/lore-header-light.png">
  <img alt="Lore — agents that know why. Deterministic. Read-only. No RAG, no guessing." src="https://raw.githubusercontent.com/tcballard/requirements-as-code/main/rac/assets/images/lore-header-light.png">
</picture>

[![CI](https://github.com/tcballard/requirements-as-code/actions/workflows/ci.yml/badge.svg)](https://github.com/tcballard/requirements-as-code/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/requirements-as-code)](https://pypi.org/project/requirements-as-code/) [![Python](https://img.shields.io/pypi/pyversions/requirements-as-code)](https://pypi.org/project/requirements-as-code/) [![License: MIT](https://img.shields.io/pypi/l/requirements-as-code)](https://github.com/tcballard/requirements-as-code/blob/main/LICENSE)

> **Give your coding agent the decisions your team already made — so it stops re-doing things you ruled out.**

Lore keeps your team's recorded knowledge — requirements, decisions, designs, roadmaps, and prompts — as typed Markdown in your repo and serves it read-only to Claude Code, Cursor, and Claude Desktop over MCP, so the agent cites your decisions instead of violating them. It is built on **RAC — Requirements as Code**, the open-source engine underneath; the package, CLI, and MCP server ship under the `rac` name.

## Install

```bash
pip install requirements-as-code
```

Requires Python 3.11+. `uv tool install requirements-as-code` also works.

## Connect your agent

Claude Code (from your repo root):

```bash
claude mcp add lore -- rac mcp
```

Claude Desktop / Cursor (`mcpServers` in the client config):

```json
{
  "mcpServers": {
    "lore": { "command": "rac", "args": ["mcp", "--root", "/absolute/path/to/your/repo"] }
  }
}
```

## Author and enforce artifacts

```bash
rac quickstart             # one command: set up identity + scaffold your first artifact
rac validate rac/          # check every artifact in a directory
rac inspect requirement.md # see its type and completeness
rac review rac/            # full repository review, worst problems first
rac export rac/ --html --out lore-export.html    # the Portal, one file
```

## Who it's for

- **Teams running coding agents heavily** (Claude Code, Cursor) who are tired of the agent ignoring decisions the team already made.
- **Teams who already write ADRs** and want those decisions to actually shape what the agent does.
- **Anyone who wants the *why* behind their software versioned alongside the code.**

## Documentation

**Full documentation: <https://tcballard.github.io/requirements-as-code/>**

- [Quickstart](https://tcballard.github.io/requirements-as-code/quickstart/) — install and author your first artifact
- [MCP server](https://tcballard.github.io/requirements-as-code/mcp/) — tools, client configuration, examples
- [CLI reference](https://tcballard.github.io/requirements-as-code/cli/) — every command, flag, and exit code

## Project status

Lore is early and evolving quickly. The MCP server ships today. Contributions, ideas, and experiments welcome — see [CONTRIBUTING.md](https://github.com/tcballard/requirements-as-code/blob/main/CONTRIBUTING.md).

## License

MIT
