/**
 * `@rac/sdk` — a thin TypeScript client for RAC (requirements-as-code).
 *
 * It shells out to the installed `rac` binary and deserializes its stable
 * `--json` contracts (ADR-007) into typed results. It reimplements none of
 * RAC's engine — the Python side stays the single source of truth (ADR-063) —
 * so a consumer (the VS Code / Cursor extension is the first) always agrees
 * with `rac` on the command line.
 *
 *     import { RacClient, RacNotFoundError } from "@rac/sdk";
 *
 *     const rac = new RacClient({ cwd: workspaceRoot });
 *     try {
 *       const result = await rac.validateFile("rac/decisions/adr-001.md");
 *       for (const issue of [...result.errors, ...result.warnings]) {
 *         // → editor diagnostics
 *       }
 *     } catch (err) {
 *       if (err instanceof RacNotFoundError) {
 *         // prompt: install RAC
 *       }
 *     }
 */

export { RacClient, createClient } from "./client.js";
export type {
  RacClientOptions,
  RecursiveOptions,
  FindOptions,
} from "./client.js";

export {
  RacError,
  RacNotFoundError,
  RacExecError,
  RacOutputError,
} from "./errors.js";

export { defaultRunner } from "./runner.js";
export type { RacRunner, RunResult, RunOptions } from "./runner.js";

export { isResolved } from "./types.js";
export type {
  Severity,
  Issue,
  FileValidation,
  FileStatus,
  DirectoryFileValidation,
  ValidationSummary,
  OkfConformance,
  DirectoryValidation,
  ResolvedArtifact,
  ResolveNotFound,
  ResolveDuplicate,
  ResolveResult,
  FindMatch,
  FindResult,
  RelationshipIssue,
  RelationshipValidation,
  ReviewIssue,
  ReviewReport,
  PortfolioStats,
  SchemaReference,
  CreatedArtifact,
  CorpusMeta,
  ExportArtifact,
  ExportRelationship,
  CorpusExport,
} from "./types.js";
