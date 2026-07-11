//! File -> parsed artifact: the oracle's `rac.core.markdown.parse` /
//! `parse_file` composition of the markdown body walk (`markdown.rs`) with
//! the frontmatter envelope (`frontmatter.rs`), per PORT-CONTRACT.d/04 §0
//! and PORT-CONTRACT.d/09 §1.7.
//!
//! The markdown module owns the body surfaces (sections, requirements,
//! titles, parse budget issues) and the raw read path; this module attaches
//! `product.metadata` / `product.metadata_issues` exactly as the oracle's
//! `parse` does:
//!
//! ```python
//! split = split_frontmatter(text)
//! if split.raw is not None:
//!     metadata, metadata_issues = parse_frontmatter(split.raw)
//! elif split.unterminated:
//!     metadata_issues = [malformed-frontmatter "never closed"]
//! ```
//!
//! The unterminated case is already emitted by `markdown::parse`; the
//! `raw is not None` case is completed here.

use crate::frontmatter::{parse_frontmatter, ArtifactMetadata};
use crate::markdown::{self, Product};

/// One validation/parse finding, unified across the frontmatter, markdown,
/// and validation subsystems. Field order mirrors the Python `Issue`
/// dataclass (`severity, code, message, line`) — `asdict` emission order.
#[derive(Debug, Clone, PartialEq)]
pub struct Issue {
    pub severity: &'static str,
    pub code: String,
    pub message: String,
    pub line: Option<i64>,
}

impl Issue {
    pub fn new(severity: &'static str, code: &str, message: String, line: Option<i64>) -> Issue {
        Issue {
            severity,
            code: code.to_string(),
            message,
            line,
        }
    }
}

fn from_markdown(i: &markdown::Issue) -> Issue {
    Issue {
        severity: i.severity,
        code: i.code.to_string(),
        message: i.message.clone(),
        line: i.line,
    }
}

fn from_frontmatter(i: crate::frontmatter::Issue) -> Issue {
    Issue {
        severity: i.severity,
        code: i.code,
        message: i.message,
        line: i.line,
    }
}

/// A parsed artifact: the markdown `Product` plus the frontmatter metadata
/// the oracle's `Product.metadata` carries.
#[derive(Debug, Clone)]
pub struct Artifact {
    pub product: Product,
    /// `product.metadata` — `None` for legacy (no-frontmatter) documents and
    /// for envelope-fatal frontmatter.
    pub metadata: Option<ArtifactMetadata>,
    /// `product.metadata_issues` in oracle order.
    pub metadata_issues: Vec<Issue>,
    /// `product.parse_issues` in oracle order.
    pub parse_issues: Vec<Issue>,
}

impl Artifact {
    /// `product.sections.get(key)` — the insertion-ordered section map.
    pub fn section(&self, key: &str) -> Option<&str> {
        self.product
            .sections
            .iter()
            .find(|(h, _)| h == key)
            .map(|(_, b)| b.as_str())
    }

    /// `key in product.sections`.
    pub fn has_section(&self, key: &str) -> bool {
        self.product.sections.iter().any(|(h, _)| h == key)
    }
}

fn attach_metadata(product: Product) -> Artifact {
    // markdown::parse populated metadata_issues only for the unterminated
    // (`raw is None`) case; complete the `raw is not None` arm here.
    let mut metadata_issues: Vec<Issue> =
        product.metadata_issues.iter().map(from_markdown).collect();
    let mut metadata = None;
    if let Some(raw) = &product.frontmatter_raw {
        let (meta, issues) = parse_frontmatter(raw);
        metadata = meta;
        metadata_issues.extend(issues.into_iter().map(from_frontmatter));
    }
    let parse_issues = product.parse_issues.iter().map(from_markdown).collect();
    Artifact {
        product,
        metadata,
        metadata_issues,
        parse_issues,
    }
}

/// `rac.core.markdown.parse(text, source_path)` with metadata attached.
pub fn parse_text(text: &str, source_path: &str) -> Artifact {
    attach_metadata(markdown::parse(text, source_path))
}

/// `rac.core.markdown.parse_file(path)` with metadata attached.
pub fn parse_file(path: &str) -> Artifact {
    attach_metadata(markdown::parse_file(path))
}
