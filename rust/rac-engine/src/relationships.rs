//! Relationship extraction and validation (`rac.services.references`,
//! `rac.services.relationships`, `rac.core.relationship_types`), per
//! PORT-CONTRACT.d/05.
//!
//! Covers the surfaces the validate/corpus parity gate needs:
//! `validate_relationships` (directory), `validate_relationships_file`, and
//! `validate_document_against_corpus` (the `rac validate - --corpus` seam).

use std::collections::HashMap;
use std::path::PathBuf;

use crate::classify::classify;
use crate::identity::{artifact_identifier, artifact_identifiers, strip_list_marker};
use crate::parse::{parse_file, Artifact};
use crate::pycompat::{py_casefold, py_splitlines, py_strip};
use crate::spec::{spec_for, ArtifactSpec, RELATIONSHIP_SECTIONS};
use crate::validate::repository_root;
use crate::walk::find_markdown_files;

// Stable issue codes (JSON contract).
pub const ISSUE_DUPLICATE_IDENTIFIER: &str = "duplicate-artifact-identifier";
pub const ISSUE_TARGET_NOT_FOUND: &str = "relationship-target-not-found";
pub const ISSUE_TARGET_AMBIGUOUS: &str = "relationship-target-ambiguous";
pub const ISSUE_SELF_REFERENCE: &str = "relationship-self-reference";
pub const ISSUE_EDGE_UNSUPPORTED: &str = "relationship-edge-unsupported";
pub const ISSUE_TARGET_SUPERSEDED: &str = "relationship-target-superseded";
pub const ISSUE_TARGET_TYPE_MISMATCH: &str = "relationship-target-type-mismatch";
pub const ISSUE_RELATIONSHIP_CYCLE: &str = "relationship-cycle";
pub const ISSUE_SCOPE_TARGET_NOT_FOUND: &str = "applies-to-target-not-found";

/// Canonical intrinsic severity per finding (`RELATIONSHIP_SEVERITY`).
pub fn relationship_severity(code: &str) -> &'static str {
    match code {
        ISSUE_TARGET_NOT_FOUND
        | ISSUE_TARGET_AMBIGUOUS
        | ISSUE_TARGET_TYPE_MISMATCH
        | ISSUE_RELATIONSHIP_CYCLE
        | ISSUE_DUPLICATE_IDENTIFIER
        | ISSUE_SCOPE_TARGET_NOT_FOUND => "error",
        ISSUE_TARGET_SUPERSEDED | ISSUE_SELF_REFERENCE | ISSUE_EDGE_UNSUPPORTED => "warning",
        _ => "warning",
    }
}

// ---------------------------------------------------------------------------
// Edge registry (rac.core.relationship_types)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct EdgeSpec {
    pub name: &'static str,
    pub range: &'static [&'static str],
    pub acyclic: bool,
    pub forbids_target_status: bool,
    pub external: bool,
    pub filesystem_scoped: bool,
}

/// `edge_spec(name)` over the built-in registry.
pub fn edge_spec(name: &str) -> Option<&'static EdgeSpec> {
    static REGISTRY: [EdgeSpec; 9] = [
        EdgeSpec {
            name: "related_requirements",
            range: &["requirement"],
            acyclic: false,
            forbids_target_status: true,
            external: false,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "related_decisions",
            range: &["decision"],
            acyclic: false,
            forbids_target_status: true,
            external: false,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "related_roadmaps",
            range: &["roadmap"],
            acyclic: false,
            forbids_target_status: true,
            external: false,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "related_prompts",
            range: &["prompt"],
            acyclic: false,
            forbids_target_status: true,
            external: false,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "related_designs",
            range: &["design"],
            acyclic: false,
            forbids_target_status: true,
            external: false,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "supersedes",
            range: &["decision"],
            acyclic: true,
            forbids_target_status: false,
            external: false,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "related_tickets",
            range: &[],
            acyclic: false,
            forbids_target_status: true,
            external: true,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "verified_by",
            range: &[],
            acyclic: false,
            forbids_target_status: true,
            external: true,
            filesystem_scoped: false,
        },
        EdgeSpec {
            name: "applies_to",
            range: &[],
            acyclic: false,
            forbids_target_status: true,
            external: true,
            filesystem_scoped: true,
        },
    ];
    REGISTRY.iter().find(|e| e.name == name)
}

