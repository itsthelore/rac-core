import * as assert from "assert";

import {
  HOOK_COMMAND_MARKER,
  HOOK_MATCHER,
  mergeHookSettings,
  removeHookSettings,
  renderHookScript,
} from "../../claudeHook";

// Pure-function coverage for the generated Claude Code pre-edit hook
// (v0.21.17, ADR-067). These need no live editor — they pin the generated
// script body and the non-clobbering settings merge that the enable/disable
// commands rely on. The hook's runtime behaviour (block on a structural finding,
// fail-open otherwise) is exercised against `rac` in the Python test battery.

suite("Claude pre-edit hook generation", () => {
  test("renders a runnable Python script that shells the configured rac binary", () => {
    const script = renderHookScript("rac", "/usr/local/bin/rac");
    assert.ok(script.startsWith("#!/usr/bin/env python3"), "has a python shebang");
    // The corpus and binary are substituted as JSON string literals.
    assert.ok(script.includes('CORPUS = "rac"'), "corpus substituted");
    assert.ok(script.includes('RAC_BIN = "/usr/local/bin/rac"'), "rac binary substituted");
    // The single deterministic gate is `rac validate - --corpus` (ADR-063).
    assert.ok(script.includes('"validate", "-", "--corpus"'), "shells rac validate --corpus");
    // Fail-open and block contract.
    assert.ok(script.includes("sys.exit(0)"), "allows (exit 0)");
    assert.ok(script.includes("sys.exit(2)"), "blocks (exit 2)");
    // No placeholders survive generation.
    assert.ok(!script.includes("{{"), "no unsubstituted placeholders");
  });

  test("escapes a binary path with quotes safely", () => {
    const script = renderHookScript("rac", 'C:\\Program Files\\rac.exe');
    // JSON-encoded so backslashes and spaces are a valid Python string literal.
    assert.ok(script.includes('RAC_BIN = "C:\\\\Program Files\\\\rac.exe"'));
  });

  test("merges into empty settings with the file-mutating matcher", () => {
    const settings = mergeHookSettings({}, "python3 hook.py");
    const entries = settings.hooks?.PreToolUse ?? [];
    assert.strictEqual(entries.length, 1);
    assert.strictEqual(entries[0].matcher, HOOK_MATCHER);
    assert.strictEqual(entries[0].hooks?.[0].command, "python3 hook.py");
  });

  test("does not clobber existing settings or other hook events", () => {
    const existing = {
      env: { FOO: "1" },
      hooks: {
        PreToolUse: [{ matcher: "Bash", hooks: [{ type: "command", command: "echo hi" }] }],
        PostToolUse: [{ matcher: "Edit", hooks: [{ type: "command", command: "fmt" }] }],
      },
    };
    const command = `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/${HOOK_COMMAND_MARKER}"`;
    const merged = mergeHookSettings(existing, command);
    assert.deepStrictEqual(merged.env, { FOO: "1" }, "unrelated keys preserved");
    assert.deepStrictEqual(
      merged.hooks?.PostToolUse,
      existing.hooks.PostToolUse,
      "other hook events untouched",
    );
    const pre = merged.hooks?.PreToolUse ?? [];
    assert.strictEqual(pre.length, 2, "existing Bash entry kept, RAC entry added");
    assert.ok(pre.some((e) => e.matcher === "Bash"), "Bash hook still present");
  });

  test("re-running is idempotent — no duplicate RAC registration", () => {
    const command = `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/${HOOK_COMMAND_MARKER}"`;
    const once = mergeHookSettings({}, command);
    const twice = mergeHookSettings(once, command);
    const racEntries = (twice.hooks?.PreToolUse ?? []).filter((e) =>
      (e.hooks ?? []).some((h) => (h.command ?? "").includes(HOOK_COMMAND_MARKER)),
    );
    assert.strictEqual(racEntries.length, 1);
  });

  test("removing leaves other hooks intact", () => {
    const command = `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/${HOOK_COMMAND_MARKER}"`;
    const withRac = mergeHookSettings(
      { hooks: { PreToolUse: [{ matcher: "Bash", hooks: [{ type: "command", command: "x" }] }] } },
      command,
    );
    const removed = removeHookSettings(withRac);
    const pre = removed.hooks?.PreToolUse ?? [];
    assert.strictEqual(pre.length, 1, "RAC entry gone");
    assert.strictEqual(pre[0].matcher, "Bash", "Bash hook preserved");
  });
});
