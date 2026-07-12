//! Portfolio statistics (`rac.services.stats`), per PORT-CONTRACT.d/09 §2.
//!
//! Walks the corpus, classifies each file, and aggregates per family
//! (requirement features, decisions, roadmaps, prompts, designs, unrecognized)
//! plus declared relationship-presence counts. Pure and deterministic.

use crate::classify::classify;
use crate::parse::Artifact;
use crate::pycompat::{first_nonempty_line, py_casefold};
use crate::relationships::corpus_items;
use crate::spec::{spec_for, ArtifactSpec, RELATIONSHIP_SECTIONS};
use crate::validate::validate;

/// Per-file result for a Requirement artifact.
pub struct FeatureStat {
    pub path: String,
    pub name: String,
    pub valid: bool,
    pub error_codes: Vec<String>,
    pub requirements: usize,
    pub success_metrics: usize,
    pub risks: usize,
}

/// Per-file result for a Decision artifact.
pub struct DecisionStat {
    pub path: String,
    pub name: String,
    pub status: Option<String>,
    pub category: Option<String>,
}

/// Lightweight validity stat for roadmap/prompt/design.
pub struct ValidityStat {
    pub path: String,
    pub name: String,
    pub valid: bool,
    pub error_codes: Vec<String>,
}

/// Per-file result for a document that matched no known schema.
pub struct UnrecognizedStat {
    pub path: String,
    pub name: String,
    pub confidence: f64,
}

pub struct PortfolioStats {
    pub directory: String,
    pub features: Vec<FeatureStat>,
    pub decisions: Vec<DecisionStat>,
    pub roadmaps: Vec<ValidityStat>,
    pub prompts: Vec<ValidityStat>,
    pub designs: Vec<ValidityStat>,
    pub unrecognized: Vec<UnrecognizedStat>,
    /// `{canonical space section -> presence count}`, canonical order.
    pub relationship_counts: Vec<(String, usize)>,
}

