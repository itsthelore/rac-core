//! parity-harness — the referee for the native-engine spike.
//!
//! Runs the same argv against two `rac` engine executables under an
//! identical, deterministic environment (pipes for stdio so `isatty` is
//! false on both sides, null stdin, neutralized cache/telemetry env) and
//! demands byte-identical stdout plus identical exit codes, after the
//! per-case declared normalizations (default: none — raw bytes).
//!
//! Exit code: 0 iff every selected case passes; 1 if any case fails;
//! 2 on harness usage/setup errors.
//!
//! Scoreboard: `<dir>/scoreboard.json` (machine) and `<dir>/scoreboard.md`
//! (human). Both are pure functions of the case outcomes — no timestamps,
//! no durations — so two runs over identical engine behavior produce
//! byte-identical scoreboards (the determinism proof the spike requires).

use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde::Deserialize;
use serde_json::{json, Value};

// ---------------------------------------------------------------------------
// Case model
// ---------------------------------------------------------------------------

/// One parity case from `parity-cases.json`.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    /// Unique case id; `--filter` matches on substrings of this.
    id: String,
    /// argv passed to both engines (executable path prepended by the harness).
    argv: Vec<String>,
    /// Working directory, relative to the repo root. Default: repo root.
    #[serde(default = "default_cwd")]
    cwd: String,
    /// Per-case environment overrides layered on the deterministic base env.
    #[serde(default)]
    env: BTreeMap<String, String>,
    /// The exit code both engines must produce. Recorded for every case so
    /// the harness referees the contract, not just A==B.
    expect_exit: i32,
    /// Documents that a nonzero exit is the expected outcome of this case.
    /// If false, a nonzero exit fails the case even when both engines agree.
    #[serde(default)]
    expect_nonzero_ok: bool,
    /// Named normalizations applied to BOTH sides' stdout before compare.
    /// Default none: comparison is raw bytes.
    #[serde(default)]
    normalize: Vec<String>,
}

