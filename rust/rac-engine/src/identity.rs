//! Artifact identity (`rac.core.identity`), per PORT-CONTRACT.d/04 §3.
//!
//! Precedence: frontmatter id -> `## ID` section -> `spec.id_field` (dead
//! today) -> filename-stem `^[A-Za-z]+-\d+` prefix -> whole stem. Pathlib
//! `stem` semantics and Unicode `\d` are replicated exactly.

use crate::parse::Artifact;
use crate::pycompat::{is_re_digit, py_casefold, py_is_space, py_splitlines, py_strip};
use crate::spec::ArtifactSpec;

/// Strip ONE leading well-formed Markdown list marker
/// (`^(?:[-*+]|\d+\.)\s+`, Unicode `\d`/`\s`) from `s`, or return it as-is.
pub fn strip_list_marker(s: &str) -> &str {
    let mut chars = s.char_indices();
    let Some((_, first)) = chars.next() else {
        return s;
    };
    let after_marker = if matches!(first, '-' | '*' | '+') {
        first.len_utf8()
    } else if is_re_digit(first) {
        // \d+ then a literal '.'
        let mut end = first.len_utf8();
        let mut rest = s[end..].char_indices();
        loop {
            match rest.next() {
                Some((_, c)) if is_re_digit(c) => end += c.len_utf8(),
                Some((_, '.')) => {
                    end += 1;
                    break;
                }
                _ => return s,
            }
        }
        end
    } else {
        return s;
    };
    // \s+ — at least one Python-whitespace char.
    let tail = &s[after_marker..];
    let trimmed = tail.trim_start_matches(py_is_space);
    if trimmed.len() == tail.len() {
        return s; // no whitespace after the marker -> no match
    }
    trimmed
}

/// identity's `_first_value(body)`: first non-empty stripped line, one
/// leading list marker stripped, stripped again.
pub fn first_value_list_stripped(body: Option<&str>) -> String {
    let Some(body) = body else {
        return String::new();
    };
    if body.is_empty() {
        return String::new();
    }
    for line in py_splitlines(body) {
        let stripped = py_strip(line);
        if !stripped.is_empty() {
            return py_strip(strip_list_marker(stripped)).to_string();
        }
    }
    String::new()
}

/// `Path(path).stem` — pathlib semantics: final component (trailing slashes
/// and `.` segments dropped), minus the last suffix, where a suffix exists
/// only when the final dot is neither at index 0 nor the last char.
pub fn path_stem(path: &str) -> String {
    let name = path
        .split('/')
        .rfind(|p| !p.is_empty() && *p != ".")
        .unwrap_or("");
    match name.rfind('.') {
        Some(i) if i > 0 && i < name.len() - 1 => name[..i].to_string(),
        _ => name.to_string(),
    }
}

/// `_ID_PREFIX_RE = ^[A-Za-z]+-\d+` (ASCII letters, Unicode digits) —
/// returns the matched prefix (`.group(0)`) or None.
pub fn id_prefix(stem: &str) -> Option<&str> {
    let bytes = stem.as_bytes();
    let mut i = 0;
    while i < bytes.len() && bytes[i].is_ascii_alphabetic() {
        i += 1;
    }
    if i == 0 || i >= bytes.len() || bytes[i] != b'-' {
        return None;
    }
    // \d+ — a contiguous, greedy digit run from digits_start.
    let digits_start = i + 1;
    let mut run_end = digits_start;
    for c in stem[digits_start..].chars() {
        if is_re_digit(c) {
            run_end += c.len_utf8();
        } else {
            break;
        }
    }
    if run_end == digits_start {
        None
    } else {
        Some(&stem[..run_end])
    }
}

