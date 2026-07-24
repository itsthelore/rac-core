//! Git revision materialization (`decided.services.revisions`) — the only
//! git-consuming module of the watchkeeper path (ADR-043). A revision name
//! becomes a temporary directory holding the corpus subpath at that
//! revision, via `git archive --format=tar` (never mutates `.git`: no
//! worktree registration, no locks) piped through a minimal in-process tar
//! reader (no tar binary, no new dependencies).
//!
//! Contract mirrored from the oracle:
//! - `git rev-parse --show-toplevel` (cwd = the corpus directory) finds the
//!   work-tree root; failure -> `not a git repository: <directory>`; a
//!   missing git binary -> `git executable not found` (both exit 2 at the
//!   CLI as `decided: <msg>`).
//! - `git rev-parse --verify --quiet <rev>^{commit}` (cwd = repo root);
//!   nonzero -> `unknown revision: <rev>`.
//! - `git archive --format=tar <rev> -- <pathspec>` (cwd = repo root); a
//!   NONZERO exit is not an error — the subpath does not exist at that
//!   revision and an EMPTY corpus is materialized (the fresh-adoption
//!   "everything added" comparison).
//! - The temporary directory is prefixed `decided-watchkeeper-` and removed
//!   when the materialization guard drops. Its path never appears in any
//!   output surface (all reported paths are corpus-relative).

use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

/// The two usage-error surfaces of revision resolution; `message()` is the
/// text after the CLI's `decided: ` prefix.
#[derive(Debug)]
pub enum RevisionError {
    /// `NotAGitRepository` — not inside a git work tree, or no git binary.
    NotAGitRepository(String),
    /// `RevisionNotFound` — the name does not resolve to a commit.
    RevisionNotFound(String),
}

impl RevisionError {
    pub fn message(&self) -> &str {
        match self {
            RevisionError::NotAGitRepository(m) => m,
            RevisionError::RevisionNotFound(m) => m,
        }
    }
}

/// `_run_git(args, cwd)` — capture both streams, never check. Only a
/// missing binary maps to `NotAGitRepository("git executable not found")`,
/// like the oracle's `FileNotFoundError` arm.
fn run_git(args: &[&str], cwd: &Path) -> Result<Output, RevisionError> {
    Command::new("git")
        .args(args)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .output()
        .map_err(|_| {
            // FileNotFoundError -> "git executable not found"; the oracle
            // would crash on any other spawn failure — degrade to the same
            // user-facing class (PORT-CONTRACT decision 3).
            RevisionError::NotAGitRepository("git executable not found".to_string())
        })
}

/// `repository_root(directory)` — the work-tree root containing `directory`.
pub fn repository_root(directory: &str) -> Result<String, RevisionError> {
    let out = run_git(&["rev-parse", "--show-toplevel"], Path::new(directory))?;
    if !out.status.success() {
        return Err(RevisionError::NotAGitRepository(format!(
            "not a git repository: {directory}"
        )));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

/// One materialized revision: the guard owns the temporary directory and
/// removes it (best effort) on drop, like the oracle's
/// `tempfile.TemporaryDirectory` context.
pub struct MaterializedRevision {
    root: PathBuf,
    /// The corpus directory inside the temp tree (`tmp/<subpath>`).
    pub corpus: PathBuf,
}

impl Drop for MaterializedRevision {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.root);
    }
}

/// A fresh `decided-watchkeeper-` temp directory under the platform temp root
/// (std honors TMPDIR like `tempfile` does).
fn make_temp_dir() -> io::Result<PathBuf> {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let base = std::env::temp_dir();
    let pid = std::process::id();
    loop {
        let n = COUNTER.fetch_add(1, Ordering::Relaxed);
        let candidate = base.join(format!("decided-watchkeeper-{pid}-{n}"));
        match std::fs::create_dir(&candidate) {
            Ok(()) => return Ok(candidate),
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e),
        }
    }
}

/// `materialized_revision(repo_root, rev, subpath)` — verify the commit,
/// archive the subpath, extract into a temp tree, and yield `tmp/<subpath>`
/// (created empty when the archive had nothing to say).
pub fn materialize_revision(
    repo_root: &str,
    rev: &str,
    subpath: &str,
) -> Result<MaterializedRevision, RevisionError> {
    let root = Path::new(repo_root);
    let verify = run_git(
        &["rev-parse", "--verify", "--quiet", &format!("{rev}^{{commit}}")],
        root,
    )?;
    if !verify.status.success() {
        return Err(RevisionError::RevisionNotFound(format!(
            "unknown revision: {rev}"
        )));
    }

    let pathspec = if subpath.is_empty() || subpath == "." {
        "."
    } else {
        subpath
    };
    let archive = run_git(&["archive", "--format=tar", rev, "--", pathspec], root)?;

    let tmp = make_temp_dir().map_err(|e| {
        // No oracle-comparable surface exists for a failing temp root; the
        // closest degrade is the not-a-repository class (never hit by the
        // parity fixtures).
        RevisionError::NotAGitRepository(format!("not a git repository: {e}"))
    })?;
    let guard_root = tmp.clone();
    if archive.status.success() {
        extract_tar(&archive.stdout, &tmp);
    }
    // A nonzero archive exit means the subpath does not exist at `rev`:
    // materialize an empty corpus rather than failing the comparison.
    let corpus = if pathspec == "." {
        tmp
    } else {
        guard_root.join(subpath)
    };
    let _ = std::fs::create_dir_all(&corpus);
    Ok(MaterializedRevision {
        root: guard_root,
        corpus,
    })
}