fn default_cwd() -> String {
    ".".to_string()
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

struct Args {
    engine_a: PathBuf,
    engine_b: PathBuf,
    cases: PathBuf,
    scoreboard_dir: PathBuf,
    filter: Option<String>,
    repo_root: Option<PathBuf>,
}

fn parse_args() -> Result<Args, String> {
    let mut engine_a = None;
    let mut engine_b = None;
    let mut cases = None;
    let mut scoreboard_dir = None;
    let mut filter = None;
    let mut repo_root = None;

    let mut it = std::env::args().skip(1);
    while let Some(flag) = it.next() {
        let mut take = |name: &str| -> Result<String, String> {
            it.next().ok_or_else(|| format!("{name} requires a value"))
        };
        match flag.as_str() {
            "--engine-a" => engine_a = Some(PathBuf::from(take("--engine-a")?)),
            "--engine-b" => engine_b = Some(PathBuf::from(take("--engine-b")?)),
            "--cases" => cases = Some(PathBuf::from(take("--cases")?)),
            "--scoreboard-dir" => scoreboard_dir = Some(PathBuf::from(take("--scoreboard-dir")?)),
            "--filter" => filter = Some(take("--filter")?),
            "--repo-root" => repo_root = Some(PathBuf::from(take("--repo-root")?)),
            other => return Err(format!("unknown argument: {other}")),
        }
    }
    Ok(Args {
        engine_a: engine_a.ok_or("--engine-a is required")?,
        engine_b: engine_b.ok_or("--engine-b is required")?,
        cases: cases.ok_or("--cases is required")?,
        scoreboard_dir: scoreboard_dir.ok_or("--scoreboard-dir is required")?,
        filter,
        repo_root,
    })
}

// ---------------------------------------------------------------------------
// Normalizations
//
// Each normalization exists because a specific output field is derived from
// git state or the build, per PORT-CONTRACT.d/08 §1.3/§4 and PORT-CONTRACT.md
// cross-cutting decision 6. Cases whose output is a pure function of file
// bytes declare none and are compared raw.
// ---------------------------------------------------------------------------

/// "strip-recency-json" — `find --json` embeds a git-derived `recency`
/// object per match (`{last_committed, age_days, stale}`, ADR-045).
/// `age_days`/`stale` are wall-clock-relative (`datetime.now(UTC)`), so even
/// oracle-vs-oracle can diverge across a day boundary between the two runs.
/// Mirrors `tests/test_golden.py` `_FIND_JSON_CASES`: parse the JSON, remove
/// the `recency` member from every object (the golden pops it from each
/// match; recursive removal is the same set for this payload), re-serialize.
/// NOTE: re-serialization (2-space pretty, preserved key order, raw UTF-8)
/// is applied identically to both sides, so byte equality is preserved; it
/// does mask `ensure_ascii`-level divergence on these cases only — that is
/// still covered by the raw JSON cases.
fn strip_recency_json(stdout: &[u8]) -> Result<Vec<u8>, String> {
    let mut value = parse_json(stdout)?;
    fn walk(v: &mut Value) {
        match v {
            Value::Object(map) => {
                map.shift_remove("recency");
                for (_, child) in map.iter_mut() {
                    walk(child);
                }
            }
            Value::Array(items) => items.iter_mut().for_each(walk),
            _ => {}
        }
    }
    walk(&mut value);
    serialize_json(&value)
}

/// "strip-stale-human" — `find` human output appends a git/wall-clock-derived
/// ` ⚠ stale (Nd)` marker to stale matches (PORT-CONTRACT.d/08 §1.3,
/// `_STALE_MARKER_RE = r" ⚠ stale \(\d+d\)"`, leading space, ⚠ = U+26A0).
/// Byte-scan removal of exactly that pattern; everything else untouched.
fn strip_stale_human(stdout: &[u8]) -> Result<Vec<u8>, String> {
    const HEAD: &[u8] = " \u{26A0} stale (".as_bytes(); // " ⚠ stale ("
    let mut out = Vec::with_capacity(stdout.len());
    let mut i = 0;
    while i < stdout.len() {
        if stdout[i..].starts_with(HEAD) {
            let mut j = i + HEAD.len();
            let digits_start = j;
            while j < stdout.len() && stdout[j].is_ascii_digit() {
                j += 1;
            }
            if j > digits_start && stdout[j..].starts_with(b"d)") {
                i = j + 2; // drop the whole marker
                continue;
            }
        }
        out.push(stdout[i]);
        i += 1;
    }
    Ok(out)
}

/// "mask-version" — the rac version string is build-derived (setuptools-scm
/// git-describe on the oracle; `RAC_RS_VERSION` injection seam on the Rust
/// side, PORT-CONTRACT.md decision 6). It appears in exactly two payload
/// positions (PORT-CONTRACT.d/09 §3.7): `export --json` `corpus.rac_version`
/// and SARIF `tool.driver.version` (a `version` key next to `"name": "rac"`).
/// Mask ONLY those two; the SARIF top-level `"version": "2.1.0"` is a
/// contract constant and stays comparable. Oracle-vs-oracle needs no version
/// handling (same binary), but the cases declare it so the same case file
/// stays valid once engine B is the Rust binary without the seam set.
fn mask_version(stdout: &[u8]) -> Result<Vec<u8>, String> {
    let mut value = parse_json(stdout)?;
    fn walk(v: &mut Value) {
        match v {
            Value::Object(map) => {
                if map.contains_key("rac_version") {
                    map["rac_version"] = json!("<MASKED-VERSION>");
                }
                let is_rac_driver = map.get("name").and_then(Value::as_str) == Some("rac")
                    && map.contains_key("version");
                if is_rac_driver {
                    map["version"] = json!("<MASKED-VERSION>");
                }
                for (_, child) in map.iter_mut() {
                    walk(child);
                }
            }
            Value::Array(items) => items.iter_mut().for_each(walk),
            _ => {}
        }
    }
    walk(&mut value);
    serialize_json(&value)
}

fn parse_json(stdout: &[u8]) -> Result<Value, String> {
    serde_json::from_slice(stdout).map_err(|e| format!("stdout is not valid JSON: {e}"))
}

fn serialize_json(value: &Value) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    bytes.push(b'\n'); // the oracle's `print` newline
    Ok(bytes)
}