fn snake(section: &str) -> String {
    section.replace(' ', "_")
}

// ---------------------------------------------------------------------------
// Reference extraction (rac.services.references)
// ---------------------------------------------------------------------------

/// `parse_references(body)`: one reference per non-empty line, one leading
/// well-formed list marker stripped.
pub fn parse_references(body: &str) -> Vec<String> {
    let mut refs = Vec::new();
    for line in py_splitlines(body) {
        let stripped = py_strip(line);
        if stripped.is_empty() {
            continue;
        }
        refs.push(py_strip(strip_list_marker(stripped)).to_string());
    }
    refs
}

/// `extract_relationships_full(product, spec)`: `{snake_section -> refs}` in
/// `spec.optional` order, including `supersedes`.
pub fn extract_relationships_full(
    artifact: &Artifact,
    spec: &ArtifactSpec,
) -> Vec<(String, Vec<String>)> {
    let mut out = Vec::new();
    for section in &spec.optional {
        if !RELATIONSHIP_SECTIONS.iter().any(|(name, _)| name == section) {
            continue;
        }
        let Some(body) = artifact.section(section) else {
            continue;
        };
        if body.is_empty() {
            continue;
        }
        let refs = parse_references(body);
        if !refs.is_empty() {
            out.push((snake(section), refs));
        }
    }
    out
}

/// `unsupported_relationship_sections(product, spec)`: canonical-order
/// relationship sections declared with refs but absent from `spec.optional`.
pub fn unsupported_relationship_sections(artifact: &Artifact, spec: &ArtifactSpec) -> Vec<String> {
    let mut out = Vec::new();
    for (section, _) in RELATIONSHIP_SECTIONS.iter() {
        if spec.optional.iter().any(|s| s == section) {
            continue;
        }
        let Some(body) = artifact.section(section) else {
            continue;
        };
        if !body.is_empty() && !parse_references(body).is_empty() {
            out.push(section.to_string());
        }
    }
    out
}

/// `_is_retired_artifact(product, spec)`.
fn is_retired(artifact: &Artifact, spec: &ArtifactSpec) -> bool {
    if spec.retired_status.is_empty() {
        return false;
    }
    let Some(body) = artifact.section("status") else {
        return false;
    };
    if body.is_empty() {
        return false;
    }
    let first = py_splitlines(body)
        .into_iter()
        .map(py_strip)
        .find(|l| !l.is_empty())
        .unwrap_or("");
    let ff = py_casefold(first);
    spec.retired_status.iter().any(|s| py_casefold(s) == ff)
}

// ---------------------------------------------------------------------------
// Compact validation rows + resolution index (ADR-108)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct ValidationRow {
    pub path: String,
    /// Artifact type name, or None for an Unknown/untyped document.
    pub spec_name: Option<String>,
    pub canonical_id: String,
    pub identifiers: Vec<String>,
    pub retired: bool,
    /// Canonical (space) section names.
    pub unsupported_sections: Vec<String>,
    /// `(snake_section, refs)` in schema order.
    pub edges: Vec<(String, Vec<String>)>,
}

/// `validation_row(path, product, spec)`.
pub fn validation_row(
    path: &str,
    artifact: &Artifact,
    spec: Option<&ArtifactSpec>,
) -> ValidationRow {
    let identifiers = artifact_identifiers(artifact, spec, path);
    let canonical_id = artifact_identifier(artifact, spec, path);
    match spec {
        None => ValidationRow {
            path: path.to_string(),
            spec_name: None,
            canonical_id,
            identifiers,
            retired: false,
            unsupported_sections: Vec::new(),
            edges: Vec::new(),
        },
        Some(spec) => ValidationRow {
            path: path.to_string(),
            spec_name: Some(spec.name.clone()),
            canonical_id,
            identifiers,
            retired: is_retired(artifact, spec),
            unsupported_sections: unsupported_relationship_sections(artifact, spec),
            edges: extract_relationships_full(artifact, spec),
        },
    }
}

