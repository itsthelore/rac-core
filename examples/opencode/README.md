# RAC with opencode

[opencode](https://opencode.ai) consumes RAC on two surfaces — a generated context
file opencode reads, and the `lore` MCP server it connects to. A stranger can
reproduce this from the file alone.

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

This writes several agent-context files; opencode reads **`AGENTS.md`** at the
project root natively as its instructions. No extra step — the recorded decisions
reach opencode's agent as instructions. The managed block keeps your own content
intact; re-run on change (`rac export rac/ --agent-rules --check` fails CI on
drift).

## 2. The `lore` MCP server (the pull)

opencode keys MCP servers under an **`mcp`** block, with a local (stdio) server
given as a `command` **array**. Add it to `opencode.json` in the repo root (a
sample is in [`opencode.example.json`](opencode.example.json)):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "lore": {
      "type": "local",
      "command": ["rac", "mcp", "--root", "."],
      "enabled": true
    }
  }
}
```

- **Project:** `opencode.json` in the repo root (commit it to share with the team).
- **Global:** `~/.config/opencode/opencode.json` — use an absolute `--root` path.
- Or run `opencode mcp add` and follow the prompts; `opencode mcp list` shows the
  server and its connection status.

It exposes the five read-only `lore` tools (`get_summary`, `search_artifacts`,
`get_artifact`, `get_related`, `find_decisions`); the server re-reads the corpus on
every call and never writes to the repo.

## 3. Enforcement is separate, and opencode-agnostic

RAC supplies context and enforces *after* the edit (ADR-067). There is no platform
API to veto an opencode agent edit before it lands, so opencode relies on the
post-edit guard: `rac validate` / `rac relationships --validate` and the GitHub
Action / pre-merge gate, the same as any contributor. (A pre-edit veto is
Claude-Code-specific — see [`examples/claude-code/`](../claude-code/README.md).)

## Verify it

Run the bundled grounding demo — same task twice, once unconnected and once with
`lore` connected — and watch the connected run respect a recorded decision the
unconnected run violates: [`examples/guide/`](../guide/demo.md).

## Summary

| Surface | Command | What opencode does with it |
| --- | --- | --- |
| `AGENTS.md` | `rac export rac/ --agent-rules` | Reads it as instructions |
| `lore` MCP | `opencode.json` → `mcp.lore` (`rac mcp --root .`) | Calls `find_decisions` / `get_related` on demand |
| CI gate | `rac validate` · `rac relationships --validate` | Enforces on every PR |

## Verification status

- **Engine half — mechanically verified (2026-07-04).** The `rac mcp` invocation
  this recipe prescribes was smoke-tested over stdio against `examples/guide/`: the
  five `lore` tools respond and `search_artifacts` / `get_artifact` / `get_related`
  return the grounding decision. This is the RAC-owned half every recipe shares.
- **Harness half — not yet verified.** Running the grounding demo *through opencode
  itself* (config parsing plus a live agent) needs the released client and an API
  key — a human/CI step. Until it is done, this recipe keeps the `verify against`
  marker below and stays out of [`docs/ecosystem.md`](../../docs/ecosystem.md).

<!-- TODO: verify against opencode <version> before listing in docs/ecosystem.md -->
