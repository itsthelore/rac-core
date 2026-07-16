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

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;
use std::fs;
use std::os::unix::fs::PermissionsExt;
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
    /// Optional file (relative to the repo root) whose RAW BYTES are piped
    /// to both engines' stdin — for `validate -` cases (fuzz campaign 2
    /// pinned regressions). Default: null stdin (immediate EOF).
    #[serde(default)]
    stdin_file: Option<String>,
    /// Optional literal text piped to both engines' stdin — for prompt-fed
    /// commands (init/quickstart) where the bytes are short and belong in
    /// the case itself. Mutually exclusive with `stdin_file`.
    #[serde(default)]
    stdin_text: Option<String>,
    /// When present, EACH engine run gets its own fresh sandbox directory
    /// built from this spec, so write commands cannot collide across
    /// engines or leak between cases. `{SANDBOX}` in argv, env values, and
    /// cwd resolves per engine to that engine's sandbox root (absolute).
    #[serde(default)]
    sandbox: Option<Sandbox>,
    /// Post-run capture globs/paths, relative to the sandbox root (`*`/`?`
    /// within a component, `**` across components). `.git` trees are excluded
    /// UNLESS a capture pattern explicitly names a `.git` component (hook
    /// install cases referee `.git/hooks/<style>`; git internals like the
    /// index stat cache stay out of scope because the explicit patterns
    /// select only the written hook files). After both engines run, the
    /// captured file SETS must be identical and each common file's bytes must
    /// match after the case's normalizations — written trees are refereed
    /// like stdout.
    #[serde(default)]
    capture: Vec<String>,
    /// Also demand identical executable bits on captured files (hook
    /// install cases). Default: bytes only.
    #[serde(default)]
    compare_file_mode: bool,
    /// Byte-compare STDERR as well (after the case's normalizations), for
    /// commands whose stderr is contract-shaped and deterministic —
    /// watchkeeper's github-mode annotations, `rac: <msg>` usage errors,
    /// and empty-stderr proofs. Default false: stderr is recorded (length
    /// only) but not refereed, because argparse usage bodies and traceback
    /// tails are documented out-of-scope divergences.
    #[serde(default)]
    compare_stderr: bool,
}

/// Per-engine sandbox spec: a fixture tree to copy in, then ordered setup
/// steps. Deterministic by construction — nothing here reads the wall
/// clock (git commits carry pinned dates).
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Sandbox {
    /// Directory (relative to the repo root) whose tree is copied into the
    /// sandbox root before setup runs. Closure fixtures live under
    /// `rust/fixtures/closure/`; keep them clean — the oracle crashes on
    /// hostile markdown during corpus walks (`new` brief).
    #[serde(default)]
    fixture: Option<String>,
    /// Setup steps executed in declared order inside the sandbox before
    /// the engine runs. Working-tree mutations "after a commit" are simply
    /// `write` steps placed after a `git` step.
    #[serde(default)]
    setup: Vec<SetupStep>,
}

/// One ordered sandbox setup step; `step` selects the variant.
#[derive(Debug, Deserialize)]
#[serde(tag = "step", rename_all = "kebab-case", deny_unknown_fields)]
enum SetupStep {
    /// Write a file (parents created) with literal content.
    Write { path: String, content: String },
    /// Create a directory (and parents) — e.g. an empty template target
    /// that a copied fixture cannot carry (git drops empty dirs).
    Mkdir { path: String },
    /// Set mode 0o755 (executable) on an existing file.
    ChmodExec { path: String },
    /// Copy a fixture tree (`from` relative to the repo root) to a
    /// sandbox-relative destination.
    CopyTree { from: String, to: String },
    /// Script a git repository at `path` (default: the sandbox root):
    /// `git init -b main`, then one commit per entry under a fixed fixture
    /// identity with GIT_AUTHOR_DATE and GIT_COMMITTER_DATE pinned to the
    /// entry's `date` (TZ offset preserved). No wall clock anywhere.
    Git {
        #[serde(default = "default_cwd")]
        path: String,
        commits: Vec<GitCommit>,
    },
    /// Remove a file (or an empty directory) inside the sandbox — the
    /// delete/rename half of cache staleness cases (INDEX-PLAN B4). A
    /// missing target is a setup error: a case that deletes nothing is
    /// not testing what it claims.
    Remove { path: String },
    /// Run the SIDE'S OWN engine once inside the sandbox before the
    /// refereed run — the cache-warming step (INDEX-PLAN P0). argv gets
    /// `{SANDBOX}` resolved; env is the same deterministic base + case
    /// env the refereed run sees, so a case that points `RAC_CACHE_DIR`
    /// into the sandbox and clears `RAC_NO_CACHE` warms exactly the
    /// cache the refereed run then reads. cwd is sandbox-relative
    /// (default the sandbox root); stdout/stderr are discarded; `expect_exit`
    /// (default 0) must match or the case errors out loudly — a warm run
    /// that fails unexpectedly must never referee silently.
    EngineRun {
        argv: Vec<String>,
        #[serde(default = "default_cwd")]
        cwd: String,
        #[serde(default)]
        expect_exit: i32,
    },
}