impl PortfolioStats {
    pub fn files_found(&self) -> usize {
        self.features.len()
    }
    pub fn valid_features(&self) -> usize {
        self.features.iter().filter(|f| f.valid).count()
    }
    pub fn invalid_features(&self) -> usize {
        self.features.iter().filter(|f| !f.valid).count()
    }
    pub fn total_requirements(&self) -> usize {
        self.features.iter().map(|f| f.requirements).sum()
    }
    pub fn total_metrics(&self) -> usize {
        self.features.iter().map(|f| f.success_metrics).sum()
    }
    pub fn total_risks(&self) -> usize {
        self.features.iter().map(|f| f.risks).sum()
    }
    /// Names of features with zero success metrics, in walk order.
    pub fn missing_metrics(&self) -> Vec<&str> {
        self.features
            .iter()
            .filter(|f| f.success_metrics == 0)
            .map(|f| f.name.as_str())
            .collect()
    }
    pub fn missing_risks(&self) -> Vec<&str> {
        self.features
            .iter()
            .filter(|f| f.risks == 0)
            .map(|f| f.name.as_str())
            .collect()
    }
    pub fn average_requirements(&self) -> f64 {
        if self.features.is_empty() {
            return 0.0;
        }
        self.total_requirements() as f64 / self.files_found() as f64
    }
    /// `max(features, key=(requirements, _neg_name(name)))`.
    pub fn largest_feature(&self) -> Option<&FeatureStat> {
        self.features.iter().reduce(|best, f| {
            // Larger requirements wins; tie -> greater _neg_name (earliest
            // name at the first differing code point, LONGER name when one
            // is a prefix of the other — see neg_name_gt).
            match f.requirements.cmp(&best.requirements) {
                std::cmp::Ordering::Greater => f,
                std::cmp::Ordering::Less => best,
                std::cmp::Ordering::Equal => {
                    if neg_name_gt(&f.name, &best.name) {
                        f
                    } else {
                        best
                    }
                }
            }
        })
    }
    /// `sorted(features, key=(-requirements, name))`.
    pub fn requirements_by_feature(&self) -> Vec<&FeatureStat> {
        let mut out: Vec<&FeatureStat> = self.features.iter().collect();
        out.sort_by(|a, b| {
            b.requirements
                .cmp(&a.requirements)
                .then_with(|| a.name.cmp(&b.name))
        });
        out
    }
    pub fn invalid(&self) -> Vec<&FeatureStat> {
        self.features.iter().filter(|f| !f.valid).collect()
    }
    pub fn decision_count(&self) -> usize {
        self.decisions.len()
    }
    pub fn decision_status_counts(&self) -> Vec<(String, usize)> {
        bucket(&self.decisions, |d| d.status.as_deref(), "status")
    }
    pub fn decision_category_counts(&self) -> Vec<(String, usize)> {
        bucket(&self.decisions, |d| d.category.as_deref(), "category")
    }
    pub fn roadmap_count(&self) -> usize {
        self.roadmaps.len()
    }
    pub fn valid_roadmaps(&self) -> usize {
        self.roadmaps.iter().filter(|r| r.valid).count()
    }
    pub fn invalid_roadmaps(&self) -> Vec<&ValidityStat> {
        self.roadmaps.iter().filter(|r| !r.valid).collect()
    }
    pub fn prompt_count(&self) -> usize {
        self.prompts.len()
    }
    pub fn valid_prompts(&self) -> usize {
        self.prompts.iter().filter(|p| p.valid).count()
    }
    pub fn invalid_prompts(&self) -> Vec<&ValidityStat> {
        self.prompts.iter().filter(|p| !p.valid).collect()
    }
    pub fn design_count(&self) -> usize {
        self.designs.len()
    }
    pub fn valid_designs(&self) -> usize {
        self.designs.iter().filter(|d| d.valid).count()
    }
    pub fn invalid_designs(&self) -> Vec<&ValidityStat> {
        self.designs.iter().filter(|d| !d.valid).collect()
    }
    pub fn unrecognized_count(&self) -> usize {
        self.unrecognized.len()
    }
    pub fn total_artifacts(&self) -> usize {
        self.files_found()
            + self.decision_count()
            + self.roadmap_count()
            + self.prompt_count()
            + self.design_count()
    }
    pub fn is_empty(&self) -> bool {
        self.total_artifacts() == 0 && self.unrecognized_count() == 0
    }
    pub fn has_meaningful_content(&self) -> bool {
        self.valid_features() > 0
            || self.decision_count() > 0
            || self.valid_roadmaps() > 0
            || self.valid_prompts() > 0
            || self.valid_designs() > 0
    }
}

/// `_neg_name(a) > _neg_name(b)` ⇔ `a` sorts before `b` by code point
/// (element-wise `-ord`). On a shared prefix Python tuple comparison makes
/// the SHORTER tuple smaller — so between "Feature" and "Feature With
/// Broken Ref" the LONGER name has the greater `_neg_name` and wins the
/// `max()` tie.
fn neg_name_gt(a: &str, b: &str) -> bool {
    let mut ai = a.chars();
    let mut bi = b.chars();
    loop {
        match (ai.next(), bi.next()) {
            (Some(ca), Some(cb)) => {
                if ca != cb {
                    // -ord(ca) > -ord(cb)  <=>  ca < cb
                    return (ca as u32) < (cb as u32);
                }
            }
            // Prefix equal so far: Python compares the (-ord, ...) tuples,
            // and a tuple that is a strict prefix of the other is SMALLER —
            // so `a` is greater exactly when it is LONGER.
            (None, Some(_)) => return false,
            (Some(_), None) => return true,
            (None, None) => return false,
        }
    }
}