/// Insertion-ordered `{casefold(ident) -> [(path, ident)]}` index.
pub struct ResolutionIndex {
    order: Vec<String>,
    map: HashMap<String, Vec<(String, String)>>,
}

impl ResolutionIndex {
    fn new() -> Self {
        ResolutionIndex {
            order: Vec::new(),
            map: HashMap::new(),
        }
    }

    fn insert(&mut self, key: String, value: (String, String)) {
        match self.map.get_mut(&key) {
            Some(v) => v.push(value),
            None => {
                self.map.insert(key.clone(), vec![value]);
                self.order.push(key);
            }
        }
    }

    pub fn get(&self, key: &str) -> &[(String, String)] {
        self.map.get(key).map(|v| v.as_slice()).unwrap_or(&[])
    }

    fn values(&self) -> impl Iterator<Item = &Vec<(String, String)>> {
        self.order.iter().map(|k| &self.map[k])
    }
}

/// `resolution_index_from_rows(rows)`.
pub fn resolution_index_from_rows(rows: &[ValidationRow]) -> ResolutionIndex {
    let mut index = ResolutionIndex::new();
    for row in rows {
        for ident in &row.identifiers {
            index.insert(py_casefold(ident), (row.path.clone(), ident.clone()));
        }
    }
    index
}

// ---------------------------------------------------------------------------
// Findings model
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct RelationshipIssue {
    pub code: String,
    pub source_path: Option<String>,
    pub relationship: Option<String>,
    pub target: Option<String>,
    pub identifier: Option<String>,
    pub paths: Option<Vec<String>>,
}

impl RelationshipIssue {
    fn reference(code: &str, source_path: &str, relationship: &str, target: &str) -> Self {
        RelationshipIssue {
            code: code.to_string(),
            source_path: Some(source_path.to_string()),
            relationship: Some(relationship.to_string()),
            target: Some(target.to_string()),
            identifier: None,
            paths: None,
        }
    }
}

#[derive(Debug)]
pub struct RelationshipValidation {
    pub directory: String,
    pub recursive: bool,
    pub relationships_checked: usize,
    pub issues: Vec<RelationshipIssue>,
}

impl RelationshipValidation {
    pub fn ok(&self) -> bool {
        self.issues.is_empty()
    }
}

// ---------------------------------------------------------------------------
// Scope entries (rac.services.scope_paths)
// ---------------------------------------------------------------------------

/// `classify_scope_entry(entry)` -> "glob" | "path" | "component".
fn classify_scope_entry(entry: &str) -> &'static str {
    if entry.contains('*') || entry.contains('?') || entry.contains('[') {
        "glob"
    } else if entry.contains('/') {
        "path"
    } else {
        "component"
    }
}

/// `normalized_scope_path(entry)` — POSIX repo-relative form, or None.
fn normalized_scope_path(entry: &str) -> Option<String> {
    let text = py_strip(entry);
    if text.is_empty() || text.starts_with('/') {
        return None;
    }
    let mut parts: Vec<&str> = Vec::new();
    for part in text.split('/').filter(|p| !p.is_empty()) {
        if part == "." {
            continue;
        }
        if part == ".." {
            return None;
        }
        parts.push(part);
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join("/"))
    }
}

// ---------------------------------------------------------------------------
// validation_from_rows — the gate core
// ---------------------------------------------------------------------------

fn resolved_unique<'a>(
    index: &'a ResolutionIndex,
    reference: &str,
    source_path: &str,
) -> Option<&'a str> {
    let targets = index.get(&py_casefold(reference));
    if targets.len() != 1 || targets[0].0 == source_path {
        return None;
    }
    Some(&targets[0].0)
}

