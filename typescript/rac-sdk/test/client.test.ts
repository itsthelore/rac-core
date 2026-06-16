import { describe, expect, it } from "vitest";

import { RacClient } from "../src/client.js";
import {
  RacExecError,
  RacNotFoundError,
  RacOutputError,
} from "../src/errors.js";
import type { RacRunner, RunResult } from "../src/runner.js";
import { isResolved } from "../src/types.js";

/** A fake runner that records the args/stdin it was called with and returns canned output. */
function fakeRunner(
  result: Partial<RunResult> & { stdout: string },
): { runner: RacRunner; calls: string[][]; inputs: (string | undefined)[] } {
  const calls: string[][] = [];
  const inputs: (string | undefined)[] = [];
  const runner: RacRunner = async (_bin, args, options) => {
    calls.push([...args]);
    inputs.push(options?.input);
    return { stdout: result.stdout, stderr: result.stderr ?? "", code: result.code ?? 0 };
  };
  return { runner, calls, inputs };
}

describe("validateFile", () => {
  it("parses a clean result", async () => {
    const { runner } = fakeRunner({
      stdout: JSON.stringify({ file: "a.md", valid: true, errors: [], warnings: [] }),
    });
    const rac = new RacClient({ runner });
    const result = await rac.validateFile("a.md");
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("returns the result on exit 1 (validation found issues, not an error)", async () => {
    const { runner, calls } = fakeRunner({
      code: 1,
      stdout: JSON.stringify({
        file: "bad.md",
        valid: false,
        errors: [{ severity: "error", code: "missing-title", message: "no title", line: null }],
        warnings: [{ severity: "warning", code: "missing-risks", message: "no risks", line: null }],
      }),
    });
    const rac = new RacClient({ runner });
    const result = await rac.validateFile("bad.md");
    expect(result.valid).toBe(false);
    expect(result.errors[0]?.code).toBe("missing-title");
    expect(result.warnings[0]?.code).toBe("missing-risks");
    expect(calls[0]).toEqual(["validate", "bad.md", "--json"]);
  });
});

describe("validateText", () => {
  it("validates via stdin (`-`) and forwards the buffer as input", async () => {
    const { runner, calls, inputs } = fakeRunner({
      code: 1,
      stdout: JSON.stringify({
        file: "-",
        valid: false,
        errors: [{ severity: "error", code: "missing-title", message: "no title", line: null }],
        warnings: [],
      }),
    });
    const rac = new RacClient({ runner });
    const result = await rac.validateText("## Problem\n\nno title\n");
    expect(result.valid).toBe(false);
    expect(calls[0]).toEqual(["validate", "-", "--json"]);
    expect(inputs[0]).toBe("## Problem\n\nno title\n");
  });
});

describe("validateDirectory", () => {
  it("parses the summary and adds --top-level when recursive is false", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        directory: "rac",
        recursive: false,
        summary: { total_files: 2, checked: 2, valid: 2, invalid: 0, skipped_unknown: 0 },
        valid: true,
        files: [],
      }),
    });
    const rac = new RacClient({ runner });
    const result = await rac.validateDirectory("rac", { recursive: false });
    expect(result.summary.total_files).toBe(2);
    expect(calls[0]).toEqual(["validate", "rac", "--json", "--top-level"]);
  });
});

describe("resolve", () => {
  it("narrows a successful resolution with isResolved", async () => {
    const { runner } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        id: "RAC-1",
        type: "decision",
        title: "ADR-001",
        path: "rac/decisions/adr-001.md",
      }),
    });
    const result = await new RacClient({ runner }).resolve("adr-001", "rac");
    expect(isResolved(result)).toBe(true);
    if (isResolved(result)) expect(result.path).toContain("adr-001");
  });

  it("returns a typed not-found outcome (exit 0, error field)", async () => {
    const { runner } = fakeRunner({
      stdout: JSON.stringify({ schema_version: "1", error: "not-found", id: "nope" }),
    });
    const result = await new RacClient({ runner }).resolve("nope");
    expect(isResolved(result)).toBe(false);
    if (!isResolved(result)) expect(result.error).toBe("not-found");
  });
});

