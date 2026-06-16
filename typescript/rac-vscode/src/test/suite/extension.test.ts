import * as assert from "assert";
import * as path from "path";
import * as vscode from "vscode";

// __dirname is out/test/suite at runtime; the fixture corpus is at the
// extension root.
const corpus = path.resolve(__dirname, "../../../fixtures/corpus");

async function waitFor(
  predicate: () => boolean,
  timeoutMs = 45000,
  intervalMs = 300,
): Promise<void> {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error("timed out waiting for the condition");
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

suite("RAC extension", () => {
  suiteSetup(async () => {
    const ext = vscode.extensions.getExtension("rac.rac-vscode");
    assert.ok(ext, "extension rac.rac-vscode is installed");
    await ext!.activate();
  });

  test("activates and registers its commands", async () => {
    const cmds = await vscode.commands.getCommands(true);
    assert.ok(cmds.includes("rac.showExplorer"), "rac.showExplorer is registered");
    assert.ok(cmds.includes("rac.newArtifact"), "rac.newArtifact is registered");
    assert.ok(
      cmds.includes("rac.validateWorkspace"),
      "rac.validateWorkspace is registered",
    );
    assert.ok(
      cmds.includes("rac.setupWorkspace"),
      "rac.setupWorkspace is registered",
    );
  });

  test("surfaces a relationship violation as a diagnostic", async () => {
    // The fixture roadmap references a Superseded decision and a missing one;
    // `rac relationships --validate` reports both, and the extension maps them
    // to diagnostics at the reference site.
    const uri = vscode.Uri.file(
      path.join(corpus, "rac", "roadmaps", "v0.1.0-sample.md"),
    );
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);

    await waitFor(() => vscode.languages.getDiagnostics(uri).length > 0);

    const diags = vscode.languages.getDiagnostics(uri);
    assert.ok(diags.length > 0, "the sample roadmap has diagnostics");
    const text = diags
      .map((d) => `${d.code ?? ""} ${d.message}`.toLowerCase())
      .join(" | ");
    assert.ok(
      /superseded|retired|not[- ]found|relationship|missing/.test(text),
      `expected a relationship finding, got: ${text}`,
    );
  });
});