/// `_resolve_references(rows, index)` -> `(checked, issues)`.
fn resolve_references(
    rows: &[ValidationRow],
    index: &ResolutionIndex,
) -> (usize, Vec<RelationshipIssue>) {
    let mut issues = Vec::new();
    let mut checked = 0usize;
    for row in rows {
        if row.spec_name.is_none() {
            continue;
        }
        for (section, refs) in &row.edges {
            if edge_spec(section).is_some_and(|e| e.external) {
                continue;
            }
            for reference in refs {
                checked += 1;
                let targets = index.get(&py_casefold(reference));
                let code = if targets.is_empty() {
                    ISSUE_TARGET_NOT_FOUND
                } else if targets.len() > 1 {
                    ISSUE_TARGET_AMBIGUOUS
                } else if targets[0].0 == row.path {
                    ISSUE_SELF_REFERENCE
                } else {
                    continue;
                };
                issues.push(RelationshipIssue::reference(
                    code, &row.path, section, reference,
                ));
            }
        }
    }
    (checked, issues)
}

/// Tarjan SCC over the sorted-adjacency graph; components of size > 1,
/// each sorted, ordered by first element.
fn cyclic_components(adjacency: &[(String, Vec<String>)]) -> Vec<Vec<String>> {
    let adj: HashMap<&str, &Vec<String>> =
        adjacency.iter().map(|(k, v)| (k.as_str(), v)).collect();
    let mut nodes: Vec<&str> = adjacency
        .iter()
        .flat_map(|(k, vs)| std::iter::once(k.as_str()).chain(vs.iter().map(|v| v.as_str())))
        .collect();
    nodes.sort();
    nodes.dedup();

    struct State<'a> {
        indices: HashMap<&'a str, usize>,
        lowlink: HashMap<&'a str, usize>,
        on_stack: std::collections::HashSet<&'a str>,
        stack: Vec<&'a str>,
        counter: usize,
        components: Vec<Vec<String>>,
    }

    fn strongconnect<'a>(
        v: &'a str,
        adj: &HashMap<&'a str, &'a Vec<String>>,
        st: &mut State<'a>,
    ) {
        st.indices.insert(v, st.counter);
        st.lowlink.insert(v, st.counter);
        st.counter += 1;
        st.stack.push(v);
        st.on_stack.insert(v);
        if let Some(neighbors) = adj.get(v) {
            for w in neighbors.iter() {
                let w = w.as_str();
                if !st.indices.contains_key(w) {
                    strongconnect(w, adj, st);
                    let lw = st.lowlink[w];
                    let lv = st.lowlink[v];
                    st.lowlink.insert(v, lv.min(lw));
                } else if st.on_stack.contains(w) {
                    let iw = st.indices[w];
                    let lv = st.lowlink[v];
                    st.lowlink.insert(v, lv.min(iw));
                }
            }
        }
        if st.lowlink[v] == st.indices[v] {
            let mut component: Vec<String> = Vec::new();
            loop {
                let w = st.stack.pop().expect("stack nonempty");
                st.on_stack.remove(w);
                component.push(w.to_string());
                if w == v {
                    break;
                }
            }
            if component.len() > 1 {
                component.sort();
                st.components.push(component);
            }
        }
    }

    let mut st = State {
        indices: HashMap::new(),
        lowlink: HashMap::new(),
        on_stack: std::collections::HashSet::new(),
        stack: Vec::new(),
        counter: 0,
        components: Vec::new(),
    };
    for node in &nodes {
        if !st.indices.contains_key(node) {
            strongconnect(node, &adj, &mut st);
        }
    }
    st.components.sort_by(|a, b| a[0].cmp(&b[0]));
    st.components
}

fn cycle_issues(rows: &[ValidationRow], index: &ResolutionIndex) -> Vec<RelationshipIssue> {
    // Sorted acyclic edge kinds — today only `supersedes`.
    let mut issues = Vec::new();
    for kind in ["supersedes"] {
        // `_acyclic_adjacency`: {source -> sorted unique resolved non-self targets}.
        let mut adjacency: Vec<(String, Vec<String>)> = Vec::new();
        for row in rows {
            if row.spec_name.is_none() {
                continue;
            }
            let refs = row
                .edges
                .iter()
                .find(|(s, _)| s == kind)
                .map(|(_, r)| r.as_slice())
                .unwrap_or(&[]);
            let mut targets: Vec<String> = Vec::new();
            for reference in refs {
                if let Some(t) = resolved_unique(index, reference, &row.path) {
                    if !targets.iter().any(|x| x == t) {
                        targets.push(t.to_string());
                    }
                }
            }
            if !targets.is_empty() {
                targets.sort();
                adjacency.push((row.path.clone(), targets));
            }
        }
        for component in cyclic_components(&adjacency) {
            issues.push(RelationshipIssue {
                code: ISSUE_RELATIONSHIP_CYCLE.to_string(),
                source_path: None,
                relationship: Some(kind.to_string()),
                target: None,
                identifier: None,
                paths: Some(component),
            });
        }
    }
    issues
}