/// `_bucket(decisions, attr, metadata_key)`: schema order first, then any
/// out-of-vocabulary values in sorted (code-point) order.
fn bucket<T>(
    items: &[T],
    get: impl Fn(&T) -> Option<&str>,
    metadata_key: &str,
) -> Vec<(String, usize)> {
    let spec = spec_for("decision");
    let order: &[String] = spec
        .and_then(|s| s.metadata.iter().find(|(k, _)| k == metadata_key))
        .map(|(_, v)| v.as_slice())
        .unwrap_or(&[]);
    // Count (insertion order = first-seen), like a Python dict.
    let mut counts: Vec<(String, usize)> = Vec::new();
    for item in items {
        if let Some(value) = get(item) {
            if value.is_empty() {
                continue;
            }
            match counts.iter_mut().find(|(k, _)| k == value) {
                Some((_, c)) => *c += 1,
                None => counts.push((value.to_string(), 1)),
            }
        }
    }
    let mut ordered: Vec<(String, usize)> = Vec::new();
    for v in order {
        if let Some((_, c)) = counts.iter().find(|(k, _)| k == v) {
            ordered.push((v.clone(), *c));
        }
    }
    // Remaining values, sorted by code point.
    let mut remaining: Vec<&(String, usize)> = counts
        .iter()
        .filter(|(k, _)| !ordered.iter().any(|(ok, _)| ok == k))
        .collect();
    remaining.sort_by(|a, b| a.0.cmp(&b.0));
    for (k, c) in remaining {
        ordered.push((k.clone(), *c));
    }
    ordered
}

/// `Path(path).stem` — filename without its final suffix.
fn path_stem(path: &str) -> String {
    let name = path.rsplit('/').next().unwrap_or(path);
    match name.rfind('.') {
        // Python `.stem`: a leading-dot-only name has no suffix.
        Some(0) => name.to_string(),
        Some(i) => name[..i].to_string(),
        None => name.to_string(),
    }
}

/// `product.title or path.stem`.
fn artifact_name(artifact: &Artifact, path: &str) -> String {
    match &artifact.product.title {
        Some(t) if !t.is_empty() => t.clone(),
        _ => path_stem(path),
    }
}

/// `canonical_value(raw, allowed)` — `_first_line(raw)` matched against the
/// allowed values, casefolded.
fn canonical_value(raw: &str, allowed: &[String]) -> String {
    let candidate = first_nonempty_line(raw);
    let folded = py_casefold(candidate);
    for value in allowed {
        if py_casefold(value) == folded {
            return value.clone();
        }
    }
    candidate.to_string()
}

/// Error-severity issue codes (`_error_codes`); no ticketing provider,
/// no overrides (stats validates raw).
fn error_codes(artifact: &Artifact, artifact_type: &str) -> Vec<String> {
    validate(artifact, None, Some(artifact_type))
        .into_iter()
        .filter(|i| i.severity == "error")
        .map(|i| i.code)
        .collect()
}

/// `present_relationship_sections(product, spec)` (canonical space names in
/// `spec.optional` order).
fn present_relationship_sections(artifact: &Artifact, spec: &ArtifactSpec) -> Vec<String> {
    let mut present = Vec::new();
    for section in &spec.optional {
        if !RELATIONSHIP_SECTIONS.iter().any(|(name, _)| name == section) {
            continue;
        }
        if let Some(body) = artifact.section(section) {
            if !body.is_empty() && !crate::relationships::parse_references(body).is_empty() {
                present.push(section.clone());
            }
        }
    }
    present
}

/// `_attach_decision_metadata` → (status, category).
fn decision_metadata(
    artifact: &Artifact,
    spec: &ArtifactSpec,
) -> (Option<String>, Option<String>) {
    let mut status = None;
    let mut category = None;
    for (field_name, allowed) in &spec.metadata {
        if let Some(body) = artifact.section(field_name) {
            if !body.is_empty() {
                let value = canonical_value(body, allowed);
                match field_name.as_str() {
                    "status" => status = Some(value),
                    "category" => category = Some(value),
                    _ => {}
                }
            }
        }
    }
    (status, category)
}

