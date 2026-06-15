/**
 * The subprocess seam. {@link RacClient} talks to `rac` only through a
 * {@link RacRunner}, so the default implementation can be swapped for a fake in
 * unit tests — no real binary needed to exercise the client's parsing and
 * error-mapping logic.
 */

import { execFile } from "node:child_process";

/** The captured outcome of one `rac` invocation. */
export interface RunResult {
  stdout: string;
  stderr: string;
  /** Process exit code; 0 on success, non-zero on validation/usage failures. */
  code: number;
}

/** Options for a single run. */
export interface RunOptions {
  /** Working directory — set this to the workspace root so `.rac/config.yaml` resolves. */
  cwd?: string;
  /** Max stdout/stderr bytes to buffer (default 64 MiB, for large exports). */
  maxBuffer?: number;
  /** Written to the child's stdin and then closed — used for `rac validate -`. */
  input?: string;
}

/**
 * Runs `bin args` and resolves with stdout/stderr/code. It resolves (not
 * rejects) on a non-zero exit, because RAC uses exit codes as data (exit 1 =
 * "validation found issues"); it rejects only when the process cannot be spawned
 * at all (e.g. ENOENT), which the client maps to {@link RacNotFoundError}.
 */
export type RacRunner = (
  bin: string,
  args: readonly string[],
  options?: RunOptions,
) => Promise<RunResult>;

/** The default runner, backed by `child_process.execFile`. */
export const defaultRunner: RacRunner = (bin, args, options = {}) =>
  new Promise<RunResult>((resolve, reject) => {
    const child = execFile(
      bin,
      [...args],
      {
        cwd: options.cwd,
        maxBuffer: options.maxBuffer ?? 64 * 1024 * 1024,
        encoding: "utf8",
      },
      (error, stdout, stderr) => {
        // A spawn failure (binary missing, not executable) surfaces as an error
        // with a string `code` like "ENOENT" and no exit code — reject so the
        // client can raise RacNotFoundError.
        if (error && typeof (error as NodeJS.ErrnoException).code === "string") {
          reject(error);
          return;
        }
        // A non-zero exit also arrives as `error`, but with a numeric `code`.
        const code =
          error && typeof (error as { code?: number }).code === "number"
            ? (error as { code: number }).code
            : 0;
        resolve({ stdout, stderr, code });
      },
    );
    // Feed stdin for commands that read it (`rac validate -`), then close it so
    // the child sees EOF and proceeds.
    if (options.input !== undefined) {
      child.stdin?.end(options.input);
    }
  });