fn scope_validation_issues(directory: &str, rows: &[ValidationRow]) -> Vec<RelationshipIssue> {
    let root: PathBuf = repository_root(directory);
    let mut issues = Vec::new();
    for row in rows {
        if row.spec_name.is_none() {
            continue;
        }
        for (section, refs) in &row.edges {
            let Some(edge) = edge_spec(section) else {
                continue;
            };
            if !edge.filesystem_scoped {
                continue;
            }
            for reference in refs {
                if classify_scope_entry(reference) != "path" {
                    continue;
                }
                if let Some(normalized) = normalized_scope_path(reference) {
                    if root.join(&normalized).exists() {
                        continue;
                    }
                }
                issues.push(RelationshipIssue::reference(
                    ISSUE_SCOPE_TARGET_NOT_FOUND,
                    &row.path,
                    section,
                    reference,
                ));
            }
        }
    }
    issues
}

/// `validation_from_rows(directory, rows, recursive)` — the single gate core.
pub fn validation_from_rows(
    directory: &str,
    rows: &[ValidationRow],
    recursive: bool,
) -> RelationshipValidation {
    let mut issues: Vec<RelationshipIssue> = Vec::new();

    // Duplicate identifiers first, sorted by display identifier (casefold).
    let mut ident_index = ResolutionIndex::new();
    for row in rows {
        ident_index.insert(
            py_casefold(&row.canonical_id),
            (row.path.clone(), row.canonical_id.clone()),
        );
    }
    let mut duplicates: Vec<(String, Vec<String>)> = Vec::new();
    for entries in ident_index.values() {
        if entries.len() > 1 {
            let display = entries
                .iter()
                .min_by(|a, b| a.0.cmp(&b.0))
                .expect("nonempty")
                .1
                .clone();
            let mut paths: Vec<String> = entries.iter().map(|(p, _)| p.clone()).collect();
            paths.sort();
            duplicates.push((display, paths));
        }
    }
    duplicates.sort_by(|a, b| py_casefold(&a.0).cmp(&py_casefold(&b.0)));
    for (display, dup_paths) in duplicates {
        issues.push(RelationshipIssue {
            code: ISSUE_DUPLICATE_IDENTIFIER.to_string(),
            source_path: None,
            relationship: None,
            target: None,
            identifier: Some(display),
            paths: Some(dup_paths),
        });
    }

    // Edge-legality: unsupported declared sections (canonical order per row).
    for row in rows {
        if row.spec_name.is_none() {
            continue;
        }
        for section in &row.unsupported_sections {
            issues.push(RelationshipIssue {
                code: ISSUE_EDGE_UNSUPPORTED.to_string(),
                source_path: Some(row.path.clone()),
                relationship: Some(snake(section)),
                target: None,
                identifier: None,
                paths: None,
            });
        }
    }

    let index = resolution_index_from_rows(rows);
    let by_path: HashMap<&str, &ValidationRow> =
        rows.iter().map(|r| (r.path.as_str(), r)).collect();

    // Range violations.
    for row in rows {
        if row.spec_name.is_none() {
            continue;
        }
        for (section, refs) in &row.edges {
            let Some(edge) = edge_spec(section) else {
                continue;
            };
            if edge.external {
                continue;
            }
            for reference in refs {
                let Some(target) = resolved_unique(&index, reference, &row.path) else {
                    continue;
                };
                let Some(target_spec) = by_path[target].spec_name.as_deref() else {
                    continue;
                };
                if !edge.range.contains(&target_spec) {
                    issues.push(RelationshipIssue::reference(
                        ISSUE_TARGET_TYPE_MISMATCH,
                        &row.path,
                        section,
                        reference,
                    ));
                }
            }
        }
    }

    // Status-consistency: live source -> retired target.
    for row in rows {
        if row.spec_name.is_none() || row.retired {
            continue;
        }
        for (section, refs) in &row.edges {
            let Some(edge) = edge_spec(section) else {
                continue;
            };
            if edge.external || !edge.forbids_target_status {
                continue;
            }
            for reference in refs {
                let Some(target) = resolved_unique(&index, reference, &row.path) else {
                    continue;
                };
                if by_path[target].retired {
                    issues.push(RelationshipIssue::reference(
                        ISSUE_TARGET_SUPERSEDED,
                        &row.path,
                        section,
                        reference,
                    ));
                }
            }
        }
    }

    // Acyclicity.
    issues.extend(cycle_issues(rows, &index));

    // Referential integrity.
    let (checked, ref_issues) = resolve_references(rows, &index);
    issues.extend(ref_issues);

    // Code-scope existence (appended last).
    issues.extend(scope_validation_issues(directory, rows));

    RelationshipValidation {
        directory: directory.to_string(),
        recursive,
        relationships_checked: checked,
        issues,
    }
}

