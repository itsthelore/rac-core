/**
 * RAC VS Code / Cursor extension.
 *
 * Wires the `@rac/sdk` thin client to the editor. All analysis stays in `rac`
 * (ADR-063); this extension maps its output into the editor:
 *
 *  - per-file validation diagnostics, live as you type (the unsaved buffer is
 *    piped through `rac validate -`), debounced, plus immediately on open/save;
 *  - cross-artifact enforcement: broken and retired-target references surfaced
 *    at the reference site, from `rac relationships --validate`;
 *  - authoring aids: artifact-ID completion in relationship sections, quick-fix
 *    insertion of missing sections, and a "New Artifact" command (`rac new`);
 *  - navigation: status-aware hover, go-to-definition, find-all-references,
 *    clickable alias links, an Outline, and workspace symbols;
 *  - ambient awareness: a status-bar health score and workspace-wide diagnostics;
 *  - the RAC Explorer webview (`rac export --html`).
 *
 * Robustness (v0.21.6): the extension activates only in RAC workspaces, caches
 * resolve/export lookups (cleared on save), checks for rac schema-version skew,
 * and logs to a dedicated "RAC" output channel. The file is organized into
 * clearly delimited sections; a module split is a possible future cleanup.
 */

import { readFile, rm } from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";

import * as vscode from "vscode";

import {
  RacClient,
  RacNotFoundError,
  isResolved,
  type CorpusExport,
  type DirectoryValidation,
  type ExportArtifact,
  type FileValidation,
  type Issue,
  type RelationshipIssue,
  type RelationshipValidation,
  type ResolveResult,
  type ResolvedArtifact,
} from "@rac/sdk";

const DEBOUNCE_MS = 300;
const RELATIONSHIP_DEBOUNCE_MS = 600;
const AWARENESS_DEBOUNCE_MS = 800;
const ARTIFACT_TYPES = ["requirement", "decision", "roadmap", "prompt", "design"];
// The JSON schema_version this extension's typed contracts target (ADR-007).
const EXPECTED_SCHEMA_VERSION = "1";

let diagnostics: vscode.DiagnosticCollection;
let relationshipDiagnostics: vscode.DiagnosticCollection;
let workspaceDiagnostics: vscode.DiagnosticCollection;
let statusBar: vscode.StatusBarItem;
let output: vscode.OutputChannel;
const clients = new Map<string, RacClient>();
const exportCache = new Map<string, CorpusExport>();
const resolveCache = new Map<string, ResolveResult>();
const debounce = new Map<string, ReturnType<typeof setTimeout>>();
const relationshipDebounce = new Map<string, ReturnType<typeof setTimeout>>();
const awarenessDebounce = new Map<string, ReturnType<typeof setTimeout>>();
let warnedMissing = false;
let warnedSkew = false;

export function activate(context: vscode.ExtensionContext): void {
  diagnostics = vscode.languages.createDiagnosticCollection("rac");
  relationshipDiagnostics = vscode.languages.createDiagnosticCollection("rac-relationships");
  workspaceDiagnostics = vscode.languages.createDiagnosticCollection("rac-workspace");
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
  statusBar.command = "workbench.actions.view.problems";
  output = vscode.window.createOutputChannel("RAC");
  const selector: vscode.DocumentSelector = { language: "markdown", scheme: "file" };

  context.subscriptions.push(
    diagnostics,
    relationshipDiagnostics,
    workspaceDiagnostics,
    statusBar,
    output,
    vscode.workspace.onDidOpenTextDocument((doc) => {
      void validateDocument(doc);
      // The live per-file collection owns open files; drop any workspace-scan
      // diagnostic for it to avoid duplicates.
      workspaceDiagnostics.delete(doc.uri);
    }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      void validateDocument(doc);
      scheduleRelationshipsFor(doc);
      scheduleAwarenessFor(doc);
      invalidateExportFor(doc);
      resolveCache.clear();
    }),
    vscode.workspace.onDidChangeTextDocument((e) => scheduleValidate(e.document)),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      cancelScheduled(doc);
      diagnostics.delete(doc.uri);
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("rac")) {
        clients.clear();
        exportCache.clear();
        resolveCache.clear();
        void validateWorkspace();
        refreshAllRelationships();
        refreshAllAwareness();
      }
    }),
    vscode.commands.registerCommand("rac.validateWorkspace", validateWorkspace),
    vscode.commands.registerCommand("rac.newArtifact", newArtifact),
    vscode.commands.registerCommand("rac.showExplorer", showExplorer),
    vscode.commands.registerCommand("rac.setupWorkspace", setupWorkspace),
    vscode.commands.registerCommand("rac.installRac", installRac),
    vscode.languages.registerHoverProvider(selector, { provideHover }),
    vscode.languages.registerDefinitionProvider(selector, { provideDefinition }),
    vscode.languages.registerReferenceProvider(selector, { provideReferences }),
    vscode.languages.registerDocumentLinkProvider(selector, { provideDocumentLinks }),
    vscode.languages.registerDocumentSymbolProvider(selector, { provideDocumentSymbols }),
    vscode.languages.registerWorkspaceSymbolProvider({ provideWorkspaceSymbols }),
    vscode.languages.registerCompletionItemProvider(selector, {
      provideCompletionItems: provideCompletions,
    }),
    vscode.languages.registerCodeActionsProvider(
      selector,
      { provideCodeActions },
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] },
    ),
  );

  for (const doc of vscode.workspace.textDocuments) void validateDocument(doc);
  refreshAllRelationships();
  refreshAllAwareness();
  checkAllSchemas();
}

