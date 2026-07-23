# AsDecided

**Engineering decisions your agents can follow.**
Build, as decided.

AsDecided keeps requirements, decisions, designs, roadmaps, and prompts as
typed Markdown in your repository. Its native Rust engine validates that
knowledge, retrieves the relevant decisions deterministically, and serves it
read-only to agents over MCP.

No embeddings, model call, or hosted index is required. The same repository
state produces the same answer.

## Install

The distribution is still published from this repository as `rac-core` while
the registry and repository rename are handled as a separate release gate:

```sh
pip install rac-core
```

This installs exactly two executable surfaces:

- `decided` — the native Rust CLI
- `decided-mcp` — the native read-only MCP server

There is no `rac` command, Python CLI fallback, or `RAC_*` environment-variable
compatibility layer.

## Start a repository

```sh
decided quickstart
decided validate decisions/
decided gate decisions/
```

New repositories use:

```text
.decided/config.yaml
decisions/
```

Existing artifact IDs such as `RAC-ABC123DEF456` are durable identities and do
not change with the product name.

## Migrate an existing repository

Migration is explicit and never runs during an ordinary command. Inspect the
plan first:

```sh
decided migrate layout . --dry-run
```

Then apply it:

```sh
decided migrate layout .
```

The migration moves `.rac/` to `.decided/` and `rac/` to `decisions/`. It
refuses to overwrite either destination.

## MCP

Configure clients to run the native server directly:

```json
{
  "mcpServers": {
    "asdecided": {
      "command": "decided-mcp",
      "args": ["--root", "."]
    }
  }
}
```

## Runtime controls

Native runtime controls use the `DECIDED_*` namespace, including
`DECIDED_CACHE_DIR`, `DECIDED_NO_CACHE`, `DECIDED_TIMING`,
`DECIDED_MAX_FILE_BYTES`, `DECIDED_AUDIT_PATH`, and
`DECIDED_AUDIT_PRINCIPAL`.

Stable machine-readable fields such as `rac_version`, and existing `RAC-*`
artifact IDs, remain unchanged where they are part of a published contract.

## Architecture

Rust is the product engine and the only normal CLI/MCP runtime. Python remains
only as packaging/SDK support and a bounded retirement-certification oracle;
it is not a second supported command implementation. Document ingestion lives
outside the core as an ancillary Python connector, and Explorer is retired.

The authoritative language-neutral compatibility fixtures live in
[`rac-spec`](https://github.com/itsthelore/rac-spec). Live-corpus validation is
based on validity, determinism, freshness, and cache/no-cache equality.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