fn apply_normalizations(names: &[String], stdout: &[u8]) -> Result<Vec<u8>, String> {
    let mut cur = stdout.to_vec();
    for name in names {
        cur = match name.as_str() {
            "strip-recency-json" => strip_recency_json(&cur),
            "strip-stale-human" => strip_stale_human(&cur),
            "mask-version" => mask_version(&cur),
            other => Err(format!("unknown normalization: {other}")),
        }
        .map_err(|e| format!("normalization {name:?} failed: {e}"))?;
    }
    Ok(cur)
}

// ---------------------------------------------------------------------------
// Engine execution
// ---------------------------------------------------------------------------

struct RunOutput {
    exit: i32,
    stdout: Vec<u8>,
    stderr_len: usize,
}

/// Deterministic base environment for every engine run (PORT-CONTRACT.d/01
/// §5.3 recommended invocation):
/// - env is cleared and rebuilt: only PATH and HOME are inherited (git
///   subprocesses need PATH; git identity/config lookup uses HOME — both
///   engines see the same values so recency output stays comparable);
/// - XDG_{CONFIG,STATE,CACHE}_HOME point at harness scratch dirs so no run
///   reads or writes real user state — with no consent file recorded the
///   oracle's usage ping / telemetry stays neutralized and nothing touches
///   the network (ADR-041 posture);
/// - RAC_NO_CACHE=1 forces the simple walk (output-neutral per ADR-106/112,
///   removes cache-state variance);
/// - LC_ALL=C, TZ=UTC, COLUMNS=80 pin incidental locale/width sensitivity;
/// - PYTHONHASHSEED=0 pins any set-iteration-order dependence in the oracle.
fn base_env(xdg_root: &Path) -> Vec<(String, String)> {
    let mut env: Vec<(String, String)> = Vec::new();
    for inherited in ["PATH", "HOME"] {
        if let Ok(v) = std::env::var(inherited) {
            env.push((inherited.to_string(), v));
        }
    }
    let xdg = |leaf: &str| xdg_root.join(leaf).to_string_lossy().into_owned();
    env.push(("XDG_CONFIG_HOME".into(), xdg("config")));
    env.push(("XDG_STATE_HOME".into(), xdg("state")));
    env.push(("XDG_CACHE_HOME".into(), xdg("cache")));
    env.push(("RAC_NO_CACHE".into(), "1".into()));
    env.push(("LC_ALL".into(), "C".into()));
    env.push(("TZ".into(), "UTC".into()));
    env.push(("COLUMNS".into(), "80".into()));
    env.push(("PYTHONHASHSEED".into(), "0".into()));
    env
}

fn run_engine(
    engine: &Path,
    case: &Case,
    repo_root: &Path,
    base: &[(String, String)],
) -> Result<RunOutput, String> {
    let cwd = repo_root.join(&case.cwd);
    let mut cmd = Command::new(engine);
    cmd.args(&case.argv)
        .current_dir(&cwd)
        .stdin(Stdio::null()) // immediate EOF; isatty(stdin) false
        .stdout(Stdio::piped()) // isatty(stdout) false -> no ANSI on either side
        .stderr(Stdio::piped());
    cmd.env_clear();
    for (k, v) in base {
        cmd.env(k, v);
    }
    for (k, v) in &case.env {
        cmd.env(k, v);
    }
    let out = cmd
        .output()
        .map_err(|e| format!("failed to spawn {}: {e}", engine.display()))?;
    let exit = out.status.code().unwrap_or_else(|| {
        use std::os::unix::process::ExitStatusExt;
        128 + out.status.signal().unwrap_or(0)
    });
    Ok(RunOutput {
        exit,
        stdout: out.stdout,
        stderr_len: out.stderr.len(),
    })
}

