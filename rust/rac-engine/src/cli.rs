//! CLI argv surface (PORT-CONTRACT.d/01).
//!
//! Parity scope: exit codes, stdout bytes, and the final
//! `<prog>: error: <msg>` stderr line. Usage/help BODY text is out of scope
//! (decision 9) — stdout stays byte-identical (empty on errors).

use crate::commands::{
    cmd_coverage, cmd_decisions_for, cmd_diff, cmd_export, cmd_find, cmd_improve, cmd_inspect,
    cmd_portfolio, cmd_relationships, cmd_resolve, cmd_retrieve, cmd_review, cmd_schema,
    cmd_stats, cmd_templates, cmd_validate, CoverageArgs, DecisionsForArgs, DiffArgs, ExportArgs,
    FindArgs, ImproveArgs, InspectArgs, PortfolioArgs, RelationshipsArgs, ResolveArgs,
    RetrieveArgs, ReviewArgs, SchemaArgs, StatsArgs, TemplatesArgs, ValidateArgs,
};
use crate::output::rac_version;

/// Root subcommand table, in argparse declaration order (the order the
/// `invalid choice` message quotes).
const SUBCOMMANDS: [&str; 33] = [
    "validate",
    "diff",
    "stats",
    "ingest",
    "inspect",
    "improve",
    "schema",
    "relationships",
    "rename",
    "review",
    "doctor",
    "coverage",
    "gate",
    "watchkeeper",
    "portfolio",
    "index",
    "export",
    "explorer",
    "mcp",
    "mcp-stats",
    "telemetry",
    "usage",
    "new",
    "templates",
    "init",
    "quickstart",
    "resolve",
    "find",
    "decisions-for",
    "eval",
    "migrate",
    "skill",
    "hook",
];

fn version_line() -> String {
    format!("rac {}", rac_version())
}

fn print_stdout(text: &str) {
    use std::io::Write;
    let mut out = std::io::stdout().lock();
    let _ = out.write_all(text.as_bytes());
    let _ = out.write_all(b"\n");
    let _ = out.flush();
}

/// argparse-style error: usage to stderr, final `<prog>: error: <msg>` line,
/// exit 2. The usage body is out of parity scope; only the last line is
/// contract-shaped.
fn argparse_error(prog: &str, message: &str) -> u8 {
    eprintln!("usage: {prog} ...");
    eprintln!("{prog}: error: {message}");
    2
}

/// Leftover-token rejection; argparse reports these against the root prog
/// (`rac`), not the subcommand.
fn unrecognized(extras: &[String]) -> u8 {
    argparse_error(
        "rac",
        &format!("unrecognized arguments: {}", extras.join(" ")),
    )
}

fn invalid_choice_message(token: &str) -> String {
    let choices = SUBCOMMANDS
        .iter()
        .map(|s| format!("'{s}'"))
        .collect::<Vec<_>>()
        .join(", ");
    format!("argument command: invalid choice: '{token}' (choose from {choices})")
}