export function deactivate(): void {
  for (const timer of debounce.values()) clearTimeout(timer);
  for (const timer of relationshipDebounce.values()) clearTimeout(timer);
  for (const timer of awarenessDebounce.values()) clearTimeout(timer);
  debounce.clear();
  relationshipDebounce.clear();
  awarenessDebounce.clear();
  diagnostics?.clear();
  diagnostics?.dispose();
  relationshipDiagnostics?.clear();
  relationshipDiagnostics?.dispose();
  workspaceDiagnostics?.clear();
  workspaceDiagnostics?.dispose();
  statusBar?.dispose();
  explorerPanel?.dispose();
  resolveCache.clear();
}

// --- per-file validation ----------------------------------------------------

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
    log("validation failed", err);
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
  refreshAllRelationships();
}

// --- cross-artifact enforcement ---------------------------------------------

// Severity and message per relationship-validation code. The headline split:
// a reference that does not resolve (error) vs. a reference to a retired
// (superseded/deprecated) artifact (warning) — the latter is what makes the
// extension RAC, not a generic linter (ADR-049, ADR-051).
const RELATIONSHIP_SEVERITY: Record<string, vscode.DiagnosticSeverity> = {
  "relationship-target-not-found": vscode.DiagnosticSeverity.Error,
  "relationship-target-ambiguous": vscode.DiagnosticSeverity.Error,
  "relationship-cycle": vscode.DiagnosticSeverity.Error,
  "relationship-target-type-mismatch": vscode.DiagnosticSeverity.Warning,
  "relationship-target-superseded": vscode.DiagnosticSeverity.Warning,
  "relationship-self-reference": vscode.DiagnosticSeverity.Warning,
  "relationship-edge-unsupported": vscode.DiagnosticSeverity.Warning,
};

const RELATIONSHIP_MESSAGE: Record<string, string> = {
  "relationship-target-not-found": "Reference does not resolve",
  "relationship-target-ambiguous": "Ambiguous reference (matches multiple artifacts)",
  "relationship-cycle": "Relationship cycle through",
  "relationship-target-type-mismatch": "Reference resolves to the wrong artifact type",
  "relationship-target-superseded": "References a retired (superseded/deprecated) artifact",
  "relationship-self-reference": "Artifact references itself",
  "relationship-edge-unsupported": "Unsupported relationship for this artifact type",
};

function scheduleRelationshipsFor(doc: vscode.TextDocument): void {
  if (doc.languageId !== "markdown" || doc.uri.scheme !== "file") return;
  if (!looksLikeRacArtifact(doc.getText())) return;
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (folder) scheduleRelationships(folder);
}

function scheduleRelationships(folder: vscode.WorkspaceFolder): void {
  const key = folder.uri.fsPath;
  const existing = relationshipDebounce.get(key);
  if (existing) clearTimeout(existing);
  relationshipDebounce.set(
    key,
    setTimeout(() => {
      relationshipDebounce.delete(key);
      void refreshRelationships(folder);
    }, RELATIONSHIP_DEBOUNCE_MS),
  );
}

function refreshAllRelationships(): void {
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    void refreshRelationships(folder);
  }
}

async function refreshRelationships(folder: vscode.WorkspaceFolder): Promise<void> {
  if (!isEnabled()) return;
  let result: RelationshipValidation;
  try {
    // Relationship validation reads files from disk, so it reflects the saved
    // corpus (not unsaved buffers) — hence save/activation-triggered.
    result = await clientFor(folder).validateRelationships(folder.uri.fsPath);
  } catch (err) {
    if (err instanceof RacNotFoundError) warnMissingOnce();
    else log("relationship validation failed", err);
    return;
  }

  const byFile = new Map<string, RelationshipIssue[]>();
  for (const issue of result.issues) {
    const list = byFile.get(issue.source_path) ?? [];
    list.push(issue);
    byFile.set(issue.source_path, list);
  }

  relationshipDiagnostics.clear();
  for (const [source, issues] of byFile) {
    const uri = path.isAbsolute(source)
      ? vscode.Uri.file(source)
      : vscode.Uri.joinPath(folder.uri, source);
    let doc: vscode.TextDocument;
    try {
      doc = await vscode.workspace.openTextDocument(uri);
    } catch {
      continue; // a referenced source we cannot open — skip rather than guess.
    }
    relationshipDiagnostics.set(
      uri,
      issues.map((issue) => relationshipDiagnostic(doc, issue)),
    );
  }
}

