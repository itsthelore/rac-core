//! Git-derived recency and staleness — a port of the git touchpoint in
//! `src/rac/services/recency.py`, per PORT-CONTRACT.d/08 §4.
//!
//! Recency is *derived* from `git log`, never stored (ADR-045). This module
//! shells out to the real `git` binary with the exact argv the oracle uses and
//! reproduces its degrade-to-`None` posture: outside a repo, with no git
//! binary, or for an untracked file, every value is `None` — no error crosses
//! the boundary.
//!
//! Landmines (PORT-CONTRACT.d/08 §4.2–4.3):
//! - `git log --format=%cI` renders the **committer's stored timezone offset**
//!   and ignores `TZ`. `last_committed` is kept **verbatim** (offset preserved,
//!   never normalized to UTC).
//! - `age_days = (reference - last_committed).days` uses Python
//!   `timedelta.days`, which **floors toward negative infinity** (a future
//!   commit yields a negative age). This is whole-day truncation, not rounding.
//! - `stale = age_days > threshold_days` — strictly greater-than, so exactly at
//!   the threshold is **not** stale.
//! - Unknown date -> `Staleness { None, None, None }`.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use rayon::prelude::*;

/// Path-count at or above which the batch joins prefer one whole-history
/// `git log` pass over per-path spawns (COUNCIL-REVIEW B1 step 2). Below it a
/// narrow query keeps the per-path fan-out, which is already fast and avoids
/// walking a large history for a handful of paths. Perf-only — both paths
/// produce byte-identical output — so the exact value is not a contract.
const RECENCY_BATCH_MIN_PATHS: usize = 16;

/// The default "stale after" window (`DEFAULT_STALE_AFTER_DAYS`).
pub const DEFAULT_STALE_AFTER_DAYS: i64 = 180;

/// Run `git <args>` with the given working directory. Returns the raw stdout
/// on exit code 0, or `None` for a non-zero exit or a missing binary
/// (`FileNotFoundError` in the oracle).
fn run_git(args: &[&str], cwd: &Path) -> Option<String> {
    let output = Command::new("git").args(args).current_dir(cwd).output().ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&output.stdout).into_owned())
}

/// `run_git` with Python `text=True` universal-newline decoding (`\r\n` and
/// lone `\r` → `\n`). The recency callers in this module only trim `%cI`
/// stamps and the toplevel path, so they stay on the raw form; the rac-mcp
/// provenance surface parses `git show` file content, where the
/// normalization is load-bearing.
pub fn run_git_text(args: &[&str], cwd: &Path) -> Option<String> {
    run_git(args, cwd).map(|t| t.replace("\r\n", "\n").replace('\r', "\n"))
}

/// The work-tree root containing `directory`, or `None` if it is not a repo /
/// git is unavailable. Mirrors `git rev-parse --show-toplevel`.
pub fn repository_root(directory: &Path) -> Option<PathBuf> {
    let out = run_git(&["rev-parse", "--show-toplevel"], directory)?;
    let root = out.trim();
    if root.is_empty() {
        None
    } else {
        Some(PathBuf::from(root))
    }
}

/// `path` made relative to an already-canonicalized `canonical_root`. Split out
/// of [`pathspec`] so a batch join canonicalizes the (shared) root once instead
/// of per path — the root's `canonicalize()` is deterministic, so the resulting
/// spec is identical either way.
fn pathspec_in(canonical_root: &Path, path: &Path) -> String {
    let abspath = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    match abspath.strip_prefix(canonical_root) {
        Ok(rel) => rel.to_string_lossy().into_owned(),
        Err(_) => abspath.to_string_lossy().into_owned(),
    }
}

/// `path` made relative to `repo_root` (via `canonicalize`, like Python's
/// `Path.resolve()`); if it lies outside the work tree, the absolute path is
/// passed through unchanged.
pub fn pathspec(repo_root: &Path, path: &Path) -> String {
    let root = repo_root.canonicalize().unwrap_or_else(|_| repo_root.to_path_buf());
    pathspec_in(&root, path)
}

/// `git log -1 --format=%cI` for `path` with a pre-canonicalized root — the
/// per-path spawn the batch joins fan out in parallel.
fn last_committed_in(repo_root: &Path, canonical_root: &Path, path: &Path) -> Option<String> {
    let spec = pathspec_in(canonical_root, path);
    let out = run_git(&["log", "-1", "--format=%cI", "--", &spec], repo_root)?;
    let stamp = out.trim();
    if stamp.is_empty() {
        None
    } else {
        Some(stamp.to_string())
    }
}