// ---------------------------------------------------------------------------
// Minimal tar reader — enough for `git archive --format=tar` output: ustar
// headers with the split name/prefix fields, the pax global header git
// always emits ('g', skipped), pax extended headers ('x', `path=` override),
// GNU longname ('L'), directories ('5'), regular files ('0'/NUL), and
// symlinks ('2', created best-effort). Entries with absolute or `..`
// components are skipped defensively (tarfile's `filter="data"` would raise
// there; git archive never produces them).
// ---------------------------------------------------------------------------

fn octal_field(bytes: &[u8]) -> u64 {
    let mut out: u64 = 0;
    for &b in bytes {
        if matches!(b, b'0'..=b'7') {
            out = out * 8 + u64::from(b - b'0');
        }
    }
    out
}

fn cstr_field(bytes: &[u8]) -> String {
    let end = bytes.iter().position(|&b| b == 0).unwrap_or(bytes.len());
    String::from_utf8_lossy(&bytes[..end]).into_owned()
}

/// Parse a pax extended-header payload (`<len> <key>=<value>\n` records)
/// and return the `path` override, if any.
fn pax_path(data: &[u8]) -> Option<String> {
    let mut i = 0;
    while i < data.len() {
        // "<decimal-length> <key>=<value>\n" — length covers the whole record.
        let space = data[i..].iter().position(|&b| b == b' ')?;
        let len: usize = std::str::from_utf8(&data[i..i + space])
            .ok()?
            .parse()
            .ok()?;
        if len == 0 || i + len > data.len() {
            return None;
        }
        let record = &data[i + space + 1..i + len];
        if let Some(eq) = record.iter().position(|&b| b == b'=') {
            let key = &record[..eq];
            if key == b"path" {
                let mut value = &record[eq + 1..];
                if value.last() == Some(&b'\n') {
                    value = &value[..value.len() - 1];
                }
                return Some(String::from_utf8_lossy(value).into_owned());
            }
        }
        i += len;
    }
    None
}

/// True when every component of the '/'-separated relative path is safe to
/// join under the extraction root.
fn safe_relative(name: &str) -> bool {
    !name.starts_with('/')
        && !name
            .split('/')
            .any(|c| c == ".." || c.chars().any(|ch| ch == '\\'))
}

/// Extract a tar stream under `target`. Unknown/unsafe entries are skipped;
/// extraction is best-effort (the oracle's crash surfaces here are out of
/// the refereed contract — git-produced archives are always well-formed).
fn extract_tar(data: &[u8], target: &Path) {
    let mut offset = 0usize;
    let mut pending_path: Option<String> = None;
    while offset + 512 <= data.len() {
        let header = &data[offset..offset + 512];
        offset += 512;
        if header.iter().all(|&b| b == 0) {
            break; // end-of-archive zero block
        }
        let size = octal_field(&header[124..136]) as usize;
        let padded = size.div_ceil(512) * 512;
        if offset + size > data.len() {
            break; // truncated
        }
        let body = &data[offset..offset + size];
        let typeflag = header[156];
        match typeflag {
            b'g' => {} // pax global header (git's comment=<sha>) — skip
            b'x' => {
                if let Some(p) = pax_path(body) {
                    pending_path = Some(p);
                }
            }
            b'L' => {
                // GNU longname: NUL-terminated name for the next entry.
                pending_path = Some(cstr_field(body));
            }
            _ => {
                let mut name = match pending_path.take() {
                    Some(p) => p,
                    None => {
                        let base = cstr_field(&header[0..100]);
                        let prefix = cstr_field(&header[345..500]);
                        if prefix.is_empty() {
                            base
                        } else {
                            format!("{prefix}/{base}")
                        }
                    }
                };
                let is_dir_name = name.ends_with('/');
                while name.ends_with('/') {
                    name.pop();
                }
                if !name.is_empty() && safe_relative(&name) {
                    let dest = target.join(&name);
                    match typeflag {
                        b'5' => {
                            let _ = std::fs::create_dir_all(&dest);
                        }
                        b'0' | 0 | b'7' if !is_dir_name => {
                            if let Some(parent) = dest.parent() {
                                let _ = std::fs::create_dir_all(parent);
                            }
                            let _ = std::fs::write(&dest, body);
                        }
                        b'2' => {
                            if let Some(parent) = dest.parent() {
                                let _ = std::fs::create_dir_all(parent);
                            }
                            #[cfg(unix)]
                            {
                                let link = cstr_field(&header[157..257]);
                                let _ = std::os::unix::fs::symlink(&link, &dest);
                            }
                        }
                        _ => {} // hardlinks/devices: never in git archives
                    }
                }
            }
        }
        offset += padded;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn octal_parses_padded_fields() {
        assert_eq!(octal_field(b"0000644\0"), 0o644);
        assert_eq!(octal_field(b"00000000173 "), 0o173);
    }

    #[test]
    fn pax_path_record() {
        let payload = b"33 path=decisions/some-long-name\n";
        assert_eq!(pax_path(payload).as_deref(), Some("decisions/some-long-name"));
    }

    #[test]
    fn rejects_escaping_names() {
        assert!(!safe_relative("/abs"));
        assert!(!safe_relative("a/../b"));
        assert!(safe_relative("decisions/d1.md"));
    }
}