describe("find", () => {
  it("passes --type and parses matches", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        query: "sdk",
        type: "roadmap",
        match_count: 1,
        matches: [{ id: "RAC-2", type: "roadmap", title: "TS SDK", path: "x.md" }],
      }),
    });
    const result = await new RacClient({ runner }).find("sdk", { dir: "rac", type: "roadmap" });
    expect(result.match_count).toBe(1);
    expect(calls[0]).toEqual(["find", "sdk", "rac", "--type", "roadmap", "--json"]);
  });
});

describe("findDecisions", () => {
  it("passes --decisions and parses the live decisions", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        query: "caching",
        type: "decision",
        match_count: 1,
        matches: [{ id: "RAC-9", type: "decision", title: "Cache policy", path: "d.md" }],
      }),
    });
    const result = await new RacClient({ runner }).findDecisions("caching", "rac");
    expect(result.type).toBe("decision");
    expect(result.matches[0].id).toBe("RAC-9");
    expect(calls[0]).toEqual(["find", "caching", "rac", "--decisions", "--json"]);
  });

  it("omits the directory when not given", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        query: "x",
        type: "decision",
        match_count: 0,
        matches: [],
      }),
    });
    await new RacClient({ runner }).findDecisions("x");
    expect(calls[0]).toEqual(["find", "x", "--decisions", "--json"]);
  });
});

describe("validateRelationships", () => {
  it("parses relationship issues", async () => {
    const { runner, calls } = fakeRunner({
      code: 1,
      stdout: JSON.stringify({
        directory: "rac",
        recursive: true,
        relationships_checked: 10,
        validation_issues: 1,
        issues: [
          { source_path: "a.md", relationship: "related_requirements", target: "x", code: "relationship-target-not-found" },
        ],
      }),
    });
    const result = await new RacClient({ runner }).validateRelationships("rac");
    expect(result.validation_issues).toBe(1);
    expect(result.issues[0]?.code).toBe("relationship-target-not-found");
    expect(calls[0]).toEqual(["relationships", "rac", "--validate", "--json"]);
  });
});

describe("schema", () => {
  it("returns the section reference and passes the type", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        type: "requirement",
        required: ["problem", "requirements"],
        recommended: ["success_metrics"],
        optional: [],
        descriptions: { problem: "the problem" },
        guidance: {},
        metadata: {},
      }),
    });
    const result = await new RacClient({ runner }).schema("requirement");
    expect(result.required).toEqual(["problem", "requirements"]);
    expect(result.descriptions.problem).toBe("the problem");
    expect(calls[0]).toEqual(["schema", "requirement", "--json"]);
  });
});

describe("createArtifact", () => {
  it("scaffolds an artifact and parses the result", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        created: true,
        type: "decision",
        path: "d.md",
        id: "RAC-NEW",
      }),
    });
    const result = await new RacClient({ runner }).createArtifact("decision", "d.md");
    expect(result.created).toBe(true);
    expect(result.id).toBe("RAC-NEW");
    expect(calls[0]).toEqual(["new", "decision", "d.md", "--json"]);
  });
});

describe("exportHtml", () => {
  it("writes via --html --out and resolves on exit 0", async () => {
    const { runner, calls } = fakeRunner({ stdout: "", stderr: "wrote x.html", code: 0 });
    await new RacClient({ runner }).exportHtml("rac", "/tmp/x.html");
    expect(calls[0]).toEqual(["export", "rac", "--html", "--out", "/tmp/x.html"]);
  });

  it("throws RacExecError on a non-zero exit", async () => {
    const runner: RacRunner = async () => ({ stdout: "", stderr: "rac: unwritable", code: 2 });
    await expect(
      new RacClient({ runner }).exportHtml("rac", "/bad/x.html"),
    ).rejects.toBeInstanceOf(RacExecError);
  });
});

