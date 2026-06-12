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

## How this relates to spec-driven development

Spec-driven development (SDD) tools — GitHub Spec Kit, OpenSpec, Kiro — manage the *change*: proposal, design, tasks, carried through to implementation. They treat requirements as ephemeral inputs that are consumed and archived. RAC manages the *requirements*: a durable, versioned, governed corpus that persists across changes and is served to your agent over MCP. RAC is the layer above SDD tools, not a competitor to them — an SDD tool drives each change, while Lore holds the decisions and requirements those changes draw on.

| Dimension | Lore / RAC | GitHub Spec Kit | OpenSpec |
| --- | --- | --- | --- |
| Requirement persistence | Requirements, decisions, designs, and roadmaps are long-lived artifacts that persist across changes | Spec, plan, and tasks are created per feature under `specs/<feature>/` | Change folders are archived on completion under `openspec/changes/archive/`; the specs directory is updated |
| Change management | None — RAC does not manage the change cycle; pair it with an SDD tool | Slash-command workflow: specify, clarify, plan, tasks, implement | Slash-command workflow: propose, apply, archive |
| Traceability | Typed `Related` links between artifacts; `rac relationships --validate` checks them in CI | `/speckit.analyze` runs cross-artifact consistency and coverage analysis | `openspec validate` checks changes and specs for structural issues |
| Tool coupling | Read-only MCP server; works with any MCP client | Slash commands or skills installed per agent at init (GitHub Copilot, Claude Code, Cursor, and others) | Slash commands for 20+ AI assistants |
| Install footprint | `pip install requirements-as-code` (Python 3.11+) | `uv tool install specify-cli` from the Git repository (Python 3.11+) | `npm install -g @fission-ai/openspec` (Node.js 20.19+) |

<!--
Comparison sources, verified 2026-06-12:
- GitHub Spec Kit — https://github.com/github/spec-kit (README): per-feature
  artifacts specs/<feature>/spec.md, plan.md, tasks.md; workflow
  /speckit.specify → /speckit.clarify → /speckit.plan → /speckit.tasks →
  /speckit.implement; /speckit.analyze described as "cross-artifact
  consistency & coverage analysis"; agents selected at init, Copilot
  default, Claude Code/Cursor/Gemini CLI and others listed; install via
  `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`,
  Python 3.11+.
- OpenSpec — https://github.com/Fission-AI/OpenSpec (README): workflow
  /opsx:propose → /opsx:apply → /opsx:archive; archive output
  "Archived to openspec/changes/archive/2025-01-23-add-dark-mode/ Specs
  updated."; "works with 20+ AI assistants via slash commands"; install
  `npm install -g @fission-ai/openspec`, Node.js 20.19.0+.
  https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md:
  `openspec validate` checks changes and specs for structural issues.
- Kiro is named in prose as part of the SDD category but excluded from
  the table: its documentation site (https://kiro.dev/docs/specs/)
  returned HTTP 403 to automated fetches at verification time, so its
  cells could not be verified against the primary source.
- Lore / RAC cells: this repository (README, docs/, rac/).
-->

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
- **Telemetry is opt-in twice over.** Local recording needs an explicit `--telemetry` flag and never includes your arguments or repository content. Remote sharing is a separate, explicit consent (`rac telemetry on`, or one honest question at `rac init`): one anonymous daily ping — a random install id, the version, and an active-repo count — never paths, queries, or content. `rac telemetry status` shows exactly what is shared, the network surface is a single readable module, and ADR-041 records the decision.

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