pub fn run(args: &[String]) -> u8 {
    let mut it = args.iter();
    let first = match it.next() {
        None => return argparse_error("rac", "the following arguments are required: command"),
        Some(a) if a == "--version" => {
            print_stdout(&version_line());
            return 0;
        }
        Some(a) if a == "-h" || a == "--help" => {
            // Help body is out of parity scope; emit a stub to stdout.
            print_stdout("usage: rac [-h] [--version] <command> ...");
            return 0;
        }
        Some(a) => a,
    };

    if first.starts_with('-') {
        return argparse_error("rac", &format!("unrecognized arguments: {first}"));
    }
    // `retrieve` (ADR-113, oracle-next 0.1.dev55+gf2091befd) dispatches but is
    // deliberately NOT in SUBCOMMANDS: the mainline oracle's `invalid choice`
    // message does not list it, and that message's bytes are pinned by the
    // mainline parity suite (case `err-unknown-subcommand`).
    if first != "retrieve" && !SUBCOMMANDS.contains(&first.as_str()) {
        return argparse_error("rac", &invalid_choice_message(first));
    }

    let rest: Vec<&String> = it.collect();

    // `--version` short-circuits on every subcommand (version_parent).
    if rest.iter().any(|a| a.as_str() == "--version") {
        print_stdout(&version_line());
        return 0;
    }
    if rest.iter().any(|a| a.as_str() == "-h" || a.as_str() == "--help") {
        print_stdout(&format!("usage: rac {first} ..."));
        return 0;
    }

    match first.as_str() {
        "validate" => run_validate(&rest),
        "diff" => run_diff(&rest),
        "inspect" => run_inspect(&rest),
        "improve" => run_improve(&rest),
        "relationships" => run_relationships(&rest),
        "stats" => run_stats(&rest),
        "schema" => run_schema(&rest),
        "templates" => run_templates(&rest),
        "resolve" => run_resolve(&rest),
        "find" => run_find(&rest),
        "retrieve" => run_retrieve(&rest),
        "review" => run_review(&rest),
        "export" => run_export(&rest),
        "portfolio" => run_portfolio(&rest),
        "coverage" => run_coverage(&rest),
        "decisions-for" => run_decisions_for(&rest),
        other => {
            eprintln!("rac-rs: subcommand '{other}' is not yet implemented");
            2
        }
    }
}

struct FlagError(u8);

/// Track the last-seen member of an argparse mutually-exclusive group and
/// error like argparse does on a conflict. Returns the exit code on conflict.
fn mutex_check(prog: &str, new_flag: &str, other_flag: &str, other_set: bool) -> Option<u8> {
    if other_set {
        Some(argparse_error(
            prog,
            &format!("argument {new_flag}: not allowed with argument {other_flag}"),
        ))
    } else {
        None
    }
}

/// Consume a single-argument option's value: the inline `--flag=VALUE` form,
/// or the next token when it reads as a value (bare `-` counts; other
/// `-`-leading tokens do not). A missing value errors immediately at this
/// argv position with `argument <flag>: expected one argument`.
fn take_opt_value(
    prog: &str,
    flag: &str,
    arg: &str,
    rest: &[&String],
    i: &mut usize,
) -> Result<String, u8> {
    if let Some(inline) = arg.strip_prefix(flag).and_then(|r| r.strip_prefix('=')) {
        return Ok(inline.to_string());
    }
    *i += 1;
    match rest.get(*i) {
        Some(v) if !v.starts_with('-') || v.as_str() == "-" => Ok(v.to_string()),
        _ => Err(argparse_error(
            prog,
            &format!("argument {flag}: expected one argument"),
        )),
    }
}

