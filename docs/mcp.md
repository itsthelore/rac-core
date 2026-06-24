# RAC Guide — MCP Server

RAC Guide is an MCP server that serves your repository's requirements,
decisions, designs, and roadmaps to coding agents as callable tools. It ships
inside the `requirements-as-code` package — no separate install.

## 1. Install

```bash
pip install requirements-as-code
# or
uv tool install requirements-as-code
```

Requires Python 3.11+. The MCP SDK is a standard dependency; no extra flag is
needed.

## 2. Configure your client

Replace `/path/to/your/repo` with the absolute path to the directory that
contains your RAC artifacts (or the `rac/` subdirectory within it). Use the
path you would pass to `rac validate`.

### Claude Code

**Command form** (adds the server to your Claude Code session):

```bash
claude mcp add lore -- rac mcp --root /path/to/your/repo
```

**`.mcp.json` form** — create or edit `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "lore": {
      "command": "rac",
      "args": ["mcp", "--root", "/path/to/your/repo"]
    }
  }
}
```

<!-- TODO: verify against Claude Code <version> before release -->

### Claude Desktop

Open `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows: `%APPDATA%\Claude\claude_desktop_config.json`) and add an entry under `mcpServers`:

```json
{
  "mcpServers": {
    "lore": {
      "command": "rac",
      "args": ["mcp", "--root", "/path/to/your/repo"]
    }
  }
}
```

Restart Claude Desktop after saving.

<!-- TODO: verify against Claude Desktop <version> before release -->

### Cursor

Create or edit `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "lore": {
      "command": "rac",
      "args": ["mcp", "--root", "/path/to/your/repo"]
    }
  }
}
```

<!-- TODO: verify against Cursor <version> before release -->

### Omnigent

[Omnigent](https://omnigent.ai) is a meta-harness: its custom agents are defined
in a `config.yaml`, and an MCP server is a first-class tool type. Add a `lore`
entry under the agent's `tools:` section:

```yaml
tools:
  lore:
    type: mcp
    command: rac
    args: ["mcp", "--root", "/path/to/your/repo"]
```

The tool travels with the agent definition, so it stays attached whichever
harness Omnigent routes to. A worked setup — including pointing the agent's
`instructions` at the generated `AGENTS.md` — is in
[`examples/omnigent/`](https://github.com/itsthelore/rac-core/blob/main/examples/omnigent/README.md).

<!-- TODO: verify against Omnigent <version> before release -->

## 3. Point Guide at a repository

`--root` accepts any directory. It does not have to be the top of a Git
repository — point it at the folder where your RAC Markdown artifacts live.

To check that the path is right before configuring your client:

```bash
rac index /path/to/your/repo
```

That should list your artifacts. If it shows nothing, run
`rac init /path/to/your/repo` to initialize the repository.

To try Guide against a ready-made corpus before using your own, point `--root`
at the included examples:

```bash
rac mcp --root examples/guide
```

The `examples/guide/` corpus contains one requirement, decision, design, and
roadmap for a fictional user management service — enough to explore all four
tools.

## 4. Your first grounded question

Once the server is connected, ask your agent:

> What decisions has this repository recorded about data deletion?

The agent should call `search_artifacts` with a keyword like "delete" or
"soft-delete", retrieve `ADR-001: Soft-Delete User Records` via `get_artifact`,
and cite the decision ID in its response.

If you are pointing at your own repository, substitute a topic you know
a decision covers.

## 5. The four tools

| Tool | When the agent calls it |
|---|---|
| `get_summary` | Once at session start — counts artifacts, flags health issues |
| `search_artifacts` | Before designing or implementing anything that a recorded decision might cover |
| `get_artifact` | When an artifact ID appears, or before changing anything a decision covers |
| `get_related` | After retrieving an artifact — finds what else the change could affect |

`get_related` takes an optional `depth` (default `1`, capped at `5`): the default
returns immediate neighbours only, while `depth>1` additionally returns a
`neighborhood` array of artifacts two or more hops away, each tagged with its
`hops` distance — for transitive context such as a decision a requirement's
roadmap depends on. The walk is bounded (depth, frontier, visited-set, and a work
budget) and deterministic; a truncation marker is set if any cap stops it.

The tool descriptions contain the trigger language; well-tuned agents call them
without being told to.

## 6. Team setup: route CLAUDE.md to a RAC prompt (Claude Code)

The tool descriptions are sufficient on their own — the grounding demo proves
that — but teams adopting RAC can raise the call rate by giving every session
standing guidance. Rather than pasting instructions into `CLAUDE.md`, record
the guidance as a RAC prompt artifact and route to it, the same pattern this
repository uses for its own agent guidance:

```bash
rac new prompt rac/prompts/agent-session-start.md
```

Fill the artifact with your team's standing instructions, for example:

- at session start, call `get_summary` to learn what recorded knowledge exists
- before designing or implementing, call `search_artifacts` for the feature
  area — recorded decisions take precedence over conventions inferred from
  the code
- when an artifact ID is mentioned, call `get_artifact`; call `get_related`
  before changing anything an artifact covers
- cite decisions by ID; if a task conflicts with a recorded decision, say so
  instead of silently overriding it

Then make `CLAUDE.md` a router:

```markdown
# Agent session context

Canonical agent guidance lives in `rac/prompts/` as validated RAC artifacts.

