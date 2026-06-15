/**
 * Typed bindings for the `rac … --json` contracts (ADR-007: additive,
 * `schema_version`-gated). These mirror the Python service result `to_dict()`
 * shapes and the `lore-web` viewer's export types; the client deserializes
 * `rac` stdout into them without reinterpreting anything (ADR-063).
 */

export type Severity = "error" | "warning";

/** One validation finding. `line` is null when the issue is file-level. */
export interface Issue {
  severity: Severity;
  code: string;
  message: string;
  line: number | null;
}

// --- rac validate <file> --json ---------------------------------------------

export interface FileValidation {
  file: string;
  valid: boolean;
  errors: Issue[];
  warnings: Issue[];
}

// --- rac validate <dir> --json ----------------------------------------------

export type FileStatus = "valid" | "invalid" | "skipped";

export interface DirectoryFileValidation {
  path: string;
  artifact_type: string;
  status: FileStatus;
  issues: Issue[];
}

export interface ValidationSummary {
  total_files: number;
  checked: number;
  valid: number;
  invalid: number;
  skipped_unknown: number;
}

export interface OkfConformance {
  conformant: boolean;
  artifacts_checked: number;
  findings: unknown[];
}

export interface DirectoryValidation {
  schema_version: string;
  directory: string;
  recursive: boolean;
  summary: ValidationSummary;
  valid: boolean;
  files: DirectoryFileValidation[];
  /** Present when OKF conformance was computed. */
  okf?: OkfConformance;
}

// --- rac resolve <id> --json ------------------------------------------------

export interface ResolvedArtifact {
  schema_version: string;
  id: string;
  type: string;
  title: string;
  path: string;
}

export interface ResolveNotFound {
  schema_version: string;
  error: "not-found";
  id: string;
}

export interface ResolveDuplicate {
  schema_version: string;
  error: "duplicate";
  id: string;
  paths: string[];
}

export type ResolveResult =
  | ResolvedArtifact
  | ResolveNotFound
  | ResolveDuplicate;

/** Narrow a {@link ResolveResult} to a successful resolution. */
export function isResolved(result: ResolveResult): result is ResolvedArtifact {
  return !("error" in result);
}

// --- rac find <query> --json ------------------------------------------------

export interface FindMatch {
  id: string;
  type: string;
  title: string;
  path: string;
  /** Present on a body/heading hit: the section the snippet came from. */
  section?: string;
  /** Present on a body/heading hit: the matched text. */
  snippet?: string;
}

export interface FindResult {
  schema_version: string;
  query: string;
  type: string | null;
  match_count: number;
  matches: FindMatch[];
}

// --- rac relationships --validate --json ------------------------------------

export interface RelationshipIssue {
  source_path: string;
  relationship: string;
  target: string;
  code: string;
}

export interface RelationshipValidation {
  directory: string;
  recursive: boolean;
  relationships_checked: number;
  validation_issues: number;
  issues: RelationshipIssue[];
}

// --- rac review <dir> --json ------------------------------------------------

export interface ReviewIssue {
  priority: number;
  severity: Severity;
  path: string;
  identifier: string;
  code: string;
  message: string;
  action: string;
  impact: string;
}

export interface ReviewReport {
  schema_version: string;
  directory: string;
  recursive: boolean;
  ok: boolean;
  empty: boolean;
  /** Rich inventory/validation/relationship blocks; passed through verbatim. */
  artifacts: unknown;
  validation: unknown;
  relationships: unknown;
  health: { score: number };
  issues: ReviewIssue[];
  actions: string[];
}

// --- rac stats <dir> --json -------------------------------------------------

export interface PortfolioStats {
  directory: string;
  empty: boolean;
  features: number;
  valid_features: number;
  invalid_features: number;
  requirements: number;
  metrics: number;
  risks: number;
  decisions: number;
  relationships: Record<string, number>;
  /** Additional additive fields (ADR-007) are preserved. */
  [key: string]: unknown;
}

// --- rac schema <type> --json ----------------------------------------------

export interface SchemaReference {
  type: string;
  required: string[];
  recommended: string[];
  optional: string[];
  /** Section name → human description. */
  descriptions: Record<string, string>;
  /** Section name → authoring questions. */
  guidance: Record<string, string[]>;
  /** Metadata vocabularies (e.g. status/category enums). */
  metadata: Record<string, unknown>;
}

// --- rac new <type> <path> --json -------------------------------------------

export interface CreatedArtifact {
  schema_version: string;
  created: boolean;
  type: string;
  path: string;
  id: string;
}

// --- rac export <dir> --json (the lore-web viewer payload) ------------------

export interface CorpusMeta {
  name: string;
  rac_version?: string;
  artifact_count?: number;
  sample?: boolean;
}

export interface ExportArtifact {
  id: string;
  aliases: string[];
  type: string;
  status: string;
  title: string;
  path: string;
  body_html: string;
}

export interface ExportRelationship {
  from: string;
  to: string;
  type: string;
}

export interface CorpusExport {
  schema_version: string;
  corpus: CorpusMeta;
  artifacts: ExportArtifact[];
  relationships: ExportRelationship[];
}
