//! Repository index — `decided index` (services/index.py, INDEX-PLAN B1).
//!
//! One walk, one parse per file, entries in sorted-path order. Identity-only
//! JSON contract (id/type/title/path/aliases); the command never consumes or
//! writes the derived cache (spec/index-contracts.json `index-command`).

use crate::classify::classify;
use crate::identity::{artifact_identifier, artifact_identifiers};
use crate::relationships::corpus_items;

/// One row in the repository manifest: structural identity only.
pub struct IndexEntry {
    pub id: String,
    pub artifact_type: String,
    pub title: Option<String>,
    pub path: String,
    pub aliases: Vec<String>,
}

/// Deterministic inventory of every artifact in a repository.
pub struct RepositoryIndex {
    pub directory: String,
    pub recursive: bool,
    pub artifacts: Vec<IndexEntry>,
}

pub fn build_repository_index(directory: &str, recursive: bool) -> RepositoryIndex {
    let items = corpus_items(directory, recursive);
    let artifacts = items
        .iter()
        .map(|it| IndexEntry {
            id: artifact_identifier(&it.artifact, it.spec, &it.path),
            artifact_type: classify(&it.artifact).artifact_type,
            title: it.artifact.product.title.clone(),
            path: it.path.clone(),
            aliases: artifact_identifiers(&it.artifact, it.spec, &it.path),
        })
        .collect();
    RepositoryIndex {
        directory: directory.to_string(),
        recursive,
        artifacts,
    }
}