/// `git log --reverse --format=%cI` for `path` with a pre-canonicalized root.
fn first_committed_in(repo_root: &Path, canonical_root: &Path, path: &Path) -> Option<String> {
    let spec = pathspec_in(canonical_root, path);
    let out = run_git(&["log", "--reverse", "--format=%cI", "--", &spec], repo_root)?;
    out.lines()
        .map(str::trim)
        .find(|l| !l.is_empty())
        .map(str::to_string)
}

/// The most recent commit time for `path` as the verbatim `%cI` string
/// (committer offset preserved), or `None` when the file is untracked /
/// uncommitted / outside a repo. Mirrors `git log -1 --format=%cI -- <path>`.
pub fn last_committed(repo_root: &Path, path: &Path) -> Option<String> {
    let canonical = repo_root.canonicalize().unwrap_or_else(|_| repo_root.to_path_buf());
    last_committed_in(repo_root, &canonical, path)
}

/// The earliest commit time for `path` as the verbatim `%cI` string of the
/// first non-blank line (committer offset preserved), or `None` when the
/// file is untracked / uncommitted / outside a repo. Mirrors
/// `git log --reverse --format=%cI -- <path>` (oldest first, first line is
/// the creation commit) — used by the OKF export's `created` field.
pub fn first_committed(repo_root: &Path, path: &Path) -> Option<String> {
    let canonical = repo_root.canonicalize().unwrap_or_else(|_| repo_root.to_path_buf());
    first_committed_in(repo_root, &canonical, path)
}

/// Whole-repo `path -> (last_committed, first_committed)` maps built from a
/// single `git log --name-only` pass. Keys are repo-root-relative paths as git
/// emits them; a path absent from a map has no committed history.
struct BatchedRecency {
    /// First occurrence in the newest-first walk = `git log -1 -- path`.
    last: HashMap<String, String>,
    /// Last occurrence (oldest) in the newest-first walk =
    /// `git log --reverse -- path | head -1`. Empty unless creation is wanted.
    first: HashMap<String, String>,
}

/// `true` iff the repo at `repo_root` contains a merge commit reachable from
/// HEAD; `None` when HEAD is unresolvable (empty repo / no git). `git rev-list`
/// short-circuits at the first merge, so this is cheap.
fn history_has_merge(repo_root: &Path) -> Option<bool> {
    let out = run_git(&["rev-list", "--merges", "--max-count=1", "HEAD"], repo_root)?;
    Some(!out.trim().is_empty())
}

/// Build the batched recency maps for `repo_root`, or `None` to signal that the
/// caller must fall back to the per-path join.
///
/// Safe **only on a linear history**: with no merge commit, the newest-first
/// first-occurrence of a path equals `git log -1 -- path` and its oldest
/// occurrence equals `git log --reverse -- path | head -1`, for every path —
/// no history-simplification divergence is possible (proven byte-identical to
/// the per-path oracle over the live corpus and every tracked file; see
/// `rust/tools` differential). A merge commit could carry an evil-merge whose
/// per-path simplification disagrees with the whole-history walk, so any merge
/// returns `None` and per-path is used instead.
fn batched_recency(repo_root: &Path, with_creation: bool) -> Option<BatchedRecency> {
    if history_has_merge(repo_root)? {
        return None;
    }
    // `\u{1}` marks a commit's `%cI` record; `-z` NUL-separates records and file
    // names (so no path quoting); `core.quotePath=false` keeps non-ASCII raw.
    let out = run_git(
        &[
            "-c",
            "core.quotePath=false",
            "log",
            "-z",
            "--format=\u{1}%cI",
            "--name-only",
        ],
        repo_root,
    )?;
    let mut last: HashMap<String, String> = HashMap::new();
    let mut first: HashMap<String, String> = HashMap::new();
    let mut cur: Option<String> = None;
    for tok in out.split('\0') {
        if let Some(date) = tok.strip_prefix('\u{1}') {
            cur = Some(date.trim().to_string());
        } else if let Some(date) = &cur {
            // The first file after a commit carries a leading '\n' from
            // `--name-only`'s blank separator line; later files do not.
            let path = tok.trim_start_matches('\n');
            if !path.is_empty() {
                last.entry(path.to_string()).or_insert_with(|| date.clone());
                if with_creation {
                    first.insert(path.to_string(), date.clone());
                }
            }
        }
    }
    Some(BatchedRecency { last, first })
}

