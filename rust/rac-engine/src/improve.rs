//! Artifact improvement (`decided.services.improve`): deterministic,
//! schema-driven guidance. Advisory and read-only — reports missing
//! required/recommended sections with schema-defined guidance questions.

use crate::classify::{classify, missing_sections};
use crate::parse::Artifact;
use crate::spec::{spec_for, ArtifactSpec};

/// `supports_improve(spec)` — every expected section defines guidance.
/// (All five current specs pass, so the unsupported branch is dead in
/// practice; ported for fidelity.)
pub fn supports_improve(spec: &ArtifactSpec) -> bool {
    spec.expected()
        .iter()
        .all(|section| spec.guidance.iter().any(|(k, _)| k == section))
}

/// Typed improvement analysis (`ImprovementResult`). Section names are
/// stored normalized; the renderers format them.
pub struct ImprovementResult {
    /// Classified artifact type, or `"unknown"`.
    pub artifact_type: String,
    pub missing_required: Vec<String>,
    pub missing_recommended: Vec<String>,
    /// Schema guidance for the missing sections: `{section -> questions}`,
    /// required-first then recommended, only sections that HAVE guidance.
    pub guidance: Vec<(String, Vec<String>)>,
    /// Whether `improve` produces suggestions for this type.
    pub supported: bool,
}

/// `improve_product(product)` — analyze and return improvement guidance.
pub fn improve_product(artifact: &Artifact) -> ImprovementResult {
    let artifact_type = classify(artifact).artifact_type;
    let spec = spec_for(&artifact_type);
    let Some(spec) = spec.filter(|s| supports_improve(s)) else {
        // Unknown, or a known type whose schema lacks complete guidance.
        return ImprovementResult {
            artifact_type,
            missing_required: Vec::new(),
            missing_recommended: Vec::new(),
            guidance: Vec::new(),
            supported: false,
        };
    };
    let (missing_required, missing_recommended) = missing_sections(artifact, spec);
    let mut guidance: Vec<(String, Vec<String>)> = Vec::new();
    for s in missing_required.iter().chain(missing_recommended.iter()) {
        // `if spec.guidance.get(s)` — only truthy (non-empty) guidance lists.
        if let Some((_, g)) = spec.guidance.iter().find(|(k, _)| k == s) {
            if !g.is_empty() {
                guidance.push((s.clone(), g.clone()));
            }
        }
    }
    ImprovementResult {
        artifact_type,
        missing_required,
        missing_recommended,
        guidance,
        supported: true,
    }
}
