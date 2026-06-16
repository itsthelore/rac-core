# RAC for VS Code / Cursor

Inline validation for [RAC](../../README.md) (requirements-as-code) artifacts,
powered by the [`@rac/sdk`](../rac-sdk/README.md) thin client.

Open or save a RAC artifact (a Markdown file with `schema_version` frontmatter)
and validation findings appear as diagnostics — the same findings `rac validate`
reports on the command line, because the extension runs `rac` rather than
reimplementing it ([ADR-063](../../rac/decisions/adr-063-non-python-clients-are-thin.md)).

> Status: early (0.1.0).

## Requirements

- The `rac` CLI installed and discoverable (`pip install requirements-as-code`),
  or its path set in `rac.path`.

## Features

- **Live validation** — diagnostics update as you type (the unsaved buffer is
  piped through `rac validate -`, debounced), and immediately on open/save.
  Errors + warnings are mapped to the right lines.
- **Cross-artifact enforcement** — references that don't resolve, and references
  to **retired** (superseded/deprecated) artifacts, are flagged at the reference
  site, drawn distinctly (from `rac relationships --validate`). Refreshes on
  save/activation, since relationship validation reads files from disk.
- **Hover** — hovering an artifact ID or alias (e.g. `adr-007`,
  `v0.20.0-python-sdk-foundation`) shows its title, type, **lifecycle status**
  (⚠ for retired), a snippet, and its path.
- **Go-to-definition, find-all-references, clickable links** — jump to a target,
  list every artifact that references the one under the cursor (from the export's
  resolved edges), and Ctrl/Cmd-click any alias to open its file.
- **Outline & workspace symbols** — the artifact's sections in the Outline view,
  and jump-to-any-artifact by title (Ctrl/Cmd-T).
- **Corpus awareness** — a status-bar health score (`rac review`, click for the
  Problems panel) and workspace-wide diagnostics (`rac validate <dir>`), so issues
  in unopened artifacts show up too.
- **RAC Explorer** — **RAC: Open Explorer** renders the corpus in a side panel
  (the self-contained, offline Portal viewer from `rac export --html`): a
  searchable list/detail view and an Obsidian-style **node-link graph** (a global
  graph, or a local graph that follows the file you are editing). Selecting a node
  opens its file, and switching files reveals that artifact in the graph.
- **Authoring aids** — artifact-alias completion inside relationship sections
  (`## Related Decisions`, …), quick-fixes that insert a missing `## Section`,
  and a **RAC: New Artifact** command that suggests an existing folder for the
  type, then scaffolds via `rac new`.
- **RAC: Validate Open Artifacts** command.
- Graceful handling when `rac` is missing — a one-time prompt to install or set
  `rac.path`, never a wall of errors.

Only Markdown files with a leading `schema_version` frontmatter block are
treated as RAC artifacts, so ordinary Markdown stays untouched.

The extension activates only in RAC workspaces (those with a `.rac/config.yaml`),
caches `rac` lookups (cleared on save) to stay responsive, warns once on `rac`
schema-version skew, and logs to a "RAC" output channel.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `rac.path` | `""` | Path to `rac`. Empty = `RAC_BIN` env, else `rac` on `PATH`. |
| `rac.validate.enable` | `true` | Validate artifacts and show diagnostics. |

## Privacy

No telemetry. The extension runs entirely on your machine and only ever invokes
your local `rac` CLI — it makes no network requests and collects no usage data.
The Explorer webview is a self-contained, offline document served under a strict
Content-Security-Policy (no network, no remote code, no eval).

## Develop

```sh
npm install        # links @rac/sdk from ../rac-sdk (build it first: cd ../rac-sdk && npm run build)
npm run check-types
npm run compile    # esbuild → dist/extension.js
```

Then press **F5** (Run RAC Extension) to launch an Extension Development Host.

## Roadmap

Tracked in [`rac/roadmaps/future/typescript-sdk-vscode.md`](../../rac/roadmaps/future/typescript-sdk-vscode.md).
Next: relationship findings drawn at the reference site (`rac relationships` /
`rac review`), and completion for artifact IDs.
