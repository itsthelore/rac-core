/**
 * {@link RacClient} — the thin client. Each method builds a `rac … --json`
 * argument list, runs it through the {@link RacRunner}, and deserializes stdout
 * into a typed result. It interprets nothing: the Python engine is the single
 * source of truth (ADR-063).
 */

import { RacExecError, RacNotFoundError, RacOutputError } from "./errors.js";
import { defaultRunner, type RacRunner, type RunResult } from "./runner.js";
import type {
  CorpusExport,
  CreatedArtifact,
  DirectoryValidation,
  FileValidation,
  FindResult,
  PortfolioStats,
  RelationshipValidation,
  ResolveResult,
  ReviewReport,
  SchemaReference,
} from "./types.js";

export interface RacClientOptions {
  /** Path to the `rac` binary. Defaults to `RAC_BIN` env, else `"rac"` on PATH. */
  racPath?: string;
  /** Working directory for every call (set to the workspace root). */
  cwd?: string;
  /** Injectable runner; defaults to a real `child_process` runner. */
  runner?: RacRunner;
}

export interface RecursiveOptions {
  /** Recurse into subdirectories (default true; false adds `--top-level`). */
  recursive?: boolean;
}

export interface FindOptions {
  /** Directory to search (default: rac's own default). */
  dir?: string;
  /** Restrict to one artifact type, e.g. `"decision"`. */
  type?: string;
}

export class RacClient {
  private readonly racPath: string;
  private readonly cwd: string | undefined;
  private readonly runner: RacRunner;

  constructor(options: RacClientOptions = {}) {
    this.racPath = options.racPath ?? process.env.RAC_BIN ?? "rac";
    this.cwd = options.cwd;
    this.runner = options.runner ?? defaultRunner;
  }

  /** `rac validate <file> --json` — validate a single artifact on disk. */
  validateFile(file: string): Promise<FileValidation> {
    return this.json<FileValidation>(["validate", file, "--json"]);
  }

  /**
   * `rac validate - --json` — validate in-memory artifact text, e.g. an unsaved
   * editor buffer, by piping it to `rac` on stdin. The result's `file` is `"-"`;
   * the caller knows the real path. Severity overrides resolve from `cwd`.
   */
  validateText(text: string): Promise<FileValidation> {
    return this.json<FileValidation>(["validate", "-", "--json"], { input: text });
  }

  /** `rac validate <dir> --json` — validate every artifact under a directory. */
  validateDirectory(
    directory: string,
    options: RecursiveOptions = {},
  ): Promise<DirectoryValidation> {
    return this.json<DirectoryValidation>(
      this.withTopLevel(["validate", directory, "--json"], options),
    );
  }

  /** `rac resolve <id> [dir] --json` — resolve an ID/alias, or report not-found/duplicate. */
  resolve(id: string, directory?: string): Promise<ResolveResult> {
    const args = ["resolve", id];
    if (directory !== undefined) args.push(directory);
    args.push("--json");
    return this.json<ResolveResult>(args);
  }

  /** `rac find <query> [dir] [--type T] --json` — keyword search over the corpus. */
  find(query: string, options: FindOptions = {}): Promise<FindResult> {
    const args = ["find", query];
    if (options.dir !== undefined) args.push(options.dir);
    if (options.type !== undefined) args.push("--type", options.type);
    args.push("--json");
    return this.json<FindResult>(args);
  }

  /** `rac relationships <dir> --validate --json` — resolve declared references. */
  validateRelationships(
    directory: string,
    options: RecursiveOptions = {},
  ): Promise<RelationshipValidation> {
    return this.json<RelationshipValidation>(
      this.withTopLevel(["relationships", directory, "--validate", "--json"], options),
    );
  }

  /** `rac review <dir> --json` — prioritized repository review with a health score. */
  review(directory: string, options: RecursiveOptions = {}): Promise<ReviewReport> {
    return this.json<ReviewReport>(
      this.withTopLevel(["review", directory, "--json"], options),
    );
  }

  /** `rac stats <dir> --json` — portfolio statistics. */
  stats(directory: string): Promise<PortfolioStats> {
    return this.json<PortfolioStats>(["stats", directory, "--json"]);
  }

  /** `rac export <dir> --json` — the corpus export payload (the lore-web viewer shape). */
  exportCorpus(directory: string, options: RecursiveOptions = {}): Promise<CorpusExport> {
    return this.json<CorpusExport>(
      this.withTopLevel(["export", directory, "--json"], options),
    );
  }

  /** `rac schema <type> --json` — the canonical section/metadata reference for a type. */
  schema(artifactType: string): Promise<SchemaReference> {
    return this.json<SchemaReference>(["schema", artifactType, "--json"]);
  }

  /** `rac new <type> <path> --json` — scaffold a new artifact (never overwrites). */
  createArtifact(artifactType: string, outputPath: string): Promise<CreatedArtifact> {
    return this.json<CreatedArtifact>(["new", artifactType, outputPath, "--json"]);
  }

  /** `rac --version` — the installed RAC version string. */
  async version(): Promise<string> {
    const result = await this.run(["--version"]);
    return result.stdout.trim();
  }

  // --- internals ------------------------------------------------------------

  private withTopLevel(args: string[], options: RecursiveOptions): string[] {
    if (options.recursive === false) args.push("--top-level");
    return args;
  }

  private async run(
    args: readonly string[],
    extra: { input?: string } = {},
  ): Promise<RunResult> {
    try {
      return await this.runner(this.racPath, args, {
        cwd: this.cwd,
        input: extra.input,
      });
    } catch {
      // A spawn failure (ENOENT and friends) means rac is not installed/usable.
      throw new RacNotFoundError(this.racPath);
    }
  }

  /**
   * Run a `--json` command and parse stdout. Exit codes 0 and 1 are both normal
   * (1 = "validation found issues"), and the JSON is returned in either case.
   * A run that produces no parseable JSON is a usage/IO failure
   * ({@link RacExecError}) or, on a clean exit, an unexpected-output failure
   * ({@link RacOutputError}).
   */
  private async json<T>(
    args: readonly string[],
    extra: { input?: string } = {},
  ): Promise<T> {
    const result = await this.run(args, extra);
    try {
      return JSON.parse(result.stdout) as T;
    } catch {
      if (result.code !== 0 || result.stderr.trim() !== "") {
        throw new RacExecError(args, result.code, result.stderr);
      }
      throw new RacOutputError(args, result.stdout);
    }
  }
}

/** Convenience factory mirroring `new RacClient(options)`. */
export function createClient(options: RacClientOptions = {}): RacClient {
  return new RacClient(options);
}
