# Lore

<!-- mcp-name: io.github.tcballard/lore -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/itsthelore/rac-core/main/rac/assets/images/lore-header-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/itsthelore/rac-core/main/rac/assets/images/lore-header-light.png">
  <img alt="Lore — agents that know why. Deterministic. Read-only. No RAG, no guessing." src="https://raw.githubusercontent.com/itsthelore/rac-core/main/rac/assets/images/lore-header-light.png">
</picture>

<p align="center">
<a href="#install">Install</a> ·
<a href="#connect-your-agent">Connect your agent</a> ·
<a href="https://itsthelore.github.io/rac-core/">Docs</a> ·
<a href="https://itsthelore.github.io/rac-core/cli/">CLI</a> ·
<a href="https://github.com/itsthelore/rac-core/blob/main/CHANGELOG.md">Changelog</a>
</p>

[![CI](https://github.com/itsthelore/rac-core/actions/workflows/ci.yml/badge.svg)](https://github.com/itsthelore/rac-core/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/requirements-as-code)](https://pypi.org/project/requirements-as-code/) [![Python](https://img.shields.io/pypi/pyversions/requirements-as-code)](https://pypi.org/project/requirements-as-code/) [![Types: Mypy](https://img.shields.io/badge/types-Mypy-blue.svg)](https://mypy-lang.org/) [![License: Apache 2.0](https://img.shields.io/pypi/l/requirements-as-code)](https://github.com/itsthelore/rac-core/blob/main/LICENSE)

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

## Importing an existing decision

Already have decisions in Confluence, Notion, or loose Markdown? The `rac-import`
agent skill turns **one** existing document into **one** valid RAC artifact, with
a human-review step before anything is written.

```bash
rac skill install rac-import   # installs into .claude/skills/ (Claude Code / Cursor auto-discover)
```

Then ask your agent, in plain language: *"import this decision doc into RAC"*
(paste the text or give a path). The skill reads the real schema with
`rac schema`, drafts the artifact from **only** what your document says, and
shows you the proposed **type, title, and any relationships to confirm or
correct** before it writes a file. It scaffolds with `rac new` (which mints the
id), then closes on `rac validate` — and offers fixes if validation fails, so it
never leaves an invalid artifact behind. It is single-document by design; for
multi-format or bulk conversion use the `rac-ingest` skill.

## Who it's for

- **Teams running coding agents heavily** (Claude Code, Cursor) who are tired of the agent ignoring decisions the team already made.
- **Teams who already write ADRs** and want those decisions to actually shape what the agent does.
- **Anyone who wants the *why* behind their software versioned alongside the code.**

## How it relates to OKF

Google's Open Knowledge Format (OKF) standardises the *carrier* — a Git tree of Markdown with YAML front matter — and is deliberately permissive: an OKF consumer must not reject a bundle for missing fields, unknown types, or broken links. RAC writes that same carrier and adds what OKF leaves to the consumer: **write-time enforcement** in CI. `rac validate` and `rac relationships --validate` reject malformed artifacts, broken or ambiguous links, references to superseded decisions, and relationship edges a type does not support — deterministically, before the knowledge lands. OKF is read-optimised interchange; RAC is write-time enforcement, and `rac export --okf` turns any RAC repo into a conformant OKF bundle — so the two compose rather than compete.

## Documentation

**Full documentation: <https://itsthelore.github.io/rac-core/>**

- [Quickstart](https://itsthelore.github.io/rac-core/quickstart/) — install and author your first artifact
- [MCP server](https://itsthelore.github.io/rac-core/mcp/) — tools, client configuration, examples
- [CLI reference](https://itsthelore.github.io/rac-core/cli/) — every command, flag, and exit code

## Origin

Lore is the product surface of **RAC — Requirements as Code**, the open-source
engine underneath; the package, CLI, and MCP server ship under the `rac` name,
and `lore` is the server identity and brand.
[Wayfinder](https://github.com/itsthelore/wayfinder-router), the deterministic
prompt-complexity router, began as a `route` experiment inside RAC and was split
into its own tool — routing is a runtime concern, not a knowledge one.

## Repository layout

```text
rac-core/
  src/rac/        the engine: CLI, core, services, output, the in-process MCP
                  server (rac mcp), and bundled skills, templates, and git hooks
  rac/            the dogfood corpus — requirements, decisions, designs, roadmaps,
                  and prompts that govern the project itself
  tests/          per-service batteries plus core / cli / artifacts coverage (ADR-027)
  docs/           the documentation site (MkDocs)
  examples/       the grounding demo, woven into the corpus and the test fixtures
  rac-localview/  the Portal / graph viewer, vendored into the engine
```

## Test

```bash
pip install -e .[dev]
python -m pytest
```

`ruff check`, `ruff format --check`, and `mypy src/` run in CI alongside the
per-service batteries (ADR-027).

## Project status

Lore is early and evolving quickly. The MCP server ships today. Contributions, ideas, and experiments welcome — see [CONTRIBUTING.md](https://github.com/itsthelore/rac-core/blob/main/CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE).