function relationshipDiagnostic(
  doc: vscode.TextDocument,
  issue: RelationshipIssue,
): vscode.Diagnostic {
  const range = findReferenceRange(doc, issue.relationship, issue.target);
  const label = RELATIONSHIP_MESSAGE[issue.code] ?? "Relationship issue";
  const severity = RELATIONSHIP_SEVERITY[issue.code] ?? vscode.DiagnosticSeverity.Warning;
  const diagnostic = new vscode.Diagnostic(range, `${label}: ${issue.target}`, severity);
  diagnostic.source = "rac";
  diagnostic.code = issue.code;
  return diagnostic;
}

// Relationship issues carry no line, so anchor the diagnostic on the target
// token inside the declared relationship section (e.g. "## Related Decisions"),
// falling back to the section heading, then the file head.
function findReferenceRange(
  doc: vscode.TextDocument,
  relationship: string,
  target: string,
): vscode.Range {
  const lines = doc.getText().split(/\r?\n/);
  const heading = relationshipHeading(relationship);
  const headingRe = new RegExp(`^#{1,6}\\s+${escapeRegExp(heading)}\\s*$`, "i");
  const headingIdx = lines.findIndex((line) => headingRe.test(line));

  const from = headingIdx >= 0 ? headingIdx + 1 : 0;
  for (let i = from; i < lines.length; i++) {
    if (headingIdx >= 0 && /^#{1,6}\s+/.test(lines[i])) break; // next heading ends the section
    const col = lines[i].indexOf(target);
    if (col >= 0) return new vscode.Range(i, col, i, col + target.length);
  }
  if (headingIdx >= 0) {
    return new vscode.Range(headingIdx, 0, headingIdx, lines[headingIdx].length);
  }
  return new vscode.Range(0, 0, 0, Number.MAX_SAFE_INTEGER);
}

function relationshipHeading(relationship: string): string {
  // "related_requirements" -> "Related Requirements"
  return relationship
    .split("_")
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// --- ambient awareness ------------------------------------------------------

// A status-bar health score (rac review) and corpus-wide diagnostics
// (rac validate <dir>), refreshed on save/activation. The live per-file
// collection owns open files; the workspace scan covers the rest, so the
// Problems panel reflects the whole corpus without double-reporting.

function scheduleAwarenessFor(doc: vscode.TextDocument): void {
  if (doc.languageId !== "markdown" || doc.uri.scheme !== "file") return;
  if (!looksLikeRacArtifact(doc.getText())) return;
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (folder) scheduleAwareness(folder);
}

function scheduleAwareness(folder: vscode.WorkspaceFolder): void {
  const key = folder.uri.fsPath;
  const existing = awarenessDebounce.get(key);
  if (existing) clearTimeout(existing);
  awarenessDebounce.set(
    key,
    setTimeout(() => {
      awarenessDebounce.delete(key);
      void refreshAwareness(folder);
    }, AWARENESS_DEBOUNCE_MS),
  );
}

function refreshAllAwareness(): void {
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    void refreshAwareness(folder);
  }
}

async function refreshAwareness(folder: vscode.WorkspaceFolder): Promise<void> {
  if (!isEnabled()) return;
  await Promise.allSettled([refreshStatusBar(folder), refreshWorkspaceDiagnostics(folder)]);
}

async function refreshStatusBar(folder: vscode.WorkspaceFolder): Promise<void> {
  try {
    const review = await clientFor(folder).review(folder.uri.fsPath);
    statusBar.text = `$(pulse) RAC ${review.health.score}/100`;
    statusBar.tooltip = review.ok
      ? "RAC corpus: no blocking findings — click for Problems"
      : "RAC corpus: blocking findings — click for Problems";
    statusBar.show();
  } catch (err) {
    if (err instanceof RacNotFoundError) {
      statusBar.hide();
      warnMissingOnce();
    } else {
      log("review failed", err);
    }
  }
}

async function refreshWorkspaceDiagnostics(folder: vscode.WorkspaceFolder): Promise<void> {
  let result: DirectoryValidation;
  try {
    result = await clientFor(folder).validateDirectory(folder.uri.fsPath);
  } catch (err) {
    if (err instanceof RacNotFoundError) warnMissingOnce();
    else log("directory validation failed", err);
    return;
  }

  workspaceDiagnostics.clear();
  const openPaths = new Set(vscode.workspace.textDocuments.map((d) => d.uri.fsPath));
  for (const file of result.files) {
    if (file.issues.length === 0) continue;
    const uri = path.isAbsolute(file.path)
      ? vscode.Uri.file(file.path)
      : vscode.Uri.joinPath(folder.uri, file.path);
    if (openPaths.has(uri.fsPath)) continue; // live diagnostics own open files
    workspaceDiagnostics.set(uri, file.issues.map(issueToDiagnostic));
  }
}

// --- corpus visualization (RAC Explorer webview) ----------------------------

// `rac export --html` already produces a self-contained Portal viewer (the
// lore-web build with the corpus injected, offline, no network). The command
// renders it in a webview; re-running it refreshes. Graph ↔ editor sync
// (v0.21.7): the vendored viewer posts `ready`/`open-artifact` to this host
// and listens for `reveal-artifact`, so selecting an artifact opens its file
// and the active editor's artifact is revealed in the graph. The extension
// forwards a path to open and an id to reveal; it derives nothing (ADR-063).

let explorerPanel: vscode.WebviewPanel | undefined;

async function showExplorer(): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    void vscode.window.showErrorMessage("RAC: open a workspace folder first.");
    return;
  }
  if (!explorerPanel) {
    const panel = vscode.window.createWebviewPanel(
      "racExplorer",
      "RAC Explorer",
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        // The Portal is self-contained (inlined scripts/styles/fonts) and loads
        // no local files, so deny all local resource roots.
        localResourceRoots: [],
      },
    );
    explorerPanel = panel;
    // Wired only while the panel lives: the webview asks to open artifacts, and
    // switching the active editor reveals its artifact in the graph.
    const subs = [
      panel.webview.onDidReceiveMessage((message: unknown) => {
        void handleExplorerMessage(folder, message);
      }),
      vscode.window.onDidChangeActiveTextEditor((editor) => {
        void revealArtifact(folder, editor?.document);
      }),
    ];
    panel.onDidDispose(() => {
      for (const sub of subs) sub.dispose();
      explorerPanel = undefined;
    });
  }
  explorerPanel.reveal(vscode.ViewColumn.Beside);
  await loadExplorer(folder);
}

