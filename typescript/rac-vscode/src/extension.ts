/**
 * RAC VS Code / Cursor extension — MVP.
 *
 * Wires the `@rac/sdk` thin client to the editor: when a RAC artifact is opened
 * or saved, it runs `rac validate <file> --json` and renders the findings as
 * diagnostics. All analysis stays in `rac` (ADR-063); this extension only maps
 * its output into the editor and handles a missing binary gracefully.
 *
 * MVP scope: validation diagnostics on open/save. Live-as-you-type validation
 * (piping the unsaved buffer through `rac validate -`) and ID hover /
 * go-to-definition are follow-ups (roadmap Initiatives 3-4).
 */

import * as vscode from "vscode";

import {
  RacClient,
  RacNotFoundError,
  type FileValidation,
  type Issue,
} from "@rac/sdk";

let diagnostics: vscode.DiagnosticCollection;
const clients = new Map<string, RacClient>();
let warnedMissing = false;

export function activate(context: vscode.ExtensionContext): void {
  diagnostics = vscode.languages.createDiagnosticCollection("rac");
  context.subscriptions.push(
    diagnostics,
    vscode.workspace.onDidOpenTextDocument((doc) => void validateDocument(doc)),
    vscode.workspace.onDidSaveTextDocument((doc) => void validateDocument(doc)),
    vscode.workspace.onDidCloseTextDocument((doc) => diagnostics.delete(doc.uri)),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("rac")) {
        clients.clear();
        void validateWorkspace();
      }
    }),
    vscode.commands.registerCommand("rac.validateWorkspace", validateWorkspace),
  );

  // Validate anything already open when the extension activates.
  for (const doc of vscode.workspace.textDocuments) void validateDocument(doc);
}

export function deactivate(): void {
  diagnostics?.clear();
  diagnostics?.dispose();
}

function isEnabled(): boolean {
  return vscode.workspace
    .getConfiguration("rac")
    .get<boolean>("validate.enable", true);
}

function clientFor(folder: vscode.WorkspaceFolder): RacClient {
  const key = folder.uri.fsPath;
  let client = clients.get(key);
  if (!client) {
    const configured = vscode.workspace
      .getConfiguration("rac", folder.uri)
      .get<string>("path")
      ?.trim();
    client = new RacClient({
      racPath: configured ? configured : undefined,
      cwd: folder.uri.fsPath,
    });
    clients.set(key, client);
  }
  return client;
}

// Only send files that look like RAC artifacts to `rac` — a leading YAML
// frontmatter block carrying `schema_version`. This is a routing gate, not
// classification (which stays in rac); it keeps arbitrary Markdown quiet.
const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---/;
function looksLikeRacArtifact(text: string): boolean {
  const match = FRONTMATTER.exec(text);
  return match !== null && /(^|\n)\s*schema_version\s*:/.test(match[1] ?? "");
}

async function validateDocument(doc: vscode.TextDocument): Promise<void> {
  if (!isEnabled()) return;
  if (doc.languageId !== "markdown" || doc.uri.scheme !== "file") return;
  if (!looksLikeRacArtifact(doc.getText())) {
    diagnostics.delete(doc.uri);
    return;
  }
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (!folder) return;

  try {
    const result = await clientFor(folder).validateFile(doc.uri.fsPath);
    diagnostics.set(doc.uri, toDiagnostics(result));
  } catch (err) {
    if (err instanceof RacNotFoundError) {
      warnMissingOnce();
      return;
    }
    // A usage/output error (e.g. unreadable file) — log, don't disrupt the editor.
    console.error("RAC: validation failed", err);
  }
}

function toDiagnostics(result: FileValidation): vscode.Diagnostic[] {
  return [...result.errors, ...result.warnings].map(issueToDiagnostic);
}

function issueToDiagnostic(issue: Issue): vscode.Diagnostic {
  // rac lines are 1-based; null means file-level (anchor at the first line).
  const line = issue.line && issue.line > 0 ? issue.line - 1 : 0;
  const range = new vscode.Range(line, 0, line, Number.MAX_SAFE_INTEGER);
  const diagnostic = new vscode.Diagnostic(
    range,
    issue.message,
    issue.severity === "error"
      ? vscode.DiagnosticSeverity.Error
      : vscode.DiagnosticSeverity.Warning,
  );
  diagnostic.source = "rac";
  diagnostic.code = issue.code;
  return diagnostic;
}

async function validateWorkspace(): Promise<void> {
  for (const doc of vscode.workspace.textDocuments) {
    await validateDocument(doc);
  }
}

function warnMissingOnce(): void {
  if (warnedMissing) return;
  warnedMissing = true;
  void vscode.window
    .showWarningMessage(
      "RAC: the `rac` CLI was not found. Install it (pip install requirements-as-code) " +
        "or set `rac.path` in settings.",
      "Open Settings",
    )
    .then((choice) => {
      if (choice === "Open Settings") {
        void vscode.commands.executeCommand(
          "workbench.action.openSettings",
          "rac.path",
        );
      }
    });
}
