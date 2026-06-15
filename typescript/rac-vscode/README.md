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
- **Hover** — hovering an artifact ID or alias (e.g. `adr-007`,
  `v0.20.0-python-sdk-foundation`) shows its title, type, and path via
  `rac resolve`.
- **Go-to-definition** — jump from a reference to the target artifact's file.
- **RAC: Validate Open Artifacts** command.
- Graceful handling when `rac` is missing — a one-time prompt to install or set
  `rac.path`, never a wall of errors.

Only Markdown files with a leading `schema_version` frontmatter block are
treated as RAC artifacts, so ordinary Markdown stays untouched.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `rac.path` | `""` | Path to `rac`. Empty = `RAC_BIN` env, else `rac` on `PATH`. |
| `rac.validate.enable` | `true` | Validate artifacts and show diagnostics. |

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