// A message from the Explorer webview. Only known types act, and `open-artifact`
// resolves the id against the cached export — so the path opened is the engine's,
// never one supplied by the webview, and it is confined to the workspace.
async function handleExplorerMessage(
  folder: vscode.WorkspaceFolder,
  message: unknown,
): Promise<void> {
  if (typeof message !== "object" || message === null) return;
  const type = (message as { type?: unknown }).type;
  if (type === "ready") {
    await revealArtifact(folder, vscode.window.activeTextEditor?.document);
    return;
  }
  if (type === "open-artifact") {
    const id = (message as { id?: unknown }).id;
    if (typeof id === "string") await openArtifactById(folder, id);
  }
}

async function openArtifactById(
  folder: vscode.WorkspaceFolder,
  id: string,
): Promise<void> {
  const corpus = await corpusExport(folder);
  const artifact = corpus?.artifacts.find((a) => a.id === id);
  if (!artifact) return;
  const uri = artifactUri(folder, artifact.path);
  if (!isInsideFolder(folder, uri)) return;
  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.One });
  } catch {
    // A path that no longer opens is not actionable from here; ignore.
  }
}

// Ask the graph to reveal the artifact for `doc`, when it is an artifact file
// inside this workspace folder. No-op otherwise (e.g. a non-artifact editor).
async function revealArtifact(
  folder: vscode.WorkspaceFolder,
  doc: vscode.TextDocument | undefined,
): Promise<void> {
  const panel = explorerPanel;
  if (!panel || !doc || doc.uri.scheme !== "file") return;
  if (vscode.workspace.getWorkspaceFolder(doc.uri)?.uri.fsPath !== folder.uri.fsPath) {
    return;
  }
  const corpus = await corpusExport(folder);
  if (!corpus) return;
  const target = doc.uri.fsPath;
  const artifact = corpus.artifacts.find(
    (a) => artifactUri(folder, a.path).fsPath === target,
  );
  if (artifact) {
    void panel.webview.postMessage({ type: "reveal-artifact", id: artifact.id });
  }
}

function isInsideFolder(folder: vscode.WorkspaceFolder, uri: vscode.Uri): boolean {
  const rel = path.relative(folder.uri.fsPath, uri.fsPath);
  return rel !== "" && !rel.startsWith("..") && !path.isAbsolute(rel);
}

async function loadExplorer(folder: vscode.WorkspaceFolder): Promise<void> {
  const panel = explorerPanel;
  if (!panel) return;
  panel.webview.html = explorerMessage("Building the corpus graph…");
  const out = path.join(os.tmpdir(), `rac-explorer-${Date.now()}.html`);
  try {
    await clientFor(folder).exportHtml(folder.uri.fsPath, out);
    const html = await readFile(out, "utf8");
    if (explorerPanel === panel) {
      panel.webview.html = hardenWebviewHtml(html, panel.webview.cspSource);
    }
  } catch (err) {
    if (err instanceof RacNotFoundError) warnMissingOnce();
    if (explorerPanel === panel) {
      const detail = err instanceof Error ? err.message : String(err);
      panel.webview.html = explorerMessage(`RAC Explorer unavailable: ${escapeHtmlText(detail)}`);
    }
  } finally {
    void rm(out, { force: true }).catch(() => undefined);
  }
}