/// `collect_stats(directory)`.
pub fn collect_stats(directory: &str) -> PortfolioStats {
    let mut stats = PortfolioStats {
        directory: directory.to_string(),
        features: Vec::new(),
        decisions: Vec::new(),
        roadmaps: Vec::new(),
        prompts: Vec::new(),
        designs: Vec::new(),
        unrecognized: Vec::new(),
        relationship_counts: Vec::new(),
    };
    // Presence counts accumulated by canonical space section (first-seen order),
    // re-ordered canonically at the end.
    let mut rel_counts: Vec<(String, usize)> = Vec::new();

    for item in corpus_items(directory, true) {
        let artifact = &item.artifact;
        let path = &item.path;
        let name = artifact_name(artifact, path);
        let classification = classify(artifact);
        let type_name = classification.artifact_type.as_str();
        let spec = spec_for(type_name);

        if let Some(spec) = spec {
            for section in present_relationship_sections(artifact, spec) {
                match rel_counts.iter_mut().find(|(k, _)| *k == section) {
                    Some((_, c)) => *c += 1,
                    None => rel_counts.push((section, 1)),
                }
            }
        }

        match type_name {
            "decision" => {
                let (status, category) =
                    decision_metadata(artifact, spec.expect("decision spec"));
                stats.decisions.push(DecisionStat {
                    path: path.clone(),
                    name,
                    status,
                    category,
                });
            }
            "roadmap" => {
                let codes = error_codes(artifact, type_name);
                stats.roadmaps.push(ValidityStat {
                    path: path.clone(),
                    name,
                    valid: codes.is_empty(),
                    error_codes: codes,
                });
            }
            "prompt" => {
                let codes = error_codes(artifact, type_name);
                stats.prompts.push(ValidityStat {
                    path: path.clone(),
                    name,
                    valid: codes.is_empty(),
                    error_codes: codes,
                });
            }
            "design" => {
                let codes = error_codes(artifact, type_name);
                stats.designs.push(ValidityStat {
                    path: path.clone(),
                    name,
                    valid: codes.is_empty(),
                    error_codes: codes,
                });
            }
            "unknown" => {
                stats.unrecognized.push(UnrecognizedStat {
                    path: path.clone(),
                    name,
                    confidence: classification.confidence,
                });
            }
            _ => {
                let codes = error_codes(artifact, type_name);
                stats.features.push(FeatureStat {
                    path: path.clone(),
                    name,
                    valid: codes.is_empty(),
                    error_codes: codes,
                    requirements: artifact.product.requirements.len(),
                    success_metrics: artifact.product.success_metrics.len(),
                    risks: artifact.product.risks.len(),
                });
            }
        }
    }

    // Canonical relationship-count order.
    for (space_name, _) in RELATIONSHIP_SECTIONS.iter() {
        if let Some((_, c)) = rel_counts.iter().find(|(k, _)| k == space_name) {
            stats.relationship_counts.push((space_name.to_string(), *c));
        }
    }
    stats
}

#[cfg(test)]
mod tests {
    use super::neg_name_gt;

    /// Python compares `tuple(-ord(c) ...)` keys, where a strict-prefix
    /// tuple is SMALLER — so between tied features the longer
    /// prefix-sharing name wins `max()`.
    #[test]
    fn neg_name_prefix_tie_prefers_longer() {
        assert!(neg_name_gt("Feature With Broken Ref", "Feature"));
        assert!(!neg_name_gt("Feature", "Feature With Broken Ref"));
        // plain code-point ordering still applies on the first difference
        assert!(neg_name_gt("Alpha", "Beta"));
        assert!(!neg_name_gt("Beta", "Alpha"));
        assert!(!neg_name_gt("Same", "Same"));
    }
}