fn run_validate(rest: &[&String]) -> u8 {
    let prog = "rac validate";
    let mut file: Option<String> = None;
    let mut json = false;
    let mut sarif = false;
    let mut top_level = false;
    let mut corpus: Option<String> = None;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    let mut i = 0;
    while i < rest.len() {
        let arg = rest[i].as_str();
        if positional_only || arg == "-" || !arg.starts_with('-') {
            if file.is_none() {
                file = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            i += 1;
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => {
                if let Some(code) = mutex_check(prog, "--json", "--sarif", sarif) {
                    return code;
                }
                json = true;
            }
            "--sarif" => {
                if let Some(code) = mutex_check(prog, "--sarif", "--json", json) {
                    return code;
                }
                sarif = true;
            }
            "--top-level" => top_level = true,
            "--recursive" => {} // affirmation of the default
            "--cache" | "--no-cache" | "--verify" => {} // output-neutral (§6)
            other if other == "--corpus" || other.starts_with("--corpus=") => {
                match take_opt_value(prog, "--corpus", other, rest, &mut i) {
                    Ok(v) => corpus = Some(v),
                    Err(code) => return code,
                }
            }
            other => extras.push(other.to_string()),
        }
        i += 1;
    }

    let Some(file) = file else {
        return argparse_error(prog, "the following arguments are required: file");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_validate(&ValidateArgs {
        file,
        json,
        sarif,
        top_level,
        corpus,
    }) as u8
}

fn run_diff(rest: &[&String]) -> u8 {
    let prog = "rac diff";
    let mut old: Option<String> = None;
    let mut new: Option<String> = None;
    let mut json = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || arg == "-" || !arg.starts_with('-') {
            if old.is_none() {
                old = Some(arg.to_string());
            } else if new.is_none() {
                new = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            other => extras.push(other.to_string()),
        }
    }

    // argparse reports every still-missing required positional at once:
    // neither given -> "old, new"; only `old` given -> "new".
    let (Some(old), Some(new)) = (old.clone(), new) else {
        let missing = if old.is_none() { "old, new" } else { "new" };
        return argparse_error(
            prog,
            &format!("the following arguments are required: {missing}"),
        );
    };
    if !extras.is_empty() {
        // Leftover positionals surface as the TOP-LEVEL parser's error.
        return unrecognized(&extras);
    }

    cmd_diff(&DiffArgs { old, new, json }) as u8
}

fn run_inspect(rest: &[&String]) -> u8 {
    let prog = "rac inspect";
    let mut file: Option<String> = None;
    let mut verbose = false;
    let mut top_level = false;
    let mut json = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || arg == "-" || !arg.starts_with('-') {
            if file.is_none() {
                file = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--verbose" => verbose = true,
            "--top-level" => top_level = true,
            "--recursive" => {} // affirmation of the default
            "--json" => json = true,
            other => extras.push(other.to_string()),
        }
    }

    let Some(file) = file else {
        return argparse_error(prog, "the following arguments are required: file");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_inspect(&InspectArgs {
        file,
        verbose,
        top_level,
        json,
    }) as u8
}

fn run_improve(rest: &[&String]) -> u8 {
    let prog = "rac improve";
    let mut file: Option<String> = None;
    let mut json = false;
    let mut template = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || arg == "-" || !arg.starts_with('-') {
            if file.is_none() {
                file = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            // `--json | --template` is a local mutually-exclusive group
            // (improve does NOT inherit json_parent).
            "--json" => {
                if let Some(code) = mutex_check(prog, "--json", "--template", template) {
                    return code;
                }
                json = true;
            }
            "--template" => {
                if let Some(code) = mutex_check(prog, "--template", "--json", json) {
                    return code;
                }
                template = true;
            }
            other => extras.push(other.to_string()),
        }
    }

    let Some(file) = file else {
        return argparse_error(prog, "the following arguments are required: file");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_improve(&ImproveArgs {
        file,
        json,
        template,
    }) as u8
}

fn run_relationships(rest: &[&String]) -> u8 {
    let prog = "rac relationships";
    let mut path: Option<String> = None;
    let mut validate = false;
    let mut sarif = false;
    let mut json = false;
    let mut top_level = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || !arg.starts_with('-') {
            if path.is_none() {
                path = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--validate" => validate = true,
            "--sarif" => sarif = true,
            "--json" => json = true,
            "--top-level" => top_level = true,
            "--recursive" => {}
            other => extras.push(other.to_string()),
        }
    }

    let Some(path) = path else {
        return argparse_error(prog, "the following arguments are required: path");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_relationships(&RelationshipsArgs {
        path,
        validate,
        sarif,
        json,
        top_level,
    }) as u8
}

fn run_stats(rest: &[&String]) -> u8 {
    let prog = "rac stats";
    let mut directory: Option<String> = None;
    let mut json = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || !arg.starts_with('-') {
            if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            other => extras.push(other.to_string()),
        }
    }

    let Some(directory) = directory else {
        return argparse_error(prog, "the following arguments are required: directory");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_stats(&StatsArgs { directory, json }) as u8
}

fn run_portfolio(rest: &[&String]) -> u8 {
    let prog = "rac portfolio";
    let mut directory: Option<String> = None;
    let mut json = false;
    let mut top_level = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || arg == "-" || !arg.starts_with('-') {
            if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            "--top-level" => top_level = true,
            "--recursive" => {} // affirmation of the default
            other => extras.push(other.to_string()),
        }
    }

    // `directory` is REQUIRED here, unlike the sibling index/export parsers.
    let Some(directory) = directory else {
        return argparse_error(prog, "the following arguments are required: directory");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_portfolio(&PortfolioArgs {
        directory,
        json,
        top_level,
    }) as u8
}

fn run_coverage(rest: &[&String]) -> u8 {
    // Optional positional (default '.'); json_parent only — an unknown flag
    // (e.g. --top-level) bubbles to the TOP-LEVEL parser's error.
    let mut directory: Option<String> = None;
    let mut json = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || arg == "-" || !arg.starts_with('-') {
            if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            other => extras.push(other.to_string()),
        }
    }

    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_coverage(&CoverageArgs {
        directory: directory.unwrap_or_else(|| ".".to_string()),
        json,
    }) as u8
}

fn run_decisions_for(rest: &[&String]) -> u8 {
    let prog = "rac decisions-for";
    let mut path: Option<String> = None;
    let mut directory: Option<String> = None;
    let mut json = false;
    let mut top_level = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || arg == "-" || !arg.starts_with('-') {
            if path.is_none() {
                path = Some(arg.to_string());
            } else if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            "--top-level" => top_level = true,
            "--recursive" => {} // affirmation of the default
            other => extras.push(other.to_string()),
        }
    }

    let Some(path) = path else {
        return argparse_error(prog, "the following arguments are required: path");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_decisions_for(&DecisionsForArgs {
        path,
        directory: directory.unwrap_or_else(|| ".".to_string()),
        json,
        top_level,
    }) as u8
}

fn run_resolve(rest: &[&String]) -> u8 {
    let prog = "rac resolve";
    let mut id: Option<String> = None;
    let mut directory: Option<String> = None;
    let mut json = false;
    let mut top_level = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || !arg.starts_with('-') {
            if id.is_none() {
                id = Some(arg.to_string());
            } else if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            "--top-level" => top_level = true,
            "--recursive" => {} // affirmation of the default
            other => extras.push(other.to_string()),
        }
    }

    let Some(id) = id else {
        return argparse_error(prog, "the following arguments are required: id");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_resolve(&ResolveArgs {
        id,
        directory: directory.unwrap_or_else(|| ".".to_string()),
        json,
        top_level,
    }) as u8
}

fn run_find(rest: &[&String]) -> u8 {
    let prog = "rac find";
    let mut query: Option<String> = None;
    let mut directory: Option<String> = None;
    let mut artifact_type: Option<String> = None;
    let mut decisions = false;
    let mut tags: Vec<String> = Vec::new();
    let mut json = false;
    let mut explain = false;
    let mut top_level = false;
    let mut live = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    let mut i = 0;
    while i < rest.len() {
        let arg = rest[i].as_str();
        if positional_only || !arg.starts_with('-') {
            if query.is_none() {
                query = Some(arg.to_string());
            } else if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            i += 1;
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            "--explain" => explain = true,
            "--top-level" => top_level = true,
            "--live" => live = true, // the live-only facet (ADR-113)
            "--recursive" => {}                        // affirmation of the default
            "--cache" | "--no-cache" | "--verify" => {} // output-neutral (ADR-112)
            "--decisions" => {
                // Mutually exclusive with --type (argparse group).
                if let Some(code) =
                    mutex_check(prog, "--decisions", "--type", artifact_type.is_some())
                {
                    return code;
                }
                decisions = true;
            }
            other if other == "--type" || other.starts_with("--type=") => {
                if let Some(code) = mutex_check(prog, "--type", "--decisions", decisions) {
                    return code;
                }
                match take_opt_value(prog, "--type", other, rest, &mut i) {
                    Ok(v) => artifact_type = Some(v),
                    Err(code) => return code,
                }
            }
            other if other == "--tag" || other.starts_with("--tag=") => {
                match take_opt_value(prog, "--tag", other, rest, &mut i) {
                    Ok(v) => tags.push(v),
                    Err(code) => return code,
                }
            }
            other => extras.push(other.to_string()),
        }
        i += 1;
    }

    let Some(query) = query else {
        return argparse_error(prog, "the following arguments are required: query");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_find(&FindArgs {
        query,
        directory: directory.unwrap_or_else(|| ".".to_string()),
        artifact_type,
        decisions,
        tags,
        json,
        explain,
        top_level,
        live,
    }) as u8
}

/// `int(value)` for argparse `type=int`: Python-style strip, optional sign,
/// ASCII digits with single interior underscores. (Non-ASCII digit forms are
/// out of scope for the parity surface.)
fn py_parse_int(value: &str) -> Option<i64> {
    let text = crate::pycompat::py_strip(value);
    let (neg, digits) = match text.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, text.strip_prefix('+').unwrap_or(text)),
    };
    if digits.is_empty() {
        return None;
    }
    let bytes = digits.as_bytes();
    if bytes[0] == b'_' || bytes[bytes.len() - 1] == b'_' {
        return None;
    }
    let mut out: i64 = 0;
    let mut prev_underscore = false;
    for &b in bytes {
        if b == b'_' {
            if prev_underscore {
                return None;
            }
            prev_underscore = true;
            continue;
        }
        prev_underscore = false;
        if !b.is_ascii_digit() {
            return None;
        }
        out = out
            .saturating_mul(10)
            .saturating_add(i64::from(b - b'0'));
    }
    Some(if neg { -out } else { out })
}

fn run_retrieve(rest: &[&String]) -> u8 {
    let prog = "rac retrieve";
    let mut task: Option<String> = None;
    let mut directory: Option<String> = None;
    let mut scope: Option<String> = None;
    let mut top_k: i64 = 5;
    let mut budget: i64 = 10_000;
    let mut live = false;
    let mut all = false;
    let mut json = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    // One int-valued flag consumer: argparse `type=int` + its error line.
    enum IntErr {
        Missing,
        Invalid(String),
    }
    let parse_int_flag = |raw: Option<&&String>| -> Result<i64, IntErr> {
        match raw {
            Some(v)
                if !v.starts_with('-')
                    || v.as_str() == "-"
                    || looks_like_negative_number(v) =>
            {
                py_parse_int(v).ok_or_else(|| IntErr::Invalid(v.to_string()))
            }
            _ => Err(IntErr::Missing),
        }
    };
    let int_flag_error = |flag: &str, err: IntErr| -> u8 {
        match err {
            IntErr::Missing => {
                argparse_error(prog, &format!("argument {flag}: expected one argument"))
            }
            IntErr::Invalid(v) => argparse_error(
                prog,
                &format!("argument {flag}: invalid int value: '{v}'"),
            ),
        }
    };

    let mut i = 0;
    while i < rest.len() {
        let arg = rest[i].as_str();
        if positional_only || !arg.starts_with('-') || arg == "-" || looks_like_negative_number(arg)
        {
            if task.is_none() {
                task = Some(arg.to_string());
            } else if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            i += 1;
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            "--live" => {
                if let Some(code) = mutex_check(prog, "--live", "--all", all) {
                    return code;
                }
                live = true;
            }
            "--all" => {
                if let Some(code) = mutex_check(prog, "--all", "--live", live) {
                    return code;
                }
                all = true;
            }
            other if other == "--scope" || other.starts_with("--scope=") => {
                match take_opt_value(prog, "--scope", other, rest, &mut i) {
                    Ok(v) => scope = Some(v),
                    Err(code) => return code,
                }
            }
            "--top-k" => {
                i += 1;
                match parse_int_flag(rest.get(i)) {
                    Ok(v) => top_k = v,
                    Err(e) => return int_flag_error("--top-k", e),
                }
            }
            other if other.starts_with("--top-k=") => {
                let v = &other["--top-k=".len()..];
                match py_parse_int(v) {
                    Some(parsed) => top_k = parsed,
                    None => return int_flag_error("--top-k", IntErr::Invalid(v.to_string())),
                }
            }
            "--budget" => {
                i += 1;
                match parse_int_flag(rest.get(i)) {
                    Ok(v) => budget = v,
                    Err(e) => return int_flag_error("--budget", e),
                }
            }
            other if other.starts_with("--budget=") => {
                let v = &other["--budget=".len()..];
                match py_parse_int(v) {
                    Some(parsed) => budget = parsed,
                    None => return int_flag_error("--budget", IntErr::Invalid(v.to_string())),
                }
            }
            other => extras.push(other.to_string()),
        }
        i += 1;
    }

    let Some(task) = task else {
        return argparse_error(prog, "the following arguments are required: task");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_retrieve(&RetrieveArgs {
        task,
        directory: directory.unwrap_or_else(|| ".".to_string()),
        scope,
        top_k,
        budget,
        all,
        json,
    }) as u8
}

/// argparse treats a token matching `^-\d+$` / `^-\d*\.\d+$` as a value, not an
/// option (the parser has no option strings that look like negative numbers).
fn looks_like_negative_number(s: &str) -> bool {
    let Some(rest) = s.strip_prefix('-') else {
        return false;
    };
    if rest.is_empty() {
        return false;
    }
    let mut seen_dot = false;
    let mut seen_digit = false;
    for ch in rest.chars() {
        if ch == '.' {
            if seen_dot {
                return false;
            }
            seen_dot = true;
        } else if ch.is_ascii_digit() {
            seen_digit = true;
        } else {
            return false;
        }
    }
    seen_digit
}

fn run_review(rest: &[&String]) -> u8 {
    let prog = "rac review";
    let mut directory: Option<String> = None;
    let mut json = false;
    let mut sarif = false;
    let mut top_level = false;
    let mut stale_after: Option<i64> = None;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    let mut i = 0;
    while i < rest.len() {
        let arg = rest[i].as_str();
        if positional_only || !arg.starts_with('-') || arg == "-" {
            if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            i += 1;
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            "--sarif" => sarif = true,
            "--top-level" => top_level = true,
            "--recursive" => {}
            "--stale-after" => {
                // nargs="?" const=14: consume the next token only if it is a
                // value (not another option), including a negative number.
                let consume = match rest.get(i + 1) {
                    Some(v) => !v.starts_with('-') || looks_like_negative_number(v),
                    None => false,
                };
                if consume {
                    i += 1;
                    let raw = rest[i].as_str();
                    match raw.trim().parse::<i64>() {
                        Ok(v) => stale_after = Some(v),
                        Err(_) => {
                            return argparse_error(
                                prog,
                                &format!("argument --stale-after: invalid int value: '{raw}'"),
                            )
                        }
                    }
                } else {
                    stale_after = Some(14);
                }
            }
            other if other.starts_with("--stale-after=") => {
                let raw = &other["--stale-after=".len()..];
                match raw.trim().parse::<i64>() {
                    Ok(v) => stale_after = Some(v),
                    Err(_) => {
                        return argparse_error(
                            prog,
                            &format!("argument --stale-after: invalid int value: '{raw}'"),
                        )
                    }
                }
            }
            other => extras.push(other.to_string()),
        }
        i += 1;
    }

    let Some(directory) = directory else {
        return argparse_error(prog, "the following arguments are required: directory");
    };
    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_review(&ReviewArgs {
        directory,
        json,
        sarif,
        top_level,
        stale_after,
    }) as u8
}

fn run_export(rest: &[&String]) -> u8 {
    let prog = "rac export";
    let mut directory: Option<String> = None;
    let mut json = false;
    let mut html = false;
    let mut okf = false;
    let mut documents = false;
    let mut graph = false;
    let mut agent_rules = false;
    let mut check = false;
    let mut client: Vec<String> = Vec::new();
    let mut out: Option<String> = None;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    // Track the last write-mode flag seen for argparse mutex diagnostics.
    let mut last_mode: Option<&'static str> = None;
    let set_mode = |flag: &'static str,
                        slot: &mut bool,
                        last_mode: &mut Option<&'static str>|
     -> Result<(), FlagError> {
        if let Some(prev) = *last_mode {
            if prev != flag {
                return Err(FlagError(argparse_error(
                    prog,
                    &format!("argument {flag}: not allowed with argument {prev}"),
                )));
            }
        }
        *slot = true;
        *last_mode = Some(flag);
        Ok(())
    };

    let mut i = 0;
    while i < rest.len() {
        let arg = rest[i].as_str();
        if positional_only || !arg.starts_with('-') || arg == "-" {
            if directory.is_none() {
                directory = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            i += 1;
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            "--html" => {
                if let Err(FlagError(c)) = set_mode("--html", &mut html, &mut last_mode) {
                    return c;
                }
            }
            "--okf" => {
                if let Err(FlagError(c)) = set_mode("--okf", &mut okf, &mut last_mode) {
                    return c;
                }
            }
            "--documents" => {
                if let Err(FlagError(c)) = set_mode("--documents", &mut documents, &mut last_mode) {
                    return c;
                }
            }
            "--graph" => {
                if let Err(FlagError(c)) = set_mode("--graph", &mut graph, &mut last_mode) {
                    return c;
                }
            }
            "--agent-rules" => {
                if let Err(FlagError(c)) =
                    set_mode("--agent-rules", &mut agent_rules, &mut last_mode)
                {
                    return c;
                }
            }
            "--check" => check = true,
            "--client" => {
                i += 1;
                match rest.get(i) {
                    Some(v) if is_client_choice(v) => client.push(v.to_string()),
                    Some(v) if !v.starts_with('-') => {
                        return argparse_error(
                            prog,
                            &format!(
                                "argument --client: invalid choice: '{v}' (choose from 'claude', 'agents', 'cursor', 'copilot')"
                            ),
                        )
                    }
                    _ => return argparse_error(prog, "argument --client: expected one argument"),
                }
            }
            other if other.starts_with("--client=") => {
                let v = &other["--client=".len()..];
                if is_client_choice(v) {
                    client.push(v.to_string());
                } else {
                    return argparse_error(
                        prog,
                        &format!(
                            "argument --client: invalid choice: '{v}' (choose from 'claude', 'agents', 'cursor', 'copilot')"
                        ),
                    );
                }
            }
            other if other == "--out" || other.starts_with("--out=") => {
                match take_opt_value(prog, "--out", other, rest, &mut i) {
                    Ok(v) => out = Some(v),
                    Err(code) => return code,
                }
            }
            other => extras.push(other.to_string()),
        }
        i += 1;
    }

    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_export(&ExportArgs {
        directory: directory.unwrap_or_else(|| ".".to_string()),
        json,
        graph,
        documents,
        html,
        okf,
        agent_rules,
        check,
        client,
        out,
    }) as u8
}

fn is_client_choice(v: &str) -> bool {
    matches!(v, "claude" | "agents" | "cursor" | "copilot")
}

fn run_schema(rest: &[&String]) -> u8 {
    let prog = "rac schema";
    let mut schema: Option<String> = None;
    let mut list = false;
    let mut json = false;
    let mut template = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || !arg.starts_with('-') {
            if schema.is_none() {
                schema = Some(arg.to_string());
            } else {
                extras.push(arg.to_string());
            }
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--list" => list = true,
            "--json" => {
                if let Some(code) = mutex_check(prog, "--json", "--template", template) {
                    return code;
                }
                json = true;
            }
            "--template" => {
                if let Some(code) = mutex_check(prog, "--template", "--json", json) {
                    return code;
                }
                template = true;
            }
            other => extras.push(other.to_string()),
        }
    }

    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_schema(&SchemaArgs {
        schema,
        list,
        json,
        template,
    }) as u8
}

fn run_templates(rest: &[&String]) -> u8 {
    let mut json = false;
    let mut extras: Vec<String> = Vec::new();
    let mut positional_only = false;

    for arg in rest {
        let arg = arg.as_str();
        if positional_only || !arg.starts_with('-') {
            extras.push(arg.to_string());
            continue;
        }
        match arg {
            "--" => positional_only = true,
            "--json" => json = true,
            other => extras.push(other.to_string()),
        }
    }

    if !extras.is_empty() {
        return unrecognized(&extras);
    }

    cmd_templates(&TemplatesArgs { json }) as u8
}
