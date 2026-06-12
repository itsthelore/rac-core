# Lore

<!-- mcp-name: io.github.tcballard/lore -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/tcballard/requirements-as-code/main/rac/assets/images/lore-header-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/tcballard/requirements-as-code/main/rac/assets/images/lore-header-light.png">
  <img alt="Lore — agents that know why. Deterministic. Read-only. No RAG, no guessing." src="https://raw.githubusercontent.com/tcballard/requirements-as-code/main/rac/assets/images/lore-header-light.png">
</picture>

[![CI](https://github.com/tcballard/requirements-as-code/actions/workflows/ci.yml/badge.svg)](https://github.com/tcballard/requirements-as-code/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/requirements-as-code)](https://pypi.org/project/requirements-as-code/) [![Python](https://img.shields.io/pypi/pyversions/requirements-as-code)](https://pypi.org/project/requirements-as-code/) [![License: MIT](https://img.shields.io/pypi/l/requirements-as-code)](https://github.com/tcballard/requirements-as-code/blob/main/LICENSE)

> **Give your coding agent the decisions your team already made — so it stops re-doing things you ruled out.**

Your agent reintroduces an approach you rejected months ago. It rebuilds something you deliberately removed. The decision was written down — in an ADR nobody, human or agent, ever reopened.

Lore stores your requirements, decisions, designs, and roadmaps as typed Markdown in your repo, and serves them to Claude Code, Cursor, and Claude Desktop over MCP. The agent cites your decisions instead of violating them.

No AI in the core. No inference. No guessing. Just your team's recorded knowledge, in your Git, handed to the agent that needs it.

Lore is built on **RAC — Requirements as Code** — the open-source engine underneath. For now the package, CLI, and MCP server all ship under the `rac` name:

```bash
pip install requirements-as-code
```

> 📺 **[90-second demo](#)** — watch an agent violate a decision, then respect it. *(link on launch)*

## Grounding your agent (start here)

Lore ships a read-only MCP server. Point your agent at your repo and it can search, retrieve, and traverse your recorded knowledge mid-task.

**1. Install**

```bash
pip install requirements-as-code
```

**2. Connect your agent**

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

**3. Ask, and watch it ground**

> *"Should I add a hard delete to the user model?"*

The agent calls Lore, finds your soft-delete decision, cites it by ID, and proposes the compliant change — instead of reintroducing the thing you removed on purpose.

The server exposes four read-only tools: `get_artifact`, `search_artifacts`, `get_related`, `get_summary`. It never writes to your repo.

▶ **Full walkthrough + runnable example: [examples/guide/](https://github.com/tcballard/requirements-as-code/tree/main/examples/guide)**

## Why this works

The code is structured, the tests are automated, the infrastructure is versioned — but the *reasoning* behind what you build is scattered across tickets, chats, and dead docs. Agents can't act on what they can't read, so they re-litigate settled decisions.

Lore puts that reasoning back in the repo as typed, connected artifacts, then serves it to the agent through a deterministic interface. You write the decision once, in Markdown; RAC validates it, links it, and makes it retrievable — durable context for both humans and AI, with no proprietary format and no hosted platform.

## Who it's for

- **Teams running coding agents heavily** (Claude Code, Cursor) who are tired of the agent ignoring decisions the team already made.
- **Teams who already write ADRs** and want those decisions to actually shape what the agent does.
- **Anyone who wants the *why* behind their software versioned alongside the code.**

## Authoring artifacts (the RAC CLI)

The MCP server is only as good as what it serves. RAC's CLI is how you write and maintain that knowledge — and how you enforce it in CI.

```bash
rac validate rac/          # check every artifact in a directory
rac inspect requirement.md # see its type and completeness
rac review rac/            # full repository review, worst problems first
```

New to Lore? Author your first artifact in five minutes: **[docs/quickstart.md](https://github.com/tcballard/requirements-as-code/blob/main/docs/quickstart.md)**.

### Supported artifact types

- **Requirements** — what needs to exist
- **Decisions** — why choices were made (ADRs)
- **Designs** — product experience thinking
- **Roadmaps** — where the product is heading
- **Prompts** — reusable AI collaboration patterns

Everything stays plain Markdown — see **[docs/artifacts.md](https://github.com/tcballard/requirements-as-code/blob/main/docs/artifacts.md)**.

## How Lore earns trust

Lore asks you to trust it with your product knowledge, so it holds itself to the same standard it applies to your repository:

- **The MCP server is read-only by construction.** It cannot create, modify, or delete files in your repo — enforced in code and verified by tests, not by convention.
- **No AI in the core.** Retrieval is deterministic: the same repo state and the same query always return the same result. The reasoning is your agent's job; Lore's job is to hand it the facts.
- **It dogfoods itself.** Lore's own planning corpus under [`rac/`](https://github.com/tcballard/requirements-as-code/tree/main/rac) is validated by RAC in CI — if the tool's rules break the tool's own artifacts, the build fails.
- **Output is a contract.** Golden tests pin CLI and MCP output; any change to what the tools return is reviewed as a product change.
- **Telemetry is opt-in, local-only, and content-free.** Nothing is recorded without an explicit flag, events never include your arguments or repository content, and nothing leaves your machine unless you submit a report yourself — Lore contains no network code.

## Documentation

- [Quickstart](https://github.com/tcballard/requirements-as-code/blob/main/docs/quickstart.md) — install and author your first artifact
- [MCP server](https://github.com/tcballard/requirements-as-code/blob/main/docs/mcp.md) — tools, client configuration, examples
- [CLI reference](https://github.com/tcballard/requirements-as-code/blob/main/docs/cli.md) — every command, flag, and exit code
- [Artifact types](https://github.com/tcballard/requirements-as-code/blob/main/docs/artifacts.md) — the five types and their sections
- [Relationships](https://github.com/tcballard/requirements-as-code/blob/main/docs/relationships.md) — link artifacts and validate the links

Requires Python 3.11+. `uv tool install requirements-as-code` also works.

## Project status

Lore is early and evolving quickly. The MCP server ships today; feedback from teams running agents in anger is exactly what shapes what comes next. Contributions, ideas, and experiments welcome — see [CONTRIBUTING.md](https://github.com/tcballard/requirements-as-code/blob/main/CONTRIBUTING.md).

## License

MIT
