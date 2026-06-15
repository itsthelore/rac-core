# RAC for VS Code / Cursor

Inline validation for [RAC](../../README.md) (requirements-as-code) artifacts,
powered by the [`@rac/sdk`](../rac-sdk/README.md) thin client.

Open or save a RAC artifact (a Markdown file with `schema_version` frontmatter)
and validation findings appear as diagnostics — the same findings `rac validate`
reports on the command line, because the extension runs `rac` rather than
reimplementing it ([ADR-063](../../rac/decisions/adr-063-non-python-clients-are-thin.md)).

> Status: scaffold (0.1.0). MVP is validation diagnostics on open/save.

## Requirements

- The `rac` CLI installed and discoverable (`pip install requirements-as-code`),
  or its path set in `rac.path`.

## Features (MVP)

- Diagnostics for RAC artifacts on open and save (errors + warnings, mapped to
  the right lines).
- **RAC: Validate Open Artifacts** command.
- Graceful handling when `rac` is missing — a one-time prompt to install or set
  `rac.path`, never a wall of errors.

Only Markdown files with a leading `schema_version` frontmatter block are
validated, so ordinary Markdown stays untouched.

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
Next: live-as-you-type validation (pipe the buffer through `rac validate -`),
ID hover / go-to-definition (`rac resolve` / `rac find`), and relationship
findings (`rac relationships` / `rac review`).