// A strict Content-Security-Policy for the Explorer webview. The exported Portal
// is self-contained — inline scripts and styles, data: fonts and images, and no
// network — so `default-src 'none'` blocks any exfiltration (there is no
// connect-src). Inline script/style and data: assets keep the offline viewer
// working; the vendored shell uses no eval/WebAssembly, so 'unsafe-eval' is
// deliberately not granted. `cspSource` is included so VS Code's own injected
// webview resources (e.g. the `acquireVsCodeApi` bridge the sync relies on) are
// permitted. The bridge itself stays origin-checked in handleExplorerMessage
// (known message types only; opened paths confined to the workspace).
function explorerCsp(cspSource: string): string {
  return [
    "default-src 'none'",
    `img-src ${cspSource} data:`,
    `font-src ${cspSource} data:`,
    `style-src ${cspSource} 'unsafe-inline'`,
    `script-src ${cspSource} 'unsafe-inline'`,
  ].join("; ");
}

function hardenWebviewHtml(html: string, cspSource: string): string {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${explorerCsp(cspSource)}">`;
  // Insert the CSP as the first child of <head> so it governs the whole document.
  return html.includes("<head>")
    ? html.replace("<head>", `<head>${meta}`)
    : `${meta}${html}`;
}

function explorerMessage(text: string): string {
  return (
    "<!DOCTYPE html><html><body " +
    'style="font-family: var(--vscode-font-family); padding: 1rem; ' +
    'color: var(--vscode-foreground)">' +
    text +
    "</body></html>"
  );
}

function escapeHtmlText(value: string): string {
  return value.replace(/[&<>]/g, (char) =>
    char === "&" ? "&amp;" : char === "<" ? "&lt;" : "&gt;",
  );
}

// --- authoring: completion, quick-fixes, new artifact -----------------------

// Artifact-ID completion fires inside a relationship section, offering human
// aliases from the corpus export (cached, invalidated on save).
const RELATIONSHIP_HEADING = /^#{1,6}\s+(Related\s+\w+|Supersedes)\b/i;