/// One scripted commit: files written first, then `git add -A` + commit.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct GitCommit {
    /// Pinned author+committer date with explicit offset, e.g.
    /// "2024-03-05T10:00:00+02:00".
    date: String,
    message: String,
    /// Files (git-dir-relative) written before this commit stages.
    #[serde(default)]
    write: Vec<GitWrite>,
}

/// A file written as part of a scripted commit.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct GitWrite {
    path: String,
    content: String,
}

fn default_cwd() -> String {
    ".".to_string()
}

/// Placeholder in argv/env/cwd resolved per engine to its sandbox root.
const SANDBOX_TOKEN: &str = "{SANDBOX}";

fn resolve_token(s: &str, sandbox_root: Option<&str>, case_id: &str) -> Result<String, String> {
    if !s.contains(SANDBOX_TOKEN) {
        return Ok(s.to_string());
    }
    let root = sandbox_root.ok_or_else(|| {
        format!("case {case_id} uses {SANDBOX_TOKEN} but declares no sandbox")
    })?;
    Ok(s.replace(SANDBOX_TOKEN, root))
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
    for_each_object(&mut value, &mut |map| {
        map.shift_remove("recency");
    });
    serialize_json(&value)
}

/// Depth-first walk applying `f` to every JSON object, parent before
/// children — the shared traversal skeleton of the two JSON normalizers.
fn for_each_object(v: &mut Value, f: &mut impl FnMut(&mut serde_json::Map<String, Value>)) {
    match v {
        Value::Object(map) => {
            f(map);
            for (_, child) in map.iter_mut() {
                for_each_object(child, f);
            }
        }
        Value::Array(items) => items.iter_mut().for_each(|item| for_each_object(item, f)),
        _ => {}
    }
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
    for_each_object(&mut value, &mut |map| {
        if let Some(slot) = map.get_mut("rac_version") {
            *slot = json!("<MASKED-VERSION>");
        }
        if map.get("name").and_then(Value::as_str) == Some("rac") {
            if let Some(slot) = map.get_mut("version") {
                *slot = json!("<MASKED-VERSION>");
            }
        }
    });
    serialize_json(&value)
}

/// "mask-ids" — minted artifact ids are wall-clock+CSPRNG-derived
/// (`<KEY>-` + 12 Crockford-base32 chars, per the `new` brief) and the
/// oracle exposes no seam to pin them, so cases mask them instead: every
/// token matching `[A-Z]{2,8}-[0-9A-HJKMNP-TV-Z]{12}` at word boundaries
/// has its 12-char tail replaced with the fixed (still-Crockford) token
/// `MASKEDMASKED`. The key is kept so a key divergence stays visible.
/// Applied to captured file bytes too, so written frontmatter compares.
fn mask_ids(stdout: &[u8]) -> Result<Vec<u8>, String> {
    const TAIL: usize = 12;
    fn crockford(b: u8) -> bool {
        // Crockford base32: 0-9 plus A-Z without I, L, O, U.
        b.is_ascii_digit()
            || (b.is_ascii_uppercase() && !matches!(b, b'I' | b'L' | b'O' | b'U'))
    }
    fn word(b: u8) -> bool {
        b.is_ascii_alphanumeric() || b == b'_'
    }
    let n = stdout.len();
    let mut out = Vec::with_capacity(n);
    let mut i = 0;
    while i < n {
        let boundary = i == 0 || (!word(stdout[i - 1]) && stdout[i - 1] != b'-');
        if boundary && stdout[i].is_ascii_uppercase() {
            let mut k = i;
            while k < n && stdout[k].is_ascii_uppercase() {
                k += 1;
            }
            if (2..=8).contains(&(k - i))
                && k < n
                && stdout[k] == b'-'
                && k + 1 + TAIL <= n
                && stdout[k + 1..k + 1 + TAIL].iter().all(|&c| crockford(c))
                && (k + 1 + TAIL == n || !word(stdout[k + 1 + TAIL]))
            {
                out.extend_from_slice(&stdout[i..=k]); // key + '-'
                out.extend_from_slice(b"MASKEDMASKED");
                i = k + 1 + TAIL;
                continue;
            }
        }
        out.push(stdout[i]);
        i += 1;
    }
    Ok(out)
}