/// `_legacy_identifier(product, spec)`: `## ID` first value, then
/// `spec.id_field` (no spec sets it — ported for fidelity).
fn legacy_identifier(artifact: &Artifact, spec: Option<&ArtifactSpec>) -> String {
    let explicit = first_value_list_stripped(artifact.section("id"));
    if !explicit.is_empty() {
        return explicit;
    }
    if let Some(spec) = spec {
        if let Some(field) = &spec.id_field {
            if !field.is_empty() {
                let declared = first_value_list_stripped(artifact.section(field));
                if !declared.is_empty() {
                    return declared;
                }
            }
        }
    }
    String::new()
}

fn metadata_id(artifact: &Artifact) -> Option<&str> {
    artifact
        .metadata
        .as_ref()
        .and_then(|m| m.id.as_deref())
        .filter(|s| !s.is_empty())
}

/// `artifact_identifier(product, spec, path)`.
pub fn artifact_identifier(artifact: &Artifact, spec: Option<&ArtifactSpec>, path: &str) -> String {
    if let Some(id) = metadata_id(artifact) {
        return id.to_string();
    }
    let legacy = legacy_identifier(artifact, spec);
    if !legacy.is_empty() {
        return legacy;
    }
    let stem = path_stem(path);
    match id_prefix(&stem) {
        Some(prefix) => prefix.to_string(),
        None => stem,
    }
}

/// `artifact_identifiers(product, spec, path)`: canonical first, then legacy
/// aliases, de-duplicated case-insensitively (casefold).
pub fn artifact_identifiers(
    artifact: &Artifact,
    spec: Option<&ArtifactSpec>,
    path: &str,
) -> Vec<String> {
    let mut ids: Vec<String> = Vec::new();
    let mut folded: Vec<String> = Vec::new();
    let add = |value: String, ids: &mut Vec<String>, folded: &mut Vec<String>| {
        if value.is_empty() {
            return;
        }
        let f = py_casefold(&value);
        if folded.contains(&f) {
            return;
        }
        folded.push(f);
        ids.push(value);
    };
    if let Some(id) = metadata_id(artifact) {
        add(id.to_string(), &mut ids, &mut folded);
    }
    add(legacy_identifier(artifact, spec), &mut ids, &mut folded);
    let stem = path_stem(path);
    if let Some(prefix) = id_prefix(&stem) {
        add(prefix.to_string(), &mut ids, &mut folded);
    }
    add(stem, &mut ids, &mut folded);
    ids
}

/// `identity_conflict(product, spec)` -> `(frontmatter_id, legacy_id)`.
pub fn identity_conflict(
    artifact: &Artifact,
    spec: Option<&ArtifactSpec>,
) -> Option<(String, String)> {
    let fm_id = metadata_id(artifact)?;
    let legacy = legacy_identifier(artifact, spec);
    if legacy.is_empty() {
        return None;
    }
    // Compared as `legacy.strip().upper() == metadata.id` (upper, not
    // casefold — the asymmetry is deliberate, PORT-CONTRACT.d/04 §3.4).
    if py_strip(&legacy).to_uppercase() == fm_id {
        return None;
    }
    Some((fm_id.to_string(), legacy))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stem_semantics() {
        assert_eq!(path_stem("a.b.md"), "a.b");
        assert_eq!(path_stem("a."), "a.");
        assert_eq!(path_stem(".hidden"), ".hidden");
        assert_eq!(path_stem("a/b/"), "b");
        assert_eq!(path_stem("a..md"), "a.");
        assert_eq!(path_stem(".md"), ".md");
        assert_eq!(path_stem("tests/fixtures/valid/feature.md"), "feature");
    }

    #[test]
    fn prefix_matching() {
        assert_eq!(id_prefix("adr-004-parser-strategy"), Some("adr-004"));
        assert_eq!(id_prefix("adr-x"), None);
        assert_eq!(id_prefix("-004"), None);
        assert_eq!(id_prefix("adr004"), None);
    }

    #[test]
    fn list_marker_strip() {
        assert_eq!(strip_list_marker("- ADR-1"), "ADR-1");
        assert_eq!(strip_list_marker("12. x"), "x");
        assert_eq!(strip_list_marker("-x"), "-x");
        assert_eq!(strip_list_marker("+  y"), "y");
    }
}
