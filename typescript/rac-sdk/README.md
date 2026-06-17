# @itsthelore/rac-sdk

A thin TypeScript client for [RAC](../../README.md) (requirements-as-code).

It shells out to the installed `rac` binary and deserializes its stable
`--json` contracts into typed results. It **reimplements none of RAC's engine** —
the Python side stays the single source of truth ([ADR-063](../../rac/decisions/adr-063-non-python-clients-are-thin.md)) —
so this client always agrees with what `rac` reports on the command line. It is
the same pattern the Ruff and ESLint editor extensions use to wrap their tools.

The first consumer is the VS Code / Cursor extension; the package is usable from
any Node program (custom CI gates, dashboards, scripts).

> Status: early (0.1.0). The surface mirrors a subset of the Python SDK and may
> change pre-1.0.

## Requirements

- Node.js >= 18
- The `rac` CLI installed and discoverable (`pip install requirements-as-code`).
  The client never bundles an engine; it calls *your* `rac`.

## Install

```sh
npm install @itsthelore/rac-sdk
```

## Usage

```ts
import { RacClient, RacNotFoundError, isResolved } from "@itsthelore/rac-sdk";

const rac = new RacClient({ cwd: workspaceRoot }); // cwd resolves .rac/config.yaml

// Validate one file → editor diagnostics
try {
  const result = await rac.validateFile("rac/decisions/adr-001.md");
  for (const issue of [...result.errors, ...result.warnings]) {
    console.log(issue.severity, issue.code, issue.message, issue.line);
  }
} catch (err) {
  if (err instanceof RacNotFoundError) {
    // surface an "install RAC" prompt — rac isn't on PATH
  } else {
    throw err;
  }
}

// Resolve an ID / alias → go-to-definition
const target = await rac.resolve("adr-001", "rac");
if (isResolved(target)) openFile(target.path);

// Search → hover / quick-pick
const { matches } = await rac.find("typescript", { dir: "rac", type: "roadmap" });
```

### Configuring the binary

`racPath` (constructor) → `RAC_BIN` env → `rac` on `PATH`, in that order:

```ts
new RacClient({ racPath: "/abs/path/to/rac", cwd: workspaceRoot });
```

## API

`new RacClient(options?)` / `createClient(options?)` — `options`: `racPath`,
`cwd`, `runner` (injectable for tests).

| Method | Wraps | Returns |
| --- | --- | --- |
| `validateFile(file)` | `rac validate <file> --json` | `FileValidation` |
| `validateDirectory(dir, {recursive?})` | `rac validate <dir> --json` | `DirectoryValidation` |
| `resolve(id, dir?)` | `rac resolve <id> [dir] --json` | `ResolveResult` |
| `find(query, {dir?, type?})` | `rac find <query> --json` | `FindResult` |
| `validateRelationships(dir, {recursive?})` | `rac relationships <dir> --validate --json` | `RelationshipValidation` |
| `review(dir, {recursive?})` | `rac review <dir> --json` | `ReviewReport` |
| `stats(dir)` | `rac stats <dir> --json` | `PortfolioStats` |
| `exportCorpus(dir, {recursive?})` | `rac export <dir> --json` | `CorpusExport` |
| `version()` | `rac --version` | `string` |

A validation *failure* is not an exception: `validateFile` of an invalid
artifact resolves with `valid: false` and populated `errors`/`warnings`.
Errors are reserved for "could not run rac": `RacNotFoundError` (binary
missing), `RacExecError` (usage/IO failure), `RacOutputError` (unparseable
output). All derive from `RacError`.

## Develop

```sh
npm install
npm run build      # tsc → dist/
npm test           # unit tests (no rac needed; uses an injected fake runner)
RAC_BIN=/abs/path/to/rac npm test   # also runs the integration suite
```

The client talks to `rac` only through the `RacRunner` seam, so the unit suite
exercises argument-building, JSON parsing, and error-mapping with a fake runner
and never spawns a process.
