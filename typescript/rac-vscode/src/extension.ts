/**
 * RAC VS Code / Cursor extension.
 *
 * Wires the `@rac/sdk` thin client to the editor. All analysis stays in `rac`
 * (ADR-063); this extension maps its output into the editor:
 *
 *  - validation diagnostics, live as you type (the unsaved buffer is piped
 *    through `rac validate -`), debounced, plus immediately on open/save;
 *  - hover and go-to-definition on artifact IDs / aliases via `rac resolve`.
 */

import * as vscode from "vscode";

import {
  RacClient,
  RacNotFoundError,
  isResolved,
  type FileValidation,
  type Issue,
  type ResolvedArtifact,
} from "@rac/sdk";

const DEBOUNCE_MS = 300;

let diagnostics: vscode.DiagnosticCollection;
const clients = new Map<string, RacClient>();
const debounce = new Map<string, ReturnType<typeof setTimeout>>();
let warnedMissing = false;

export function activate(context: vscode.ExtensionContext): void {
  diagnostics = vscode.languages.createDiagnosticCollection("rac");
  const selector: vscode.DocumentSelector = { language: "markdown", scheme: "file" };

  context.subscriptions.push(
    diagnostics,
    vscode.workspace.onDidOpenTextDocument((doc) => void validateDocument(doc)),
    vscode.workspace.onDidSaveTextDocument((doc) => void validateDocument(doc)),
    vscode.workspace.onDidChangeTextDocument((e) => scheduleValidate(e.document)),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      cancelScheduled(doc);
      diagnostics.delete(doc.uri);
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("rac")) {
        clients.clear();
        void validateWorkspace();
      }
    }),
    vscode.commands.registerCommand("rac.validateWorkspace", validateWorkspace),
    vscode.languages.registerHoverProvider(selector, { provideHover }),
    vscode.languages.registerDefinitionProvider(selector, { provideDefinition }),
  );

  for (const doc of vscode.workspace.textDocuments) void validateDocument(doc);
}

export function deactivate(): void {
  for (const timer of debounce.values()) clearTimeout(timer);
  debounce.clear();
  diagnostics?.clear();
  diagnostics?.dispose();
}

// --- diagnostics ------------------------------------------------------------

function isEnabled(): boolean {
  return vscode.workspace
    .getConfiguration("rac")
    .get<boolean>("validate.enable", true);
}

function scheduleValidate(doc: vscode.TextDocument): void {
  const key = doc.uri.toString();
  const existing = debounce.get(key);
  if (existing) clearTimeout(existing);
  debounce.set(
    key,
    setTimeout(() => {
      debounce.delete(key);
      void validateDocument(doc);
    }, DEBOUNCE_MS),
  );
}

function cancelScheduled(doc: vscode.TextDocument): void {
  const key = doc.uri.toString();
  const existing = debounce.get(key);
  if (existing) {
    clearTimeout(existing);
    debounce.delete(key);
  }
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
    // Validate the current buffer (unsaved edits included) via stdin.
    const result = await clientFor(folder).validateText(doc.getText());
    diagnostics.set(doc.uri, toDiagnostics(result));
  } catch (err) {
    if (err instanceof RacNotFoundError) {
      warnMissingOnce();
      return;
    }
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

// --- hover & go-to-definition ----------------------------------------------

// Reference-ish tokens: identifiers with a hyphen (adr-007, v0.20.0-foo,
// rac-growth-adoption) or a RAC/REQ id. A cheap filter so plain prose words
// don't each trigger a `rac resolve`.
const REFERENCE_WORD = /[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]/;
function looksLikeReference(token: string): boolean {
  return token.includes("-") && /[A-Za-z]/.test(token);
}

async function resolveAt(
  doc: vscode.TextDocument,
  position: vscode.Position,
): Promise<ResolvedArtifact | undefined> {
  if (!looksLikeRacArtifact(doc.getText())) return undefined;
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (!folder) return undefined;
  const range = doc.getWordRangeAtPosition(position, REFERENCE_WORD);
  if (!range) return undefined;
  const token = doc.getText(range);
  if (!looksLikeReference(token)) return undefined;

  try {
    const result = await clientFor(folder).resolve(token);
    return isResolved(result) ? result : undefined;
  } catch (err) {
    if (err instanceof RacNotFoundError) warnMissingOnce();
    return undefined;
  }
}

async function provideHover(
  doc: vscode.TextDocument,
  position: vscode.Position,
): Promise<vscode.Hover | undefined> {
  const target = await resolveAt(doc, position);
  if (!target) return undefined;
  const md = new vscode.MarkdownString(undefined, true);
  md.appendMarkdown(`**${target.title}**\n\n`);
  md.appendMarkdown(`\`${target.type}\` · \`${target.id}\`\n\n`);
  md.appendMarkdown(`[${target.path}](${vscode.Uri.file(target.path)})`);
  return new vscode.Hover(md);
}

async function provideDefinition(
  doc: vscode.TextDocument,
  position: vscode.Position,
): Promise<vscode.Location | undefined> {
  const target = await resolveAt(doc, position);
  if (!target) return undefined;
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (!folder) return undefined;
  // resolve returns a path relative to the client cwd (the workspace folder).
  const uri = vscode.Uri.joinPath(folder.uri, target.path);
  return new vscode.Location(uri, new vscode.Position(0, 0));
}

// --- shared -----------------------------------------------------------------

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

// Only treat Markdown with a leading YAML frontmatter block carrying
// `schema_version` as a RAC artifact. A routing gate, not classification.
const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---/;
function looksLikeRacArtifact(text: string): boolean {
  const match = FRONTMATTER.exec(text);
  return match !== null && /(^|\n)\s*schema_version\s*:/.test(match[1] ?? "");
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