// ---------------------------------------------------------------------------
// Comparison / reporting
// ---------------------------------------------------------------------------

struct CaseResult {
    id: String,
    pass: bool,
    exit_a: i32,
    exit_b: i32,
    expect_exit: i32,
    stdout_bytes_a: usize,
    stdout_bytes_b: usize,
    stderr_bytes_a: usize,
    stderr_bytes_b: usize,
    normalize: Vec<String>,
    fail_reasons: Vec<String>,
    first_diff_offset: Option<usize>,
    diff_context: Option<String>,
}

fn first_diff(a: &[u8], b: &[u8]) -> Option<usize> {
    let n = a.len().min(b.len());
    (0..n).find(|&i| a[i] != b[i]).or({
        if a.len() != b.len() {
            Some(n)
        } else {
            None
        }
    })
}

/// Hexdump a window of `bytes` around `offset` (16-byte rows, hex + printable
/// ASCII), for the failure context in the scoreboard.
fn hexdump_window(bytes: &[u8], offset: usize) -> String {
    let start = (offset / 16).saturating_sub(1) * 16;
    let end = (start + 4 * 16).min(bytes.len());
    let mut out = String::new();
    let mut row = start;
    while row < end {
        let slice = &bytes[row..(row + 16).min(end)];
        let _ = write!(out, "{row:08x}  ");
        for i in 0..16 {
            if i == 8 {
                out.push(' ');
            }
            match slice.get(i) {
                Some(byte) => {
                    let _ = write!(out, "{byte:02x} ");
                }
                None => out.push_str("   "),
            }
        }
        out.push_str(" |");
        for byte in slice {
            out.push(if (0x20..0x7f).contains(byte) {
                *byte as char
            } else {
                '.'
            });
        }
        out.push_str("|\n");
        row += 16;
    }
    if end < bytes.len() {
        let _ = writeln!(out, "… ({} more bytes)", bytes.len() - end);
    }
    out
}

fn judge_case(case: &Case, a: &RunOutput, b: &RunOutput) -> CaseResult {
    let mut reasons: Vec<String> = Vec::new();

    if a.exit != b.exit {
        reasons.push(format!("exit code mismatch: A={} B={}", a.exit, b.exit));
    }
    if a.exit == b.exit && a.exit != case.expect_exit {
        reasons.push(format!(
            "exit code {} differs from recorded expectation {}",
            a.exit, case.expect_exit
        ));
    }
    if !case.expect_nonzero_ok && (a.exit != 0 || b.exit != 0) {
        reasons.push(format!(
            "nonzero exit (A={} B={}) but case is not flagged expect_nonzero_ok",
            a.exit, b.exit
        ));
    }

    let norm_a = apply_normalizations(&case.normalize, &a.stdout);
    let norm_b = apply_normalizations(&case.normalize, &b.stdout);
    let mut first_diff_offset = None;
    let mut diff_context = None;
    match (&norm_a, &norm_b) {
        (Ok(na), Ok(nb)) => {
            if let Some(off) = first_diff(na, nb) {
                reasons.push(format!(
                    "stdout mismatch at byte {off} (normalized lengths A={} B={})",
                    na.len(),
                    nb.len()
                ));
                first_diff_offset = Some(off);
                diff_context = Some(format!(
                    "engine A (normalized):\n{}\nengine B (normalized):\n{}",
                    hexdump_window(na, off),
                    hexdump_window(nb, off)
                ));
            }
        }
        (Err(e), _) => reasons.push(format!("engine A: {e}")),
        (_, Err(e)) => reasons.push(format!("engine B: {e}")),
    }

    CaseResult {
        id: case.id.clone(),
        pass: reasons.is_empty(),
        exit_a: a.exit,
        exit_b: b.exit,
        expect_exit: case.expect_exit,
        stdout_bytes_a: a.stdout.len(),
        stdout_bytes_b: b.stdout.len(),
        stderr_bytes_a: a.stderr_len,
        stderr_bytes_b: b.stderr_len,
        normalize: case.normalize.clone(),
        fail_reasons: reasons,
        first_diff_offset,
        diff_context,
    }
}