// ---------------------------------------------------------------------------
// Corpus entry points
// ---------------------------------------------------------------------------

/// One parsed + classified item: `(display path, artifact, spec)`.
pub struct CorpusItem {
    pub path: String,
    pub artifact: Artifact,
    pub spec: Option<&'static ArtifactSpec>,
}

/// `_corpus_items(directory, recursive)` — the sorted-path walk, parsed and
/// classified.
pub fn corpus_items(directory: &str, recursive: bool) -> Vec<CorpusItem> {
    find_markdown_files(directory, recursive)
        .into_iter()
        .map(|entry| {
            let artifact = parse_file(&entry.display);
            let spec = spec_for(&classify(&artifact).artifact_type);
            CorpusItem {
                path: entry.display,
                artifact,
                spec,
            }
        })
        .collect()
}

fn rows_from_items(items: &[CorpusItem]) -> Vec<ValidationRow> {
    items
        .iter()
        .map(|item| validation_row(&item.path, &item.artifact, item.spec))
        .collect()
}

/// `validate_relationships(directory, recursive)`.
pub fn validate_relationships(directory: &str, recursive: bool) -> RelationshipValidation {
    let items = corpus_items(directory, recursive);
    validation_from_rows(directory, &rows_from_items(&items), recursive)
}

/// `validate_relationships_file(path)`.
pub fn validate_relationships_file(path: &str) -> RelationshipValidation {
    let artifact = parse_file(path);
    let spec = spec_for(&classify(&artifact).artifact_type);
    let rows = vec![validation_row(path, &artifact, spec)];
    validation_from_rows(path, &rows, false)
}

/// `validate_document_against_corpus(product, source_path, directory)` — the
/// `rac validate - --corpus DIR` seam (ADR-067).
pub fn validate_document_against_corpus(
    artifact: &Artifact,
    source_path: &str,
    directory: &str,
    recursive: bool,
) -> RelationshipValidation {
    let corpus = corpus_items(directory, recursive);
    let spec = spec_for(&classify(artifact).artifact_type);
    let proposed_ident = py_casefold(&artifact_identifier(artifact, spec, source_path));
    let mut rows: Vec<ValidationRow> = Vec::new();
    for item in &corpus {
        let ident = artifact_identifier(&item.artifact, item.spec, &item.path);
        if py_casefold(&ident) == proposed_ident {
            continue; // the on-disk counterpart of the document being edited
        }
        rows.push(validation_row(&item.path, &item.artifact, item.spec));
    }
    rows.push(validation_row(source_path, artifact, spec));
    let result = validation_from_rows(directory, &rows, recursive);
    let own: Vec<RelationshipIssue> = result
        .issues
        .into_iter()
        .filter(|i| i.source_path.as_deref() == Some(source_path))
        .collect();
    RelationshipValidation {
        directory: directory.to_string(),
        recursive,
        relationships_checked: result.relationships_checked,
        issues: own,
    }
}