@rac/prompts/agent-session-start.md
```

Claude Code inlines the referenced artifact at session start, so the effect is
identical to pasting the text — but the guidance is now a governed artifact:
`rac validate` checks it in CI, it is versioned and diffable like any other
decision, and Guide itself can serve it (`get_artifact` retrieves your usage
instructions — the system is self-describing).

Two caveats:

- The import inlines the artifact verbatim, YAML frontmatter included. That
  is harmless, and the agent then knows the artifact's own ID.
- `@import` syntax is Claude Code-specific. For Cursor or Claude Desktop,
  carry the same pointer in their native convention (for example
  `.cursor/rules`); the prompt artifact remains the single source of truth.

## 7. Telemetry (opt-in)

Guide records nothing by default. If you want to see whether it is actually
being used — and help decide where Guide investment goes — opt in with an
explicit flag in your client's server configuration:

```json
{
  "mcpServers": {
    "lore": {
      "command": "rac",
      "args": ["mcp", "--root", "/path/to/repo", "--telemetry"]
    }
  }
}
```

When enabled, each tool call appends one JSON line to a local log
(`~/.local/state/rac/guide-telemetry.jsonl`, or under `$XDG_STATE_HOME`):

```json
{"schema_version": "1", "ts": "2026-06-12T14:03:22.512Z", "session": "a3f29c1b",
 "tool": "search_artifacts", "outcome": "ok", "duration_ms": 12, "truncated": false}
```

What is recorded: timestamp, a random per-session id, the tool name, whether
the call succeeded, how long it took, and whether the response was truncated.
What is **never** recorded: tool arguments, artifact IDs, search queries,
file paths, or any repository content. The server announces the log path on
stderr at startup, so enablement is never silent.

Read the log back any time:

```bash
rac mcp-stats          # human summary: events, sessions, per-tool usage
rac mcp-stats --json   # the same summary as JSON — this is the export
```

If you want to share your usage with the project (early reports directly
shape Guide's roadmap):

```bash
rac mcp-stats --share
```

This prints a prefilled GitHub issue URL. Open it, review the report — counts
and timestamps only — and submit it with your own account. RAC never sends
anything anywhere; building a URL is string formatting, and transmission
belongs to you and your browser. Submitted reports are public issues.

### Share anonymously (optional)

If you'd rather contribute a signal without writing anything, opt in to an
anonymous daily ping:

```bash
rac telemetry on       # opt in (rac init also asks once, on a real terminal)
rac telemetry status   # exactly what is shared, and whether sending is possible
rac telemetry off      # stop; nothing else changes
```

With consent on, `rac mcp` sends at most one ping per 24 hours. This is the
entire transmission — adding a field requires a new recorded decision
(ADR-041):

```json
{
  "api_key": "<public project write key>",
  "event": "lore-daily-ping",
  "timestamp": "<ISO 8601 UTC>",
  "properties": {
    "distinct_id": "<random install id>",
    "$process_person_profile": false,
    "schema_version": "1",
    "rac_version": "<version>",
    "active_repos": 2
  }
}
```

What the fields are: the install id is a random token minted when you opt in
(derived from nothing, so it identifies nothing); `$process_person_profile:
false` tells PostHog to create no person profile, so the event stays
anonymous on the receiving side as well; `active_repos` counts the
distinct repositories Guide served in the last 30 days, tracked locally as
salted digests in `~/.local/state/rac/active-repos.json` — the salt never
leaves your machine and only the count is sent. The last-ping marker lives at
`~/.local/state/rac/last-ping`; your consent record at
`~/.config/rac/telemetry.json`.

Sharing is independent of `--telemetry` — each is its own opt-in. When
sharing is on, the server announces it on stderr at startup; it is never
silent. The sender is one readable module (`rac/mcp/ping.py`, the only
network code in RAC): failures are dropped without retries, the socket
timeout is three seconds, and a build with no endpoint key configured sends
nothing at all — `rac telemetry status` will say so.

## 8. Troubleshooting

### Server not listed in the client

- Confirm `rac` is on the PATH the client uses. Test with:
  ```bash
  which rac
  rac --version
  ```
- If you installed with `uv tool install`, the tool binary may be in
  `~/.local/bin/` — add that to PATH or use the full path in the config.
- Check the client's MCP server log for startup errors.

### Wrong root (Guide answers from the wrong repository)

- Verify the `--root` path in your config matches the directory you intend.
- Run `rac index /path/to/your/repo` to confirm the right artifacts are visible.
- In Claude Code, run `/mcp` to inspect the server configuration.

### Empty corpus (Guide says no artifacts found)

When the server starts against a root with no RAC artifacts it prints a
diagnostic to stderr:

```
rac mcp: no RAC artifacts found under '/path/to/your/repo'. Point --root at a
directory containing RAC Markdown artifacts, or run 'rac init' to initialize
a new repository. The server is running; get_summary will report the empty state.
```

This is not a fatal error — the server runs and `get_summary` reports zero
artifacts. To fix it:

1. Check that `--root` points at the right directory.
2. Run `rac index /path/to/your/repo` to confirm artifacts are visible.
3. If the directory has no RAC artifacts yet, run `rac init /path/to/your/repo`
   and start creating artifacts with `rac new`.

### get_summary returns all zeros

Same cause as the empty corpus diagnostic above. Either `--root` is wrong or
the repository has not been initialized. See the troubleshooting steps above.

## Further reading

- [CLI reference](cli.md) — every `rac` command including `rac mcp`
- [Artifact types](artifacts.md) — what requirements, decisions, designs, roadmaps, and prompts look like
- [Repository workflow](repo-workflow.md) — how to organize a RAC repository
- [Examples corpus](https://github.com/itsthelore/rac-core/tree/main/examples/guide/) — the ready-made guide corpus