/// Last-committed time for each of `paths` (the raw recency primitive). Every
/// path maps to `None` when `directory` is not a repo. Order preserved.
///
/// On a linear-history repo with enough paths to amortize it, one whole-history
/// `git log` pass serves the whole join (COUNCIL-REVIEW B1 step 2); otherwise
/// the per-path `git log` spawns run in parallel (step 1). ADR-045 recency is
/// *derived* and each spawn is independent with deterministic stdout, so every
/// path — batched or per-path — is byte-identical to the serial oracle.
pub fn last_committed_for_paths(directory: &Path, paths: &[PathBuf]) -> Vec<(PathBuf, Option<String>)> {
    match repository_root(directory) {
        None => paths.iter().map(|p| (p.clone(), None)).collect(),
        Some(root) => {
            let canonical = root.canonicalize().unwrap_or_else(|_| root.clone());
            if paths.len() >= RECENCY_BATCH_MIN_PATHS {
                if let Some(b) = batched_recency(&root, false) {
                    return paths
                        .iter()
                        .map(|p| (p.clone(), b.last.get(&pathspec_in(&canonical, p)).cloned()))
                        .collect();
                }
            }
            paths
                .par_iter()
                .map(|p| (p.clone(), last_committed_in(&root, &canonical, p)))
                .collect()
        }
    }
}

/// `(path, last_committed, first_committed)` for each of `paths`;
/// `first_committed` is `None` unless `with_creation`. Order preserved. Uses
/// the same batched-vs-parallel choice as [`last_committed_for_paths`]; serves
/// the OKF export's created/updated join.
pub fn recency_pairs_for_paths(
    directory: &Path,
    paths: &[PathBuf],
    with_creation: bool,
) -> Vec<(PathBuf, Option<String>, Option<String>)> {
    match repository_root(directory) {
        None => paths.iter().map(|p| (p.clone(), None, None)).collect(),
        Some(root) => {
            let canonical = root.canonicalize().unwrap_or_else(|_| root.clone());
            if paths.len() >= RECENCY_BATCH_MIN_PATHS {
                if let Some(b) = batched_recency(&root, with_creation) {
                    return paths
                        .iter()
                        .map(|p| {
                            let spec = pathspec_in(&canonical, p);
                            let last = b.last.get(&spec).cloned();
                            let first = if with_creation { b.first.get(&spec).cloned() } else { None };
                            (p.clone(), last, first)
                        })
                        .collect();
                }
            }
            paths
                .par_iter()
                .map(|p| {
                    let last = last_committed_in(&root, &canonical, p);
                    let first = if with_creation {
                        first_committed_in(&root, &canonical, p)
                    } else {
                        None
                    };
                    (p.clone(), last, first)
                })
                .collect()
        }
    }
}

/// One artifact's freshness: its verbatim last-committed date and the derived
/// indicators. All-`None` when the date is unknown. Mirrors `Staleness`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Staleness {
    /// The verbatim `%cI` string, or `None`.
    pub last_committed: Option<String>,
    /// Whole days between `reference` and `last_committed`, floored toward
    /// negative infinity (Python `timedelta.days`).
    pub age_days: Option<i64>,
    /// `age_days > threshold_days` (strictly greater; boundary is not stale).
    pub stale: Option<bool>,
}

impl Staleness {
    /// The unknown-date result: `{None, None, None}`.
    pub fn unknown() -> Self {
        Staleness {
            last_committed: None,
            age_days: None,
            stale: None,
        }
    }
}

/// Staleness of one last-committed date against `threshold_days`, evaluated at
/// `reference_epoch_secs` (Unix seconds, UTC). An unknown / unparseable date
/// yields the all-`None` result.
///
/// `reference_epoch_secs` stands in for the oracle's `reference` datetime
/// (`datetime.now(UTC)` in production; injectable for determinism). Passing it
/// as an epoch keeps this function clock-free and portable.
pub fn staleness(
    last_committed: Option<&str>,
    threshold_days: i64,
    reference_epoch_secs: i64,
) -> Staleness {
    let stamp = match last_committed {
        None => return Staleness::unknown(),
        Some(s) => s,
    };
    let committed_epoch = match parse_iso8601_epoch(stamp) {
        Some(e) => e,
        None => return Staleness::unknown(),
    };
    // Python `timedelta.days` = floor(total_seconds / 86400) toward -inf.
    let delta = reference_epoch_secs - committed_epoch;
    let age_days = floor_div(delta, 86_400);
    Staleness {
        last_committed: Some(stamp.to_string()),
        age_days: Some(age_days),
        stale: Some(age_days > threshold_days),
    }
}

/// Floor division toward negative infinity (Rust `/` truncates toward zero).
fn floor_div(a: i64, b: i64) -> i64 {
    let q = a / b;
    let r = a % b;
    if (r != 0) && ((r < 0) != (b < 0)) {
        q - 1
    } else {
        q
    }
}