describe("agentRules", () => {
  it("generates and parses the per-client file states", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        mode: "generate",
        digest: "abc123",
        root: "/w",
        files: [
          { client: "claude", path: "CLAUDE.md", state: "written" },
          { client: "agents", path: "AGENTS.md", state: "in-sync" },
        ],
      }),
    });
    const result = await new RacClient({ runner }).agentRules("rac", { out: "/w" });
    expect(result.mode).toBe("generate");
    expect(result.digest).toBe("abc123");
    expect(result.files[0]?.state).toBe("written");
    expect(calls[0]).toEqual(["export", "rac", "--agent-rules", "--json", "--out", "/w"]);
  });

  it("passes --check and restricts clients, returning drift on exit 1", async () => {
    const { runner, calls } = fakeRunner({
      code: 1,
      stdout: JSON.stringify({
        mode: "check",
        digest: "def456",
        root: "/w",
        files: [{ client: "claude", path: "CLAUDE.md", state: "stale" }],
      }),
    });
    const result = await new RacClient({ runner }).agentRules("rac", {
      check: true,
      clients: ["claude"],
    });
    expect(result.mode).toBe("check");
    expect(result.files[0]?.state).toBe("stale");
    expect(calls[0]).toEqual([
      "export",
      "rac",
      "--agent-rules",
      "--json",
      "--check",
      "--client",
      "claude",
    ]);
  });
});

describe("error mapping", () => {
  it("raises RacNotFoundError when the binary cannot be spawned", async () => {
    const runner: RacRunner = async () => {
      const err = new Error("spawn rac ENOENT") as NodeJS.ErrnoException;
      err.code = "ENOENT";
      throw err;
    };
    await expect(new RacClient({ runner }).validateFile("a.md")).rejects.toBeInstanceOf(
      RacNotFoundError,
    );
  });

  it("raises RacExecError on a usage error (exit 2, stderr, no JSON)", async () => {
    const runner: RacRunner = async () => ({
      stdout: "",
      stderr: "rac: file not found: a.md",
      code: 2,
    });
    await expect(new RacClient({ runner }).validateFile("a.md")).rejects.toBeInstanceOf(
      RacExecError,
    );
  });

  it("raises RacOutputError on a clean exit with non-JSON output", async () => {
    const runner: RacRunner = async () => ({ stdout: "not json", stderr: "", code: 0 });
    await expect(new RacClient({ runner }).stats("rac")).rejects.toBeInstanceOf(
      RacOutputError,
    );
  });
});

describe("init", () => {
  it("runs `rac init <dir> --json` with the key and parses the result", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        repository_key: "DEMO",
        config_path: "/w/.rac/config.yaml",
        created: true,
      }),
    });
    const result = await new RacClient({ runner }).init("/w", "DEMO");
    expect(result.repository_key).toBe("DEMO");
    expect(result.created).toBe(true);
    expect(calls[0]).toEqual(["init", "/w", "--json", "--key", "DEMO"]);
  });

  it("omits --key when not given", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        repository_key: "W",
        config_path: "p",
        created: true,
      }),
    });
    await new RacClient({ runner }).init("/w");
    expect(calls[0]).toEqual(["init", "/w", "--json"]);
  });
});

describe("quickstart", () => {
  it("runs `rac quickstart <dir> --json` with key/type and parses the scaffolded artifact", async () => {
    const { runner, calls } = fakeRunner({
      stdout: JSON.stringify({
        schema_version: "1",
        repository_key: "DEMO",
        config_path: "/w/.rac/config.yaml",
        created: true,
        artifact: {
          type: "requirement",
          path: "/w/rac/requirements/first-requirement.md",
          id: "DEMO-KV8QR2AVYDFN",
        },
      }),
    });
    const result = await new RacClient({ runner }).quickstart("/w", {
      key: "DEMO",
      type: "requirement",
    });
    expect(result.repository_key).toBe("DEMO");
    expect(result.artifact.id).toBe("DEMO-KV8QR2AVYDFN");
    expect(result.artifact.path).toContain("first-requirement.md");
    expect(calls[0]).toEqual([
      "quickstart",
      "/w",
      "--json",
      "--key",
      "DEMO",
      "--type",
      "requirement",
    ]);
  });
});
