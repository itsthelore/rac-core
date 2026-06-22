# RAC with GitHub Copilot

[GitHub Copilot](https://github.com/features/copilot) in VS Code consumes RAC on
two surfaces — a generated custom-instructions file Copilot reads, and the `lore`
MCP server its agent mode connects to. A stranger can reproduce this from the
file alone.

## Prerequisites

```bash
pip install requirements-as-code   # the `rac` CLI and the `lore` MCP server
```

A repository with a RAC corpus under `rac/` (run `rac quickstart`, or use this
repository's own `rac/`).

## 1. Custom instructions (the push)

```bash
rac export rac/ --agent-rules
```

Among the agent-context files this writes is **`.github/copilot-instructions.md`**
— Copilot's repository custom-instructions file — into a managed block (your own
content is preserved). Copilot Chat applies it automatically (ensure
*"Use Instruction Files"* / `github.copilot.chat.codeGeneration.useInstructionFiles`
is enabled — on by default in recent VS Code). Re-run on change;
`rac export rac/ --agent-rules --check` fails CI on drift.

## 2. The `lore` MCP server (the pull)

Copilot's **agent mode** uses MCP servers. Add `.vscode/mcp.json` in the repo
root — note VS Code uses the **`servers`** key (not `mcpServers`); a sample is in
[`mcp.example.json`](mcp.example.json):

```json
{
  "servers": {
    "lore": {
      "type": "stdio",
      "command": "rac",
      "args": ["mcp", "--root", "."]
    }
  }
}
```

(Or run **MCP: Open User Configuration** for a user-level server.) Start it from
the MCP view, then use Copilot Chat in **Agent** mode. It exposes the five
read-only `lore` tools (`get_summary`, `search_artifacts`, `get_artifact`,
`get_related`, `find_decisions`); the server re-reads the corpus on every call
and never writes to the repo.

## 3. Enforcement is separate, and Copilot-agnostic

RAC supplies context and enforces *after* the edit (ADR-067). No platform API
vetoes a Copilot suggestion before it lands, so Copilot relies on the post-edit
guard: `rac validate` / `rac relationships --validate` and the GitHub Action /
pre-merge gate. (The pre-edit veto is Claude-Code-specific — see
[`examples/claude-code/`](../claude-code/README.md).)

## Verify it

Run the bundled grounding demo — same task twice, once unconnected and once with
`lore` connected — and watch the connected run respect a recorded decision the
unconnected run violates: [`examples/guide/`](../guide/demo.md).

## Summary

| Surface | Command | What Copilot does with it |
| --- | --- | --- |
| `.github/copilot-instructions.md` | `rac export rac/ --agent-rules` | Applies it as repo custom instructions |
| `lore` MCP | `.vscode/mcp.json` (`servers`) → `rac mcp --root .` | Agent mode calls `find_decisions` / `get_related` on demand |
| CI gate | `rac validate` · `rac relationships --validate` | Enforces on every PR |
