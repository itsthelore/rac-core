# RAC — TypeScript

TypeScript clients for [RAC](../README.md) (requirements-as-code). Both packages
are **thin clients**: they shell out to the installed `rac` CLI and deserialize
its stable `--json` contracts; they reimplement none of the engine, so they
always agree with the command line ([ADR-063](../rac/decisions/adr-063-non-python-clients-are-thin.md)).
They version independently of the Python package.

| Package | What it is |
| --- | --- |
| [`rac-sdk`](./rac-sdk) (`@rac/sdk`) | The thin Node client: `RacClient` over `rac … --json`, a `RacError` hierarchy, an injectable runner for tests. |
| [`rac-vscode`](./rac-vscode) | The VS Code / Cursor extension: live validation, hover, and go-to-definition. Consumes `@rac/sdk`. |

## Develop

```sh
# SDK first — the extension consumes it via file:../rac-sdk
cd rac-sdk && npm install && npm run build && npm test
cd ../rac-vscode && npm install && npm run check-types && npm run compile
```

The SDK's integration tests run against a real `rac` when `RAC_BIN` is set
(`RAC_BIN=/abs/path/to/rac npm test`).

## Roadmap

The TypeScript SDK and extension are the `v0.21.x` series:
[`rac/roadmaps/v0.21.x-editor/`](../rac/roadmaps/v0.21.x-editor/). This first
release (v0.21.0) is the SDK + extension MVP; later releases add cross-artifact
enforcement, authoring aids, navigation, ambient awareness, a corpus-graph
webview, and release hardening.