fn scoreboard_json(args: &Args, results: &[CaseResult]) -> Value {
    let passed = results.iter().filter(|r| r.pass).count();
    json!({
        "schema_version": "1",
        "engine_a": args.engine_a.to_string_lossy(),
        "engine_b": args.engine_b.to_string_lossy(),
        "cases_file": args.cases.to_string_lossy(),
        "filter": args.filter,
        "total": results.len(),
        "passed": passed,
        "failed": results.len() - passed,
        "cases": results.iter().map(|r| json!({
            "id": r.id,
            "pass": r.pass,
            "exit_a": r.exit_a,
            "exit_b": r.exit_b,
            "expect_exit": r.expect_exit,
            "stdout_bytes_a": r.stdout_bytes_a,
            "stdout_bytes_b": r.stdout_bytes_b,
            "stderr_bytes_a": r.stderr_bytes_a,
            "stderr_bytes_b": r.stderr_bytes_b,
            "normalize": r.normalize,
            "fail_reasons": r.fail_reasons,
            "first_diff_offset": r.first_diff_offset,
        })).collect::<Vec<_>>(),
    })
}

fn scoreboard_md(args: &Args, results: &[CaseResult]) -> String {
    let passed = results.iter().filter(|r| r.pass).count();
    let mut md = String::new();
    let _ = writeln!(md, "# Parity scoreboard");
    let _ = writeln!(md);
    let _ = writeln!(md, "- engine A: `{}`", args.engine_a.display());
    let _ = writeln!(md, "- engine B: `{}`", args.engine_b.display());
    let _ = writeln!(md, "- cases: `{}`", args.cases.display());
    if let Some(f) = &args.filter {
        let _ = writeln!(md, "- filter: `{f}`");
    }
    let _ = writeln!(
        md,
        "- result: **{passed}/{} passed{}**",
        results.len(),
        if passed == results.len() { "" } else { " — FAIL" }
    );
    let _ = writeln!(md);
    let _ = writeln!(
        md,
        "| case | result | exit A | exit B | expected | stdout A | stdout B | normalizations |"
    );
    let _ = writeln!(md, "|---|---|---|---|---|---|---|---|");
    for r in results {
        let _ = writeln!(
            md,
            "| {} | {} | {} | {} | {} | {} | {} | {} |",
            r.id,
            if r.pass { "PASS" } else { "**FAIL**" },
            r.exit_a,
            r.exit_b,
            r.expect_exit,
            r.stdout_bytes_a,
            r.stdout_bytes_b,
            if r.normalize.is_empty() {
                "—".to_string()
            } else {
                r.normalize.join(", ")
            },
        );
    }
    let failures: Vec<&CaseResult> = results.iter().filter(|r| !r.pass).collect();
    if !failures.is_empty() {
        let _ = writeln!(md);
        let _ = writeln!(md, "## Failures");
        for r in failures {
            let _ = writeln!(md);
            let _ = writeln!(md, "### {}", r.id);
            let _ = writeln!(md);
            for reason in &r.fail_reasons {
                let _ = writeln!(md, "- {reason}");
            }
            if let Some(off) = r.first_diff_offset {
                let _ = writeln!(md);
                let _ = writeln!(md, "First diff at byte offset {off}:");
                let _ = writeln!(md);
                if let Some(ctx) = &r.diff_context {
                    let _ = writeln!(md, "```");
                    md.push_str(ctx);
                    let _ = writeln!(md, "```");
                }
            }
        }
    }
    md
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

fn run() -> Result<i32, String> {
    let args = parse_args()?;

    let cases_path = fs::canonicalize(&args.cases)
        .map_err(|e| format!("cannot resolve --cases {}: {e}", args.cases.display()))?;
    let cases_text = fs::read_to_string(&cases_path)
        .map_err(|e| format!("cannot read {}: {e}", cases_path.display()))?;
    let cases: Vec<Case> = serde_json::from_str(&cases_text)
        .map_err(|e| format!("invalid case file {}: {e}", cases_path.display()))?;

    // Duplicate case ids would make scoreboard rows ambiguous — refuse.
    {
        let mut seen = std::collections::BTreeSet::new();
        for c in &cases {
            if !seen.insert(&c.id) {
                return Err(format!("duplicate case id: {}", c.id));
            }
        }
    }

    // Repo root: explicit --repo-root, else derived from the case file's
    // location (the case file lives at <repo>/rust/parity-cases.json).
    let repo_root = match &args.repo_root {
        Some(p) => fs::canonicalize(p)
            .map_err(|e| format!("cannot resolve --repo-root {}: {e}", p.display()))?,
        None => cases_path
            .parent()
            .and_then(Path::parent)
            .ok_or("cannot derive repo root from --cases path; pass --repo-root")?
            .to_path_buf(),
    };

    // Engines resolved to absolute paths up front: children run with a
    // per-case cwd, so relative engine paths must be pinned now.
    let engine_a = fs::canonicalize(&args.engine_a)
        .map_err(|e| format!("cannot resolve --engine-a {}: {e}", args.engine_a.display()))?;
    let engine_b = fs::canonicalize(&args.engine_b)
        .map_err(|e| format!("cannot resolve --engine-b {}: {e}", args.engine_b.display()))?;

    let selected: Vec<&Case> = match &args.filter {
        Some(f) => cases.iter().filter(|c| c.id.contains(f.as_str())).collect(),
        None => cases.iter().collect(),
    };
    if selected.is_empty() {
        return Err(match &args.filter {
            Some(f) => format!("no cases match --filter {f:?}"),
            None => "case file contains no cases".to_string(),
        });
    }

    fs::create_dir_all(&args.scoreboard_dir)
        .map_err(|e| format!("cannot create {}: {e}", args.scoreboard_dir.display()))?;
    let xdg_root = fs::canonicalize(&args.scoreboard_dir)
        .map_err(|e| e.to_string())?
        .join("xdg-scratch");
    for leaf in ["config", "state", "cache"] {
        fs::create_dir_all(xdg_root.join(leaf)).map_err(|e| e.to_string())?;
    }
    let base = base_env(&xdg_root);

    let mut results = Vec::with_capacity(selected.len());
    for case in &selected {
        let out_a = run_engine(&engine_a, case, &repo_root, &base)?;
        let out_b = run_engine(&engine_b, case, &repo_root, &base)?;
        let result = judge_case(case, &out_a, &out_b);
        eprintln!(
            "{} {} (exit A={} B={})",
            if result.pass { "PASS" } else { "FAIL" },
            result.id,
            result.exit_a,
            result.exit_b
        );
        results.push(result);
    }

    let board = scoreboard_json(&args, &results);
    let mut board_bytes = serde_json::to_vec_pretty(&board).map_err(|e| e.to_string())?;
    board_bytes.push(b'\n');
    fs::write(args.scoreboard_dir.join("scoreboard.json"), board_bytes)
        .map_err(|e| e.to_string())?;
    fs::write(
        args.scoreboard_dir.join("scoreboard.md"),
        scoreboard_md(&args, &results),
    )
    .map_err(|e| e.to_string())?;

    let passed = results.iter().filter(|r| r.pass).count();
    eprintln!("parity: {passed}/{} cases passed", results.len());
    Ok(if passed == results.len() { 0 } else { 1 })
}

fn main() {
    match run() {
        Ok(code) => std::process::exit(code),
        Err(msg) => {
            eprintln!("parity-harness: {msg}");
            std::process::exit(2);
        }
    }
}
