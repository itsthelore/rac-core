# RAC with Zed

[Zed](https://zed.dev) consumes RAC on two surfaces — a generated context file Zed
reads, and the `lore` MCP server it connects to. A stranger can reproduce this from
the file alone.

## Prerequisites

```bash
pip install rac-core   # the `rac` CLI and the `lore` MCP server
```

A repository with a RAC corpus under `rac/` (run `rac quickstart`, or use this
repository's own `rac/`).

## 1. Context file (the push)

```bash
rac export rac/ --agent-rules
```

This writes several agent-context files; Zed reads **`AGENTS.md`** at the project
root as agent **Instructions** (Zed's always-on rules are its Instructions, which
include a project `AGENTS.md`). No extra step — the recorded decisions reach Zed's
Agent Panel as instructions. The managed block keeps your own content intact;
re-run on change (`rac export rac/ --agent-rules --check` fails CI on drift).

## 2. The `lore` MCP server (the pull)

Zed keys MCP servers under **`context_servers`** (not `mcpServers`), added at the
top level of `settings.json` (a sample is in
[`settings.example.json`](settings.example.json)):

```json
{
  "context_servers": {
    "lore": {
      "source": "custom",
      "command": "rac",
      "args": ["mcp", "--root", "."],
      "env": {}
    }
  }
}
```

- **Project:** `.zed/settings.json` in the repo root (commit it to share with the
  team).
- **Global:** your user `settings.json` — use an absolute `--root` path.

Zed restarts the server process on save (no editor restart). It exposes the five
read-only `lore` tools (`get_summary`, `search_artifacts`, `get_artifact`,
`get_related`, `find_decisions`); the server re-reads the corpus on every call and
never writes to the repo.

## 3. Enforcement is separate, and Zed-agnostic

RAC supplies context and enforces *after* the edit (ADR-067). There is no platform
API to veto a Zed agent edit before it lands, so Zed relies on the post-edit guard:
`rac validate` / `rac relationships --validate` and the GitHub Action / pre-merge
gate, the same as any contributor. (A pre-edit veto is Claude-Code-specific — see
[`examples/claude-code/`](../claude-code/README.md).)

## Verify it

Run the bundled grounding demo — same task twice, once unconnected and once with
`lore` connected — and watch the connected run respect a recorded decision the
unconnected run violates: [`examples/guide/`](../guide/demo.md).

## Summary

| Surface | Command | What Zed does with it |
| --- | --- | --- |
| `AGENTS.md` | `rac export rac/ --agent-rules` | Reads it as agent Instructions |
| `lore` MCP | `settings.json` → `context_servers.lore` | Calls `find_decisions` / `get_related` on demand |
| CI gate | `rac validate` · `rac relationships --validate` | Enforces on every PR |

<!-- TODO: verify against Zed <version> before listing in docs/ecosystem.md -->