/// "mask-json-field:<dotted>" — replace the value at a dotted key path
/// (e.g. `metadata.generated_at`) with "<MASKED-FIELD>" wherever the path
/// matches under ANY object in the payload. Exists for clock/build-derived
/// JSON fields (eval `metadata.generated_at` / `metadata.lore_version`,
/// per the eval brief).
fn mask_json_field(stdout: &[u8], dotted: &str) -> Result<Vec<u8>, String> {
    let segs: Vec<&str> = dotted.split('.').collect();
    if segs.iter().any(|s| s.is_empty()) {
        return Err(format!("invalid dotted key path: {dotted:?}"));
    }
    fn mask_at(map: &mut serde_json::Map<String, Value>, segs: &[&str]) {
        if segs.len() == 1 {
            if let Some(slot) = map.get_mut(segs[0]) {
                *slot = json!("<MASKED-FIELD>");
            }
        } else if let Some(Value::Object(child)) = map.get_mut(segs[0]) {
            mask_at(child, &segs[1..]);
        }
    }
    let mut value = parse_json(stdout)?;
    for_each_object(&mut value, &mut |map| mask_at(map, &segs));
    serialize_json(&value)
}

/// "mask-consent-mint" — `telemetry on` mints install_id/salt
/// (`secrets.token_hex(16)` -> 32 lowercase hex) and re-mints consented_at
/// (`isoformat(timespec="seconds")` with `+00:00` -> `Z`) on every opt-in,
/// and the oracle exposes NO seam to pin any of them (unlike the
/// `RAC_RS_VERSION` build seam), so the referee masks exactly those two
/// minted shapes instead: a maximal 32-char lowercase-hex run at word
/// boundaries becomes `<MASKED-HEX32>`, and a `dddd-dd-ddTdd:dd:ddZ`
/// timestamp at digit/word boundaries becomes `<MASKED-UTC-TS>`. Applied
/// to stdout AND captured files (the written telemetry.json), like every
/// normalization. Cases that must referee id PRESERVATION seed ids that do
/// not match the hex32 shape, so a wrongly re-minted id stays visible.
fn mask_consent_mint(stdout: &[u8]) -> Result<Vec<u8>, String> {
    fn word(b: u8) -> bool {
        b.is_ascii_alphanumeric() || b == b'_'
    }
    fn hex(b: u8) -> bool {
        b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
    }
    /// `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z` starting at `i`.
    fn ts_at(s: &[u8], i: usize) -> bool {
        const SHAPE: &[u8] = b"dddd-dd-ddTdd:dd:ddZ";
        if i + SHAPE.len() > s.len() {
            return false;
        }
        SHAPE.iter().enumerate().all(|(k, &c)| match c {
            b'd' => s[i + k].is_ascii_digit(),
            lit => s[i + k] == lit,
        })
    }
    const TS_LEN: usize = 20;
    const HEX_LEN: usize = 32;
    let n = stdout.len();
    let mut out = Vec::with_capacity(n);
    let mut i = 0;
    while i < n {
        let prev_word = i > 0 && word(stdout[i - 1]);
        if !prev_word
            && ts_at(stdout, i)
            && (i + TS_LEN == n || !word(stdout[i + TS_LEN]))
        {
            out.extend_from_slice(b"<MASKED-UTC-TS>");
            i += TS_LEN;
            continue;
        }
        if !prev_word && hex(stdout[i]) {
            let mut k = i;
            while k < n && hex(stdout[k]) {
                k += 1;
            }
            if k - i == HEX_LEN && (k == n || !word(stdout[k])) {
                out.extend_from_slice(b"<MASKED-HEX32>");
                i = k;
                continue;
            }
        }
        out.push(stdout[i]);
        i += 1;
    }
    Ok(out)
}

/// "mask-sandbox-path" — sandboxed runs give each engine its OWN root, so
/// output embedding the root (argv echoes, absolute-path listings) differs
/// across engines by construction. Replace every occurrence of the
/// engine's own root with "<SANDBOX>" before compare.
fn mask_sandbox_path(stdout: &[u8], ctx: &NormCtx) -> Result<Vec<u8>, String> {
    let root = ctx
        .sandbox_root
        .ok_or("case declares no sandbox, so there is no root to mask")?;
    Ok(replace_all(stdout, root.as_bytes(), b"<SANDBOX>"))
}

