/**
 * Integration test against a real `rac` binary and the live RAC corpus.
 *
 * Skipped unless `RAC_BIN` points at an installed `rac` — so the unit suite
 * runs anywhere, while CI (or a local dev with RAC installed) exercises the
 * actual subprocess + JSON contract end to end. Run it from this package with:
 *
 *     RAC_BIN=/abs/path/to/rac npm test
 */

import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { RacClient } from "../src/client.js";
import { isResolved } from "../src/types.js";

const racBin = process.env.RAC_BIN;
// Repo root: test/ -> rac-sdk/ -> typescript/ -> repo
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

describe.skipIf(!racBin)("integration (real rac)", () => {
  const rac = new RacClient({ racPath: racBin, cwd: repoRoot });

  it("reports a version string", async () => {
    expect(await rac.version()).toMatch(/\d+\.\d+/);
  });

  it("validates a known-good artifact", async () => {
    const result = await rac.validateFile("rac/decisions/adr-001-markdown-first.md");
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("resolves a known alias", async () => {
    const result = await rac.resolve("adr-001", "rac");
    expect(isResolved(result)).toBe(true);
    if (isResolved(result)) {
      expect(result.type).toBe("decision");
      expect(result.path).toContain("adr-001");
    }
  });

  it("validates the whole corpus directory (contract shape)", async () => {
    const result = await rac.validateDirectory("rac");
    expect(result.summary.total_files).toBeGreaterThan(0);
    expect(typeof result.summary.invalid).toBe("number");
    expect(Array.isArray(result.files)).toBe(true);
  });

  it("validates in-memory text via stdin", async () => {
    const bad = await rac.validateText("## Problem\n\nno title\n");
    expect(bad.file).toBe("-");
    expect(bad.valid).toBe(false);
    expect(bad.errors.some((i) => i.code === "missing-title")).toBe(true);
  });

  it("returns the canonical schema for a type", async () => {
    const schema = await rac.schema("requirement");
    expect(schema.type).toBe("requirement");
    expect(schema.required).toContain("problem");
    expect(schema.required).toContain("requirements");
  });
});