function inRelationshipSection(doc: vscode.TextDocument, line: number): boolean {
  for (let i = line; i >= 0; i--) {
    const text = doc.lineAt(i).text;
    if (/^#{1,6}\s+/.test(text)) return RELATIONSHIP_HEADING.test(text);
  }
  return false;
}

async function provideCompletions(
  doc: vscode.TextDocument,
  position: vscode.Position,
): Promise<vscode.CompletionItem[] | undefined> {
  if (!looksLikeRacArtifact(doc.getText())) return undefined;
  if (!inRelationshipSection(doc, position.line)) return undefined;
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (!folder) return undefined;
  const corpus = await corpusExport(folder);
  if (!corpus) return undefined;

  // Replace the whole hyphenated token under the cursor, so accepting "adr-007"
  // after typing "adr-" produces "adr-007", not "adr-adr-007".
  const replaceRange = doc.getWordRangeAtPosition(position, REFERENCE_WORD);

  const items: vscode.CompletionItem[] = [];
  for (const artifact of corpus.artifacts) {
    for (const alias of artifact.aliases) {
      if (alias === artifact.id) continue; // offer human aliases, not the opaque id
      const item = new vscode.CompletionItem(alias, vscode.CompletionItemKind.Reference);
      item.detail = `${artifact.type} — ${artifact.title}`;
      item.insertText = alias;
      if (replaceRange) item.range = replaceRange;
      items.push(item);
    }
  }
  return items;
}

function provideCodeActions(
  doc: vscode.TextDocument,
  _range: vscode.Range,
  context: vscode.CodeActionContext,
): vscode.CodeAction[] {
  const actions: vscode.CodeAction[] = [];
  for (const diagnostic of context.diagnostics) {
    if (diagnostic.source !== "rac" || typeof diagnostic.code !== "string") continue;

    if (diagnostic.code === "missing-title") {
      // A title is a top-level `# ` heading, not a `## ` section — insert it
      // after any frontmatter rather than appending a bogus "## Title" section
      // (which would not clear the finding).
      const action = new vscode.CodeAction(
        "Insert title heading",
        vscode.CodeActionKind.QuickFix,
      );
      action.diagnostics = [diagnostic];
      const edit = new vscode.WorkspaceEdit();
      edit.insert(doc.uri, titleInsertPosition(doc), "# Title\n\n");
      action.edit = edit;
      actions.push(action);
      continue;
    }

    // The remaining missing-<section> codes (problem, requirements, risks,
    // success-metrics) are genuine `## ` sections.
    const match = /^missing-(.+)$/.exec(diagnostic.code);
    if (!match) continue;
    const title = titleCase(match[1].replace(/-/g, " "));
    const action = new vscode.CodeAction(
      `Insert "## ${title}" section`,
      vscode.CodeActionKind.QuickFix,
    );
    action.diagnostics = [diagnostic];
    const edit = new vscode.WorkspaceEdit();
    const text = doc.getText();
    const separator = text.endsWith("\n") ? "\n" : "\n\n";
    edit.insert(doc.uri, endOfDocument(doc), `${separator}## ${title}\n\n`);
    action.edit = edit;
    actions.push(action);
  }
  return actions;
}

// A title goes immediately after the YAML frontmatter block, else at the top.
function titleInsertPosition(doc: vscode.TextDocument): vscode.Position {
  const lines = doc.getText().split(/\r?\n/);
  if (lines[0] === "---") {
    for (let i = 1; i < lines.length; i++) {
      if (lines[i] === "---") return new vscode.Position(i + 1, 0);
    }
  }
  return new vscode.Position(0, 0);
}

function endOfDocument(doc: vscode.TextDocument): vscode.Position {
  return doc.lineAt(doc.lineCount - 1).range.end;
}

async function newArtifact(): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    void vscode.window.showErrorMessage("RAC: open a workspace folder first.");
    return;
  }
  const type = await vscode.window.showQuickPick(ARTIFACT_TYPES, {
    placeHolder: "Artifact type",
  });
  if (!type) return;

  // Suggest an existing folder — `rac new` won't create missing parents, so
  // steering to a folder that already holds this type avoids a needless error.
  const dir = await pickArtifactFolder(folder, type);
  if (dir === undefined) return;

  const name = await vscode.window.showInputBox({
    prompt: `File name for the new ${type}`,
    value: `new-${type}.md`,
  });
  if (!name) return;
  const relPath = `${dir}/${name}`;

  try {
    const result = await clientFor(folder).createArtifact(type, relPath);
    const uri = vscode.Uri.joinPath(folder.uri, result.path);
    invalidateExport(folder);
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(uri));
  } catch (err) {
    if (err instanceof RacNotFoundError) {
      warnMissingOnce();
      return;
    }
    void vscode.window.showErrorMessage(
      `RAC: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

function titleCase(value: string): string {
  return value.replace(/\b\w/g, (char) => char.toUpperCase());
}

// Offer the workspace-relative folders that already hold artifacts of this type
// (from the cached export). One match is auto-selected; none falls back to the
// conventional `rac/<type>s`. All offered folders exist, so `rac new` succeeds.
async function pickArtifactFolder(
  folder: vscode.WorkspaceFolder,
  type: string,
): Promise<string | undefined> {
  const corpus = await corpusExport(folder);
  const dirs = new Set<string>();
  for (const artifact of corpus?.artifacts ?? []) {
    if (artifact.type !== type) continue;
    // export paths are absolute (the extension passes an absolute dir); make
    // them workspace-relative with forward slashes.
    const rel = vscode.workspace.asRelativePath(vscode.Uri.file(artifact.path), false);
    const slash = rel.lastIndexOf("/");
    if (slash > 0) dirs.add(rel.slice(0, slash));
  }
  const choices = [...dirs].sort();
  if (choices.length === 0) return `rac/${type}s`;
  if (choices.length === 1) return choices[0];
  return vscode.window.showQuickPick(choices, {
    placeHolder: `Folder for the new ${type}`,
  });
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

  const result = await resolveToken(folder, token);
  return result && isResolved(result) ? result : undefined;
}

// Resolve a token, memoized per folder (cleared on save). Caches not-found
// results too, so repeated hovers over plain words don't re-spawn `rac`.
async function resolveToken(
  folder: vscode.WorkspaceFolder,
  token: string,
): Promise<ResolveResult | undefined> {
  const key = `${folder.uri.fsPath}::${token}`;
  const cached = resolveCache.get(key);
  if (cached) return cached;
  try {
    const result = await clientFor(folder).resolve(token);
    resolveCache.set(key, result);
    return result;
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
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  const corpus = folder ? await corpusExport(folder) : undefined;
  const artifact = corpus?.artifacts.find((a) => a.id === target.id);

  const md = new vscode.MarkdownString(undefined, true);
  md.appendMarkdown(`**${target.title}**\n\n`);
  const status = artifact ? statusLabel(artifact.status) : "";
  md.appendMarkdown(`\`${target.type}\`${status ? ` · ${status}` : ""} · \`${target.id}\`\n\n`);
  if (artifact) {
    const snippet = snippetFromHtml(artifact.body_html);
    if (snippet) md.appendMarkdown(`${snippet}\n\n`);
  }
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

// Find-all-references: incoming links from the export's resolved `from → to`
// edges (no extra `rac` call), anchored at the referencing token in each source.
async function provideReferences(
  doc: vscode.TextDocument,
  position: vscode.Position,
): Promise<vscode.Location[] | undefined> {
  const target = await resolveAt(doc, position);
  if (!target) return undefined;
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (!folder) return undefined;
  const corpus = await corpusExport(folder);
  if (!corpus) return undefined;
  const index = buildIndex(corpus);
  const targetAliases = (index.byId.get(target.id)?.aliases ?? [target.id]).map((a) =>
    a.toLowerCase(),
  );

  const locations: vscode.Location[] = [];
  const sourceIds = new Set(
    corpus.relationships.filter((r) => r.to === target.id).map((r) => r.from),
  );
  for (const sourceId of sourceIds) {
    const source = index.byId.get(sourceId);
    if (!source) continue;
    const uri = artifactUri(folder, source.path);
    try {
      const srcDoc = await vscode.workspace.openTextDocument(uri);
      locations.push(new vscode.Location(uri, firstAliasRange(srcDoc, targetAliases)));
    } catch {
      locations.push(new vscode.Location(uri, new vscode.Position(0, 0)));
    }
  }
  return locations;
}

// Make known artifact aliases in the document clickable links to their files.
async function provideDocumentLinks(
  doc: vscode.TextDocument,
): Promise<vscode.DocumentLink[] | undefined> {
  if (!looksLikeRacArtifact(doc.getText())) return undefined;
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (!folder) return undefined;
  const corpus = await corpusExport(folder);
  if (!corpus) return undefined;
  const index = buildIndex(corpus);

  const links: vscode.DocumentLink[] = [];
  const text = doc.getText();
  const tokenRe = /[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]/g;
  for (let m = tokenRe.exec(text); m !== null; m = tokenRe.exec(text)) {
    const token = m[0];
    if (!looksLikeReference(token)) continue;
    const artifact = index.aliasToArtifact.get(token.toLowerCase());
    if (!artifact) continue;
    const range = new vscode.Range(doc.positionAt(m.index), doc.positionAt(m.index + token.length));
    const link = new vscode.DocumentLink(range, artifactUri(folder, artifact.path));
    link.tooltip = `${artifact.type} — ${artifact.title}`;
    links.push(link);
  }
  return links;
}

// Outline: the artifact's own Markdown headings (`#` title, `##` sections).
function provideDocumentSymbols(doc: vscode.TextDocument): vscode.DocumentSymbol[] {
  const symbols: vscode.DocumentSymbol[] = [];
  const lines = doc.getText().split(/\r?\n/);
  let title: vscode.DocumentSymbol | undefined;
  for (let i = 0; i < lines.length; i++) {
    const heading = /^(#{1,6})\s+(.+?)\s*$/.exec(lines[i]);
    if (!heading) continue;
    const level = heading[1].length;
    const range = new vscode.Range(i, 0, i, lines[i].length);
    const symbol = new vscode.DocumentSymbol(
      heading[2],
      "",
      level === 1 ? vscode.SymbolKind.File : vscode.SymbolKind.String,
      range,
      range,
    );
    if (level === 1 || !title) {
      symbols.push(symbol);
      title = symbol;
    } else {
      title.children.push(symbol);
    }
  }
  return symbols;
}

// Workspace symbols: every artifact, reachable by title (VS Code filters).
async function provideWorkspaceSymbols(): Promise<vscode.SymbolInformation[]> {
  const symbols: vscode.SymbolInformation[] = [];
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const corpus = await corpusExport(folder);
    if (!corpus) continue;
    for (const artifact of corpus.artifacts) {
      const uri = artifactUri(folder, artifact.path);
      symbols.push(
        new vscode.SymbolInformation(
          artifact.title,
          vscode.SymbolKind.File,
          artifact.type,
          new vscode.Location(uri, new vscode.Position(0, 0)),
        ),
      );
    }
  }
  return symbols;
}

// `rac export` returns absolute artifact paths when given an absolute directory
// (the extension passes one), so build the Uri from the absolute path directly;
// fall back to joining a relative path onto the workspace folder.
function artifactUri(folder: vscode.WorkspaceFolder, artifactPath: string): vscode.Uri {
  return path.isAbsolute(artifactPath)
    ? vscode.Uri.file(artifactPath)
    : vscode.Uri.joinPath(folder.uri, artifactPath);
}

interface CorpusIndex {
  byId: Map<string, ExportArtifact>;
  aliasToArtifact: Map<string, ExportArtifact>;
}

function buildIndex(corpus: CorpusExport): CorpusIndex {
  const byId = new Map<string, ExportArtifact>();
  const aliasToArtifact = new Map<string, ExportArtifact>();
  for (const artifact of corpus.artifacts) {
    byId.set(artifact.id, artifact);
    for (const alias of artifact.aliases) {
      aliasToArtifact.set(alias.toLowerCase(), artifact);
    }
  }
  return { byId, aliasToArtifact };
}

function firstAliasRange(doc: vscode.TextDocument, aliasesLower: string[]): vscode.Range {
  const lines = doc.getText().split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const lower = lines[i].toLowerCase();
    for (const alias of aliasesLower) {
      const col = lower.indexOf(alias);
      if (col >= 0) return new vscode.Range(i, col, i, col + alias.length);
    }
  }
  return new vscode.Range(0, 0, 0, 0);
}

