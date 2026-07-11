//! CLI argv surface (PORT-CONTRACT.d/01).
//!
//! Parity scope: exit codes, stdout bytes, and the final
//! `<prog>: error: <msg>` stderr line. Usage/help BODY text is out of scope
//! (decision 9) — stdout stays byte-identical (empty on errors).
//!
//! Wired for real: `validate`, `relationships` (--validate arm), and
//! `--version` (root + every subcommand). Every other subcommand is a
//! clearly-marked unimplemented stub (stderr, exit 2).

use crate::commands::{
    cmd_find, cmd_relationships, cmd_resolve, cmd_schema, cmd_stats, cmd_templates, cmd_validate,
    FindArgs, RelationshipsArgs, ResolveArgs, SchemaArgs, StatsArgs, TemplatesArgs, ValidateArgs,
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
    let first = loop {
        match it.next() {
            None => {
                return argparse_error("rac", "the following arguments are required: command")
            }
            Some(a) if a == "--version" => {
                print_stdout(&version_line());
                return 0;
            }
            Some(a) if a == "-h" || a == "--help" => {
                // Help body is out of parity scope; emit a stub to stdout.
                print_stdout("usage: rac [-h] [--version] <command> ...");
                return 0;
            }
            Some(a) => break a,
        }
    };

    if first.starts_with('-') {
        return argparse_error("rac", &format!("unrecognized arguments: {first}"));
    }
    if !SUBCOMMANDS.contains(&first.as_str()) {
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
        "relationships" => run_relationships(&rest),
        "stats" => run_stats(&rest),
        "schema" => run_schema(&rest),
        "templates" => run_templates(&rest),
        "resolve" => run_resolve(&rest),
        "find" => run_find(&rest),
        other => {
            // UNIMPLEMENTED STUB — no parity cases run these in this phase.
            eprintln!("rac-rs: subcommand '{other}' is not yet implemented");
            2
        }
    }
}

struct FlagError(u8);

/// Track the last-seen member of an argparse mutually-exclusive group and
/// error like argparse does on a conflict.
fn mutex_check(
    prog: &str,
    new_flag: &str,
    other_flag: &str,
    other_set: bool,
) -> Result<(), FlagError> {
    if other_set {
        Err(FlagError(argparse_error(
            prog,
            &format!("argument {new_flag}: not allowed with argument {other_flag}"),
        )))
    } else {
        Ok(())
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
                if let Err(FlagError(code)) = mutex_check(prog, "--json", "--sarif", sarif) {
                    return code;
                }
                json = true;
            }
            "--sarif" => {
                if let Err(FlagError(code)) = mutex_check(prog, "--sarif", "--json", json) {
                    return code;
                }
                sarif = true;
            }
            "--top-level" => top_level = true,
            "--recursive" => {} // affirmation of the default
            "--cache" | "--no-cache" | "--verify" => {} // output-neutral (§6)
            "--corpus" => {
                i += 1;
                match rest.get(i) {
                    Some(v) if !v.starts_with('-') || v.as_str() == "-" => {
                        corpus = Some(v.to_string());
                    }
                    _ => {
                        return argparse_error(prog, "argument --corpus: expected one argument")
                    }
                }
            }
            other if other.starts_with("--corpus=") => {
                corpus = Some(other["--corpus=".len()..].to_string());
            }
            other => extras.push(other.to_string()),
        }
        i += 1;
    }

    let Some(file) = file else {
        return argparse_error(prog, "the following arguments are required: file");
    };
    if !extras.is_empty() {
        return argparse_error(
            "rac",
            &format!("unrecognized arguments: {}", extras.join(" ")),
        );
    }

    cmd_validate(&ValidateArgs {
        file,
        json,
        sarif,
        top_level,
        corpus,
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
        return argparse_error(
            "rac",
            &format!("unrecognized arguments: {}", extras.join(" ")),
        );
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
        return argparse_error(
            "rac",
            &format!("unrecognized arguments: {}", extras.join(" ")),
        );
    }

    cmd_stats(&StatsArgs { directory, json }) as u8
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
        return argparse_error(
            "rac",
            &format!("unrecognized arguments: {}", extras.join(" ")),
        );
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
            "--recursive" => {}                        // affirmation of the default
            "--cache" | "--no-cache" | "--verify" => {} // output-neutral (ADR-112)
            "--decisions" => {
                // Mutually exclusive with --type (argparse group).
                if let Err(FlagError(code)) =
                    mutex_check(prog, "--decisions", "--type", artifact_type.is_some())
                {
                    return code;
                }
                decisions = true;
            }
            "--type" => {
                if let Err(FlagError(code)) = mutex_check(prog, "--type", "--decisions", decisions)
                {
                    return code;
                }
                i += 1;
                match rest.get(i) {
                    Some(v) if !v.starts_with('-') || v.as_str() == "-" => {
                        artifact_type = Some(v.to_string());
                    }
                    _ => return argparse_error(prog, "argument --type: expected one argument"),
                }
            }
            other if other.starts_with("--type=") => {
                if let Err(FlagError(code)) = mutex_check(prog, "--type", "--decisions", decisions)
                {
                    return code;
                }
                artifact_type = Some(other["--type=".len()..].to_string());
            }
            "--tag" => {
                i += 1;
                match rest.get(i) {
                    Some(v) if !v.starts_with('-') || v.as_str() == "-" => {
                        tags.push(v.to_string());
                    }
                    _ => return argparse_error(prog, "argument --tag: expected one argument"),
                }
            }
            other if other.starts_with("--tag=") => {
                tags.push(other["--tag=".len()..].to_string());
            }
            other => extras.push(other.to_string()),
        }
        i += 1;
    }

    let Some(query) = query else {
        return argparse_error(prog, "the following arguments are required: query");
    };
    if !extras.is_empty() {
        return argparse_error(
            "rac",
            &format!("unrecognized arguments: {}", extras.join(" ")),
        );
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
    }) as u8
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
                if let Err(FlagError(code)) = mutex_check(prog, "--json", "--template", template) {
                    return code;
                }
                json = true;
            }
            "--template" => {
                if let Err(FlagError(code)) = mutex_check(prog, "--template", "--json", json) {
                    return code;
                }
                template = true;
            }
            other => extras.push(other.to_string()),
        }
    }

    if !extras.is_empty() {
        return argparse_error(
            "rac",
            &format!("unrecognized arguments: {}", extras.join(" ")),
        );
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
        return argparse_error(
            "rac",
            &format!("unrecognized arguments: {}", extras.join(" ")),
        );
    }

    cmd_templates(&TemplatesArgs { json }) as u8
}