/// Python `datetime.fromisoformat(stamp).isoformat()` round trip of a git
/// `%cI` stamp: verbatim for the `±HH:MM` form git emits; a trailing `Z`
/// re-serializes as `+00:00`, a colonless `±HHMM` gains its colon, `±HH`
/// becomes `±HH:00`, and a space separator becomes `T`.
pub fn isoformat_roundtrip(stamp: &str) -> String {
    let mut s = stamp.to_string();
    if s.len() > 10 && s.as_bytes()[10] == b' ' {
        s.replace_range(10..11, "T");
    }
    if s.ends_with('Z') || s.ends_with('z') {
        s.truncate(s.len() - 1);
        s.push_str("+00:00");
        return s;
    }
    // Find the offset sign after the time part (beyond index 10 to skip the
    // date's hyphens).
    if let Some(pos) = s.rfind(['+', '-']) {
        if pos > 10 {
            let body = &s[pos + 1..];
            if body.len() == 4 && body.bytes().all(|b| b.is_ascii_digit()) {
                let fixed = format!("{}:{}", &body[..2], &body[2..]);
                s.replace_range(pos + 1.., &fixed);
            } else if body.len() == 2 && body.bytes().all(|b| b.is_ascii_digit()) {
                let fixed = format!("{body}:00");
                s.replace_range(pos + 1.., &fixed);
            }
        }
    }
    s
}

/// Parse a strict ISO-8601 timestamp with an explicit offset (`%cI` form:
/// `YYYY-MM-DDTHH:MM:SS[.ffffff](Z|±HH:MM|±HHMM)`) into Unix epoch seconds
/// (UTC). Fractional seconds are ignored for whole-day math (git `%cI` has
/// none). Returns `None` on any structural surprise (treated as "unknown",
/// matching the oracle's `fromisoformat` `ValueError` -> `None`).
pub fn parse_iso8601_epoch(s: &str) -> Option<i64> {
    let bytes = s.as_bytes();
    if bytes.len() < 19 {
        return None;
    }
    // Date: YYYY-MM-DD
    let year: i64 = s.get(0..4)?.parse().ok()?;
    if bytes[4] != b'-' {
        return None;
    }
    let month: i64 = s.get(5..7)?.parse().ok()?;
    if bytes[7] != b'-' {
        return None;
    }
    let day: i64 = s.get(8..10)?.parse().ok()?;
    // Separator: 'T' or ' '
    if bytes[10] != b'T' && bytes[10] != b' ' {
        return None;
    }
    // Time: HH:MM:SS
    let hour: i64 = s.get(11..13)?.parse().ok()?;
    if bytes[13] != b':' {
        return None;
    }
    let minute: i64 = s.get(14..16)?.parse().ok()?;
    if bytes[16] != b':' {
        return None;
    }
    let second: i64 = s.get(17..19)?.parse().ok()?;

    // Remainder: optional fractional seconds, then the offset.
    let mut rest = &s[19..];
    if let Some(stripped) = rest.strip_prefix('.') {
        // Skip fractional digits.
        let non_digit = stripped
            .char_indices()
            .find(|(_, c)| !c.is_ascii_digit())
            .map(|(i, _)| i)
            .unwrap_or(stripped.len());
        rest = &stripped[non_digit..];
    }

    let offset_secs = parse_offset(rest)?;

    let days = days_from_civil(year, month, day);
    let local_secs = days * 86_400 + hour * 3_600 + minute * 60 + second;
    // The stamp's civil time is UTC + offset, so UTC = local - offset.
    Some(local_secs - offset_secs)
}

/// Parse a trailing timezone offset (`Z`, `±HH:MM`, or `±HHMM`) to seconds.
fn parse_offset(rest: &str) -> Option<i64> {
    if rest == "Z" || rest == "z" {
        return Some(0);
    }
    let bytes = rest.as_bytes();
    if bytes.is_empty() {
        return None; // %cI always carries an explicit offset
    }
    let sign = match bytes[0] {
        b'+' => 1,
        b'-' => -1,
        _ => return None,
    };
    let body = &rest[1..];
    let (hh, mm) = if body.len() == 5 && body.as_bytes()[2] == b':' {
        (&body[0..2], &body[3..5]) // ±HH:MM
    } else if body.len() == 4 {
        (&body[0..2], &body[2..4]) // ±HHMM
    } else if body.len() == 2 {
        (&body[0..2], "00") // ±HH
    } else {
        return None;
    };
    let h: i64 = hh.parse().ok()?;
    let m: i64 = mm.parse().ok()?;
    Some(sign * (h * 3_600 + m * 60))
}

/// Days from the Unix epoch (1970-01-01) to the civil date `y-m-d`, via Howard
/// Hinnant's algorithm. Correct for the proleptic Gregorian calendar and any
/// year range git can emit.
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400; // [0, 399]
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1; // [0, 365]
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy; // [0, 146096]
    era * 146_097 + doe - 719_468
}