fn replace_all(haystack: &[u8], needle: &[u8], replacement: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(haystack.len());
    let mut i = 0;
    while i < haystack.len() {
        if haystack[i..].starts_with(needle) {
            out.extend_from_slice(replacement);
            i += needle.len();
        } else {
            out.push(haystack[i]);
            i += 1;
        }
    }
    out
}

fn parse_json(stdout: &[u8]) -> Result<Value, String> {
    serde_json::from_slice(stdout).map_err(|e| format!("stdout is not valid JSON: {e}"))
}

fn serialize_json(value: &Value) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    bytes.push(b'\n'); // the oracle's `print` newline
    Ok(bytes)
}

/// Per-engine context consumed by side-dependent normalizations
/// ("mask-sandbox-path" masks each side's OWN sandbox root).
struct NormCtx<'a> {
    sandbox_root: Option<&'a str>,
}

fn apply_normalizations(names: &[String], stdout: &[u8], ctx: &NormCtx) -> Result<Vec<u8>, String> {
    let mut cur = stdout.to_vec();
    for name in names {
        cur = if let Some(dotted) = name.strip_prefix("mask-json-field:") {
            mask_json_field(&cur, dotted)
        } else {
            match name.as_str() {
                "strip-recency-json" => strip_recency_json(&cur),
                "strip-stale-human" => strip_stale_human(&cur),
                "mask-version" => mask_version(&cur),
                "mask-ids" => mask_ids(&cur),
                "mask-consent-mint" => mask_consent_mint(&cur),
                "mask-sandbox-path" => mask_sandbox_path(&cur, ctx),
                other => Err(format!("unknown normalization: {other}")),
            }
        }
        .map_err(|e| format!("normalization {name:?} failed: {e}"))?;
    }
    Ok(cur)
}

// ---------------------------------------------------------------------------
// Sandboxes, setup steps, and post-run capture
//
// Write commands (new, rename --apply, migrate, init, export --okf, ...)
// cannot share the repo tree or one common cwd: each engine gets a fresh
// per-case sandbox, and the written tree is refereed after the run.
// ---------------------------------------------------------------------------

fn write_file(root: &Path, rel: &str, content: &str) -> Result<(), String> {
    let path = root.join(rel);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("cannot create {}: {e}", parent.display()))?;
    }
    fs::write(&path, content).map_err(|e| format!("cannot write {}: {e}", path.display()))
}

/// Recursive tree copy; `fs::copy` preserves permission bits, so fixture
/// executables stay executable.
fn copy_tree(src: &Path, dst: &Path) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| format!("cannot create {}: {e}", dst.display()))?;
    let entries =
        fs::read_dir(src).map_err(|e| format!("cannot read dir {}: {e}", src.display()))?;
    for entry in entries {
        let entry = entry.map_err(|e| format!("cannot read dir {}: {e}", src.display()))?;
        let from = entry.path();
        let to = dst.join(entry.file_name());
        let ty = entry
            .file_type()
            .map_err(|e| format!("cannot stat {}: {e}", from.display()))?;
        if ty.is_dir() {
            copy_tree(&from, &to)?;
        } else {
            fs::copy(&from, &to)
                .map_err(|e| format!("cannot copy {} -> {}: {e}", from.display(), to.display()))?;
        }
    }
    Ok(())
}

/// Run one git command for a scripted fixture under a pinned, deterministic
/// environment: fixed fixture identity, per-commit pinned dates (offset
/// preserved), no user/system config, no wall clock.
fn run_git(dir: &Path, args: &[&str], date: Option<&str>) -> Result<(), String> {
    let mut cmd = Command::new("git");
    cmd.args(args)
        .current_dir(dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    cmd.env_clear();
    if let Ok(path) = std::env::var("PATH") {
        cmd.env("PATH", path);
    }
    cmd.env("HOME", dir); // never read the real user's git config
    cmd.env("GIT_CONFIG_NOSYSTEM", "1");
    cmd.env("TZ", "UTC");
    cmd.env("GIT_AUTHOR_NAME", "Parity Fixture");
    cmd.env("GIT_AUTHOR_EMAIL", "parity@example.invalid");
    cmd.env("GIT_COMMITTER_NAME", "Parity Fixture");
    cmd.env("GIT_COMMITTER_EMAIL", "parity@example.invalid");
    if let Some(d) = date {
        cmd.env("GIT_AUTHOR_DATE", d);
        cmd.env("GIT_COMMITTER_DATE", d);
    }
    let out = cmd
        .output()
        .map_err(|e| format!("failed to spawn git: {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "git {:?} in {} failed: {}",
            args,
            dir.display(),
            String::from_utf8_lossy(&out.stderr).trim()
        ));
    }
    Ok(())
}

