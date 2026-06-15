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
 *  - hover and go-to-definition on artifact IDs / aliases via `rac resolve`.
 *
 * The file is organized into clearly delimited sections; a module split is
 * scoped for v0.21.6 (robustness/release).
 */

import * as path from "node:path";

import * as vscode from "vscode";

import {
  RacClient,
  RacNotFoundError,
  isResolved,
  type CorpusExport,
  type FileValidation,
  type Issue,
  type RelationshipIssue,
  type RelationshipValidation,
  type ResolvedArtifact,
} from "@rac/sdk";

const DEBOUNCE_MS = 300;
const RELATIONSHIP_DEBOUNCE_MS = 600;
const ARTIFACT_TYPES = ["requirement", "decision", "roadmap", "prompt", "design"];

let diagnostics: vscode.DiagnosticCollection;
let relationshipDiagnostics: vscode.DiagnosticCollection;
const clients = new Map<string, RacClient>();
const exportCache = new Map<string, CorpusExport>();
const debounce = new Map<string, ReturnType<typeof setTimeout>>();
const relationshipDebounce = new Map<string, ReturnType<typeof setTimeout>>();
let warnedMissing = false;

export function activate(context: vscode.ExtensionContext): void {
  diagnostics = vscode.languages.createDiagnosticCollection("rac");
  relationshipDiagnostics = vscode.languages.createDiagnosticCollection("rac-relationships");
  const selector: vscode.DocumentSelector = { language: "markdown", scheme: "file" };

  context.subscriptions.push(
    diagnostics,
    relationshipDiagnostics,
    vscode.workspace.onDidOpenTextDocument((doc) => void validateDocument(doc)),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      void validateDocument(doc);
      scheduleRelationshipsFor(doc);
      invalidateExportFor(doc);
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
        void validateWorkspace();
        refreshAllRelationships();
      }
    }),
    vscode.commands.registerCommand("rac.validateWorkspace", validateWorkspace),
    vscode.commands.registerCommand("rac.newArtifact", newArtifact),
    vscode.languages.registerHoverProvider(selector, { provideHover }),
    vscode.languages.registerDefinitionProvider(selector, { provideDefinition }),
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
}

export function deactivate(): void {
  for (const timer of debounce.values()) clearTimeout(timer);
  for (const timer of relationshipDebounce.values()) clearTimeout(timer);
  debounce.clear();
  relationshipDebounce.clear();
  diagnostics?.clear();
  diagnostics?.dispose();
  relationshipDiagnostics?.clear();
  relationshipDiagnostics?.dispose();
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
    else console.error("RAC: relationship validation failed", err);
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