const RETIRED_STATUS = new Set(["superseded", "deprecated", "abandoned"]);
function statusLabel(status: string): string {
  if (!status || status.toLowerCase() === "unknown") return "";
  return RETIRED_STATUS.has(status.toLowerCase()) ? `⚠ ${status}` : status;
}

function snippetFromHtml(html: string): string {
  // Drop the leading <h1> title (it repeats the bold title above), strip tags.
  const text = html
    .replace(/^[\s\S]*?<\/h1>/i, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
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

// The corpus export, cached per folder and invalidated on save. Powers
// alias-based completion (and, later, hover enrichment).
async function corpusExport(
  folder: vscode.WorkspaceFolder,
): Promise<CorpusExport | undefined> {
  const key = folder.uri.fsPath;
  const cached = exportCache.get(key);
  if (cached) return cached;
  try {
    const data = await clientFor(folder).exportCorpus(folder.uri.fsPath);
    exportCache.set(key, data);
    return data;
  } catch (err) {
    if (err instanceof RacNotFoundError) warnMissingOnce();
    return undefined;
  }
}

function invalidateExport(folder: vscode.WorkspaceFolder): void {
  exportCache.delete(folder.uri.fsPath);
}

function invalidateExportFor(doc: vscode.TextDocument): void {
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  if (folder) invalidateExport(folder);
}

// Only treat Markdown with a leading YAML frontmatter block carrying
// `schema_version` as a RAC artifact. A routing gate, not classification.
const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---/;
function looksLikeRacArtifact(text: string): boolean {
  const match = FRONTMATTER.exec(text);
  return match !== null && /(^|\n)\s*schema_version\s*:/.test(match[1] ?? "");
}

// Version-skew check: a cheap `rac resolve` probe carries `schema_version`
// regardless of outcome. Warn once if the installed rac speaks a contract this
// extension wasn't built against.
function checkAllSchemas(): void {
  for (const folder of vscode.workspace.workspaceFolders ?? []) void checkSchema(folder);
}

async function checkSchema(folder: vscode.WorkspaceFolder): Promise<void> {
  let result: ResolveResult;
  try {
    result = await clientFor(folder).resolve("__rac_schema_probe__");
  } catch (err) {
    if (err instanceof RacNotFoundError) warnMissingOnce();
    return;
  }
  if (result.schema_version !== EXPECTED_SCHEMA_VERSION && !warnedSkew) {
    warnedSkew = true;
    void vscode.window.showWarningMessage(
      `RAC: the installed rac reports schema_version ${result.schema_version}, but this ` +
        `extension targets ${EXPECTED_SCHEMA_VERSION}. Some features may misbehave — ` +
        "update rac or the extension so they match.",
    );
  }
}

function log(message: string, err?: unknown): void {
  const detail =
    err instanceof Error ? `: ${err.message}` : err !== undefined ? `: ${String(err)}` : "";
  output.appendLine(`[${new Date().toISOString()}] ${message}${detail}`);
}

function warnMissingOnce(): void {
  if (warnedMissing) return;
  warnedMissing = true;
  const INSTALL = "Install with pipx";
  const PATH = "Set rac.path";
  void vscode.window
    .showWarningMessage(
      "RAC: the `rac` CLI was not found. Install it, or point the extension at an existing install.",
      INSTALL,
      PATH,
    )
    .then((choice) => {
      if (choice === INSTALL) installRac();
      else if (choice === PATH) {
        void vscode.commands.executeCommand("workbench.action.openSettings", "rac.path");
      }
    });
}

// Open a terminal pre-loaded with the recommended install, for the user to run.
// Wired to the missing-rac prompt and the Get-Started walkthrough.
function installRac(): void {
  const term = vscode.window.createTerminal("Install rac");
  term.show();
  term.sendText("pipx install requirements-as-code");
}

// Scaffold an empty workspace into a RAC corpus via `rac quickstart` (identity +
// a starter artifact), then open it. The thin client computes nothing — `rac`
// establishes the `.rac/config.yaml` identity and the template. Available in any
// workspace (the command activates the extension), not just RAC ones.
async function setupWorkspace(): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    void vscode.window.showErrorMessage("RAC: open a folder first, then set up a corpus.");
    return;
  }
  const config = vscode.Uri.joinPath(folder.uri, ".rac", "config.yaml");
  try {
    await vscode.workspace.fs.stat(config);
    void vscode.window.showInformationMessage(
      "RAC: this workspace already has a corpus (.rac/config.yaml).",
    );
    return;
  } catch {
    // not set up yet — proceed
  }
  // A default repository key from the folder name; `rac` validates/normalizes it.
  const key =
    path.basename(folder.uri.fsPath).replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 12) ||
    "RAC";
  try {
    const result = await clientFor(folder).quickstart(folder.uri.fsPath, { key });
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(result.artifact.path));
    await vscode.window.showTextDocument(doc);
    void vscode.window.showInformationMessage(
      `RAC: corpus ready (key ${result.repository_key}). Edit the starter artifact and save to see it validate.`,
    );
    void validateWorkspace();
    refreshAllRelationships();
  } catch (err) {
    if (err instanceof RacNotFoundError) {
      warnMissingOnce();
      return;
    }
    log("setupWorkspace failed", err);
    void vscode.window.showErrorMessage(
      `RAC: setup failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}