/// Everything an `engine-run` setup step needs about the side it warms.
struct SetupCtx<'a> {
    engine: &'a Path,
    case: &'a Case,
    base: &'a [(String, String)],
}

fn run_setup_engine(
    argv: &[String],
    cwd: &str,
    expect_exit: i32,
    root: &Path,
    ctx: &SetupCtx,
) -> Result<(), String> {
    let sandbox_root = root.to_string_lossy().into_owned();
    let resolve = |s: &str| resolve_token(s, Some(&sandbox_root), &ctx.case.id);
    let mut cmd = Command::new(ctx.engine);
    for arg in argv {
        cmd.arg(resolve(arg)?);
    }
    cmd.current_dir(root.join(resolve(cwd)?))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    cmd.env_clear();
    for (k, v) in ctx.base {
        cmd.env(k, v);
    }
    for (k, v) in &ctx.case.env {
        cmd.env(k, resolve(v)?);
    }
    let out = cmd
        .output()
        .map_err(|e| format!("engine-run failed to spawn {}: {e}", ctx.engine.display()))?;
    let exit = out.status.code().unwrap_or_else(|| {
        use std::os::unix::process::ExitStatusExt;
        128 + out.status.signal().unwrap_or(0)
    });
    if exit != expect_exit {
        return Err(format!(
            "engine-run {argv:?} exited {exit} (expected {expect_exit}); stderr: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        ));
    }
    Ok(())
}

fn apply_setup_step(
    step: &SetupStep,
    root: &Path,
    repo_root: &Path,
    ctx: &SetupCtx,
) -> Result<(), String> {
    match step {
        SetupStep::Write { path, content } => write_file(root, path, content),
        SetupStep::Mkdir { path } => {
            let dir = root.join(path);
            fs::create_dir_all(&dir).map_err(|e| format!("cannot create {}: {e}", dir.display()))
        }
        SetupStep::ChmodExec { path } => {
            let target = root.join(path);
            fs::set_permissions(&target, fs::Permissions::from_mode(0o755))
                .map_err(|e| format!("cannot chmod {}: {e}", target.display()))
        }
        SetupStep::CopyTree { from, to } => copy_tree(&repo_root.join(from), &root.join(to)),
        SetupStep::Git { path, commits } => {
            let dir = root.join(path);
            fs::create_dir_all(&dir)
                .map_err(|e| format!("cannot create {}: {e}", dir.display()))?;
            run_git(&dir, &["init", "-q", "-b", "main"], None)?;
            for commit in commits {
                for w in &commit.write {
                    write_file(&dir, &w.path, &w.content)?;
                }
                run_git(&dir, &["add", "-A"], None)?;
                run_git(
                    &dir,
                    &["commit", "-q", "--allow-empty", "-m", &commit.message],
                    Some(&commit.date),
                )?;
            }
            Ok(())
        }
        SetupStep::Remove { path } => {
            let target = root.join(path);
            let result = if target.is_dir() {
                fs::remove_dir(&target)
            } else {
                fs::remove_file(&target)
            };
            result.map_err(|e| format!("cannot remove {}: {e}", target.display()))
        }
        SetupStep::EngineRun {
            argv,
            cwd,
            expect_exit,
        } => run_setup_engine(argv, cwd, *expect_exit, root, ctx),
    }
}

/// Build one engine's fresh sandbox for a case under
/// `<scoreboard-dir>/sandboxes/<case-id>/<side>`: wiped if present, seeded
/// from the declared fixture tree, then mutated by the ordered setup steps.
/// Returns the canonicalized root (the exact string `{SANDBOX}` resolves
/// to and "mask-sandbox-path" masks). Left on disk for post-run forensics.
fn prepare_sandbox(
    case: &Case,
    side: &str,
    sandbox_area: &Path,
    repo_root: &Path,
    ctx: &SetupCtx,
) -> Result<Option<PathBuf>, String> {
    let Some(spec) = &case.sandbox else {
        return Ok(None);
    };
    let root = sandbox_area.join(&case.id).join(side);
    if root.exists() {
        fs::remove_dir_all(&root)
            .map_err(|e| format!("cannot clear sandbox {}: {e}", root.display()))?;
    }
    fs::create_dir_all(&root).map_err(|e| format!("cannot create {}: {e}", root.display()))?;
    let root = fs::canonicalize(&root).map_err(|e| e.to_string())?;
    if let Some(fixture) = &spec.fixture {
        copy_tree(&repo_root.join(fixture), &root)
            .map_err(|e| format!("case {} fixture: {e}", case.id))?;
    }
    for step in &spec.setup {
        apply_setup_step(step, &root, repo_root, ctx)
            .map_err(|e| format!("case {} setup: {e}", case.id))?;
    }
    Ok(Some(root))
}

/// One captured post-run file: raw bytes plus the owner-executable bit.
struct CapturedFile {
    bytes: Vec<u8>,
    executable: bool,
}

/// Minimal glob over '/'-separated relative paths: `**` matches any number
/// of components (including zero); `*`/`?` match within one component.
/// Hand-rolled to keep the harness dependency-free; capture sets are small.
fn glob_match(pattern: &str, path: &str) -> bool {
    fn match_comps(pat: &[&str], path: &[&str]) -> bool {
        match pat.first() {
            None => path.is_empty(),
            Some(&"**") => (0..=path.len()).any(|k| match_comps(&pat[1..], &path[k..])),
            Some(head) => {
                !path.is_empty()
                    && match_comp(head.as_bytes(), path[0].as_bytes())
                    && match_comps(&pat[1..], &path[1..])
            }
        }
    }
    fn match_comp(pat: &[u8], s: &[u8]) -> bool {
        match pat.first() {
            None => s.is_empty(),
            Some(b'*') => match_comp(&pat[1..], s) || (!s.is_empty() && match_comp(pat, &s[1..])),
            Some(b'?') => !s.is_empty() && match_comp(&pat[1..], &s[1..]),
            Some(&c) => !s.is_empty() && s[0] == c && match_comp(&pat[1..], &s[1..]),
        }
    }
    let pat: Vec<&str> = pattern.split('/').collect();
    let comps: Vec<&str> = path.split('/').collect();
    match_comps(&pat, &comps)
}

fn walk_files(
    root: &Path,
    dir: &Path,
    include_git: bool,
    out: &mut Vec<String>,
) -> Result<(), String> {
    let entries =
        fs::read_dir(dir).map_err(|e| format!("cannot read dir {}: {e}", dir.display()))?;
    for entry in entries {
        let entry = entry.map_err(|e| format!("cannot read dir {}: {e}", dir.display()))?;
        if entry.file_name() == ".git" && !include_git {
            continue; // git internals (index stat cache) are never comparable
        }
        let path = entry.path();
        let ty = entry
            .file_type()
            .map_err(|e| format!("cannot stat {}: {e}", path.display()))?;
        if ty.is_dir() {
            walk_files(root, &path, include_git, out)?;
        } else {
            let rel = path
                .strip_prefix(root)
                .expect("walked path is under root")
                .to_string_lossy()
                .into_owned();
            out.push(rel);
        }
    }
    Ok(())
}

/// Collect the case's post-run capture set from one sandbox: every file
/// under the sandbox root whose relative path matches any capture glob.
/// BTreeMap keys give a deterministic comparison order.
fn capture_files(
    case: &Case,
    sandbox: Option<&Path>,
) -> Result<BTreeMap<String, CapturedFile>, String> {
    if case.capture.is_empty() {
        return Ok(BTreeMap::new());
    }
    let root = sandbox
        .ok_or_else(|| format!("case {} declares capture but no sandbox", case.id))?;
    // `.git` trees are comparable only when a pattern names one explicitly
    // (hook install referees `.git/hooks/<style>`).
    let include_git = case
        .capture
        .iter()
        .any(|pat| pat.split('/').any(|comp| comp == ".git"));
    let mut files = Vec::new();
    walk_files(root, root, include_git, &mut files)?;
    let mut captured = BTreeMap::new();
    for rel in files {
        if case.capture.iter().any(|pat| glob_match(pat, &rel)) {
            let path = root.join(&rel);
            let meta = fs::metadata(&path)
                .map_err(|e| format!("cannot stat {}: {e}", path.display()))?;
            let bytes =
                fs::read(&path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
            let executable = meta.permissions().mode() & 0o100 != 0;
            captured.insert(rel, CapturedFile { bytes, executable });
        }
    }
    Ok(captured)
}

// ---------------------------------------------------------------------------
// Engine execution
// ---------------------------------------------------------------------------

struct RunOutput {
    exit: i32,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
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
    sandbox_root: Option<&str>,
) -> Result<RunOutput, String> {
    let resolve = |s: &str| resolve_token(s, sandbox_root, &case.id);
    // A `{SANDBOX}` cwd resolves absolute, so `join` uses it verbatim;
    // otherwise cwd stays repo-root-relative as before.
    let cwd = repo_root.join(resolve(&case.cwd)?);
    let stdin_bytes = match (&case.stdin_file, &case.stdin_text) {
        (Some(_), Some(_)) => {
            return Err(format!(
                "case {}: stdin_file and stdin_text are mutually exclusive",
                case.id
            ))
        }
        (Some(rel), None) => Some(std::fs::read(repo_root.join(rel)).map_err(|e| {
            format!("failed to read stdin_file {rel} for case {}: {e}", case.id)
        })?),
        (None, Some(text)) => Some(text.clone().into_bytes()),
        (None, None) => None,
    };
    let mut cmd = Command::new(engine);
    for arg in &case.argv {
        cmd.arg(resolve(arg)?);
    }
    cmd.current_dir(&cwd)
        // Piped stdin when the case supplies bytes, else immediate EOF.
        // isatty(stdin) is false either way.
        .stdin(if stdin_bytes.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped()) // isatty(stdout) false -> no ANSI on either side
        .stderr(Stdio::piped());
    cmd.env_clear();
    for (k, v) in base {
        cmd.env(k, v);
    }
    for (k, v) in &case.env {
        cmd.env(k, resolve(v)?);
    }
    let out = if let Some(bytes) = stdin_bytes {
        use std::io::Write;
        let mut child = cmd
            .spawn()
            .map_err(|e| format!("failed to spawn {}: {e}", engine.display()))?;
        {
            let mut sink = child.stdin.take().expect("piped stdin");
            let _ = sink.write_all(&bytes); // drop closes the pipe -> EOF
        }
        child
            .wait_with_output()
            .map_err(|e| format!("failed to wait on {}: {e}", engine.display()))?
    } else {
        cmd.output()
            .map_err(|e| format!("failed to spawn {}: {e}", engine.display()))?
    };
    let exit = out.status.code().unwrap_or_else(|| {
        use std::os::unix::process::ExitStatusExt;
        128 + out.status.signal().unwrap_or(0)
    });
    Ok(RunOutput {
        exit,
        stdout: out.stdout,
        stderr: out.stderr,
    })
}

/// Everything one engine produced for a case: process output, the sandbox
/// root it ran against (None for shared-tree cases), and the post-run
/// captured files.
struct EngineSide {
    out: RunOutput,
    sandbox_root: Option<String>,
    captured: BTreeMap<String, CapturedFile>,
}

/// One engine's full case execution: fresh sandbox (when declared), run,
/// post-run capture.
fn run_side(
    engine: &Path,
    case: &Case,
    side: &str,
    repo_root: &Path,
    base: &[(String, String)],
    sandbox_area: &Path,
) -> Result<EngineSide, String> {
    let ctx = SetupCtx { engine, case, base };
    let sandbox = prepare_sandbox(case, side, sandbox_area, repo_root, &ctx)?;
    let sandbox_root = sandbox.map(|p| p.to_string_lossy().into_owned());
    let out = run_engine(engine, case, repo_root, base, sandbox_root.as_deref())?;
    let captured = capture_files(case, sandbox_root.as_deref().map(Path::new))?;
    Ok(EngineSide {
        out,
        sandbox_root,
        captured,
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

fn judge_case(case: &Case, side_a: &EngineSide, side_b: &EngineSide) -> CaseResult {
    let a = &side_a.out;
    let b = &side_b.out;
    let ctx_a = NormCtx {
        sandbox_root: side_a.sandbox_root.as_deref(),
    };
    let ctx_b = NormCtx {
        sandbox_root: side_b.sandbox_root.as_deref(),
    };
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

    let norm_a = apply_normalizations(&case.normalize, &a.stdout, &ctx_a);
    let norm_b = apply_normalizations(&case.normalize, &b.stdout, &ctx_b);
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

    // stderr comparison, opt-in per case: same normalizations, same byte
    // referee, its own failure context (watchkeeper github-mode annotations
    // and `rac: <msg>` usage errors are contract-shaped stderr).
    if case.compare_stderr {
        match (
            apply_normalizations(&case.normalize, &a.stderr, &ctx_a),
            apply_normalizations(&case.normalize, &b.stderr, &ctx_b),
        ) {
            (Ok(na), Ok(nb)) => {
                if let Some(off) = first_diff(&na, &nb) {
                    reasons.push(format!(
                        "stderr mismatch at byte {off} (normalized lengths A={} B={})",
                        na.len(),
                        nb.len()
                    ));
                    if diff_context.is_none() {
                        diff_context = Some(format!(
                            "engine A stderr (normalized):\n{}\nengine B stderr (normalized):\n{}",
                            hexdump_window(&na, off),
                            hexdump_window(&nb, off)
                        ));
                    }
                }
            }
            (Err(e), _) => reasons.push(format!("engine A stderr: {e}")),
            (_, Err(e)) => reasons.push(format!("engine B stderr: {e}")),
        }
    }

    // Written-tree comparison: the captured file SETS must be identical,
    // then each common file's bytes after the case's normalizations (the
    // same ones applied to stdout), then modes when the case demands.
    let paths: BTreeSet<&String> = side_a.captured.keys().chain(side_b.captured.keys()).collect();
    for path in paths {
        let (fa, fb) = match (side_a.captured.get(path), side_b.captured.get(path)) {
            (Some(fa), Some(fb)) => (fa, fb),
            (present_a, _) => {
                reasons.push(format!(
                    "captured file {path}: present under engine {} only",
                    if present_a.is_some() { "A" } else { "B" }
                ));
                continue;
            }
        };
        match (
            apply_normalizations(&case.normalize, &fa.bytes, &ctx_a),
            apply_normalizations(&case.normalize, &fb.bytes, &ctx_b),
        ) {
            (Ok(na), Ok(nb)) => {
                if let Some(off) = first_diff(&na, &nb) {
                    reasons.push(format!(
                        "captured file {path}: mismatch at byte {off} (normalized lengths A={} B={})",
                        na.len(),
                        nb.len()
                    ));
                    if diff_context.is_none() {
                        diff_context = Some(format!(
                            "captured file {path}, engine A (normalized):\n{}\ncaptured file {path}, engine B (normalized):\n{}",
                            hexdump_window(&na, off),
                            hexdump_window(&nb, off)
                        ));
                    }
                }
            }
            (Err(e), _) => reasons.push(format!("captured file {path}, engine A: {e}")),
            (_, Err(e)) => reasons.push(format!("captured file {path}, engine B: {e}")),
        }
        if case.compare_file_mode && fa.executable != fb.executable {
            reasons.push(format!(
                "captured file {path}: executable bit differs (A={} B={})",
                fa.executable, fb.executable
            ));
        }
    }

    CaseResult {
        id: case.id.clone(),
        pass: reasons.is_empty(),
        exit_a: a.exit,
        exit_b: b.exit,
        expect_exit: case.expect_exit,
        stdout_bytes_a: a.stdout.len(),
        stdout_bytes_b: b.stdout.len(),
        stderr_bytes_a: a.stderr.len(),
        stderr_bytes_b: b.stderr.len(),
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
            }
            // Context also stands alone for captured-file mismatches, where
            // stdout matched and no stdout offset exists.
            if let Some(ctx) = &r.diff_context {
                let _ = writeln!(md);
                let _ = writeln!(md, "```");
                md.push_str(ctx);
                let _ = writeln!(md, "```");
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
    let scoreboard_root = fs::canonicalize(&args.scoreboard_dir).map_err(|e| e.to_string())?;
    let xdg_root = scoreboard_root.join("xdg-scratch");
    for leaf in ["config", "state", "cache"] {
        fs::create_dir_all(xdg_root.join(leaf)).map_err(|e| e.to_string())?;
    }
    // Per-case, per-engine sandboxes live next to the scoreboard.
    let sandbox_area = scoreboard_root.join("sandboxes");
    let base = base_env(&xdg_root);

    let mut results = Vec::with_capacity(selected.len());
    for case in &selected {
        let side_a = run_side(&engine_a, case, "a", &repo_root, &base, &sandbox_area)?;
        let side_b = run_side(&engine_b, case, "b", &repo_root, &base, &sandbox_area)?;
        let result = judge_case(case, &side_a, &side_b);
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
    fs::write(args.scoreboard_dir.join("scoreboard.json"), serialize_json(&board)?)
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
