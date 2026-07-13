//! rac-mcp — the Guide MCP server over stdio, a Rust port of `rac mcp`
//! (PORT-CONTRACT.d/10-mcp-surface.md is the binding wire contract).
//!
//! Framing: newline-delimited JSON-RPC, UTF-8, non-ASCII raw, no
//! Content-Length headers (§1). Envelopes are compact (§2); the inner tool
//! payload is `json.dumps(..., ensure_ascii=False)` with DEFAULT separators
//! (spaces after `:` and `,`). Six tools (the ORACLE-NEXT surface, a strict
//! superset of PRIMARY's five, §10). Stateless re-read per call (ADR-032).

mod args;
mod graph;
mod provenance;
mod sidecar;
mod tools;

use args::{Arg, Kind, Param};
use rac_engine::budget;
use serde_json::{json, Map, Value};
use std::io::{BufRead, Write};

/// Pinned `serverInfo.version` (contract landmine, §3): the oracle emits the
/// bundled **Python `mcp` SDK package version** (`mcp==1.28.1`), not the rac
/// product version. Byte parity requires the same literal.
const SDK_VERSION: &str = "1.28.1";
const SERVER_NAME: &str = "lore";

/// Protocol versions the pinned SDK negotiates; anything else falls back to
/// the latest. The harness pins its requests to 2025-06-18.
const SUPPORTED_PROTOCOL_VERSIONS: [&str; 3] = ["2024-11-05", "2025-03-26", "2025-06-18"];
const LATEST_PROTOCOL_VERSION: &str = "2025-06-18";

/// The pinned `tools/list` result — the captured ORACLE-NEXT bytes, embedded
/// verbatim (schemas, descriptions, pydantic-shaped titles incl. the
/// function-name leaks `find_decisions_toolArguments` /
/// `retrieve_grounding_toolArguments`; §4).
const TOOLS_LIST_RESULT: &str = include_str!("tools_list_result.json");

/// The SDK's logging notification for an unparseable input line (§1) —
/// note the field order: method, params, jsonrpc.
const PARSE_ERROR_NOTIFICATION: &str = "{\"method\":\"notifications/message\",\"params\":{\"level\":\"error\",\"logger\":\"mcp.server.exception_handler\",\"data\":\"Internal Server Error\"},\"jsonrpc\":\"2.0\"}";

fn usage_error(msg: &str) -> ! {
    eprintln!("rac mcp: error: {msg}");
    std::process::exit(2);
}

fn main() {
    let mut argv = std::env::args().skip(1);
    let mut root = ".".to_string();
    let mut cache = true;
    while let Some(a) = argv.next() {
        match a.as_str() {
            "--root" => match argv.next() {
                Some(v) => root = v,
                None => usage_error("--root requires a value"),
            },
            // Cache flags are real since INDEX-PLAN B6 and remain
            // output-neutral (ADR-112: cache-on vs cache-off runs are
            // frame-for-frame byte-identical; native warm == cold holds
            // even for the duplicate-token class, PORT-CONTRACT.d/10 §0a).
            "--no-cache" => cache = false,
            "--cache" => cache = true,
            other => usage_error(&format!("unrecognized argument: {other}")),
        }
    }
    if !std::path::Path::new(&root).is_dir() {
        usage_error(&format!("not a directory: {root}"));
    }
    check_corpus(&root);
    // Server-lifetime freshness (ADR-105): one tracker per server keeps the
    // derived read-model current by stat-scan detection (ADR-114: no
    // inotify rung), re-deriving only where files changed.
    let mut tracker = if rac_engine::derived_cache::cache_enabled(cache) {
        Some(rac_engine::freshness::FreshnessTracker::new(
            rac_engine::derived_cache::default_cache_dir(),
            &root,
            None,
        ))
    } else {
        None
    };
    serve(&root, &mut tracker);
}

/// Startup diagnostic (stderr only; declared-normalized in parity, §0).
fn check_corpus(root: &str) {
    let entries = rac_engine::resolve::build_index(root, true);
    if !entries.iter().any(|e| e.artifact_type != "unknown") {
        eprintln!(
            "rac mcp: no RAC artifacts found under '{root}'. Point --root at a \
directory containing RAC Markdown artifacts, or run 'rac init' to initialize \
a new repository. The server is running; get_summary will report the empty state."
        );
    }
}

fn serve(root: &str, tracker: &mut Option<rac_engine::freshness::FreshnessTracker>) {
    let stdin = std::io::stdin();
    let stdout = std::io::stdout();
    let mut out = stdout.lock();
    for line in stdin.lock().lines() {
        let Ok(line) = line else { break };
        if line.trim().is_empty() {
            continue;
        }
        let Ok(message) = serde_json::from_str::<Value>(&line) else {
            writeln!(out, "{PARSE_ERROR_NOTIFICATION}").ok();
            out.flush().ok();
            continue;
        };
        let Some(method) = message.get("method").and_then(Value::as_str) else {
            writeln!(out, "{PARSE_ERROR_NOTIFICATION}").ok();
            out.flush().ok();
            continue;
        };
        let id = message.get("id");
        let Some(id) = id else {
            continue; // notification (e.g. notifications/initialized): no response
        };
        let id_json = serde_json::to_string(id).unwrap_or_else(|_| "null".to_string());
        let frame = match method {
            "initialize" => initialize_frame(&id_json, &message),
            "ping" => format!("{{\"jsonrpc\":\"2.0\",\"id\":{id_json},\"result\":{{}}}}"),
            "tools/list" => {
                format!("{{\"jsonrpc\":\"2.0\",\"id\":{id_json},\"result\":{TOOLS_LIST_RESULT}}}")
            }
            "prompts/list" => {
                format!("{{\"jsonrpc\":\"2.0\",\"id\":{id_json},\"result\":{{\"prompts\":[]}}}}")
            }
            "resources/list" => {
                format!("{{\"jsonrpc\":\"2.0\",\"id\":{id_json},\"result\":{{\"resources\":[]}}}}")
            }
            "tools/call" => tools_call_frame(root, tracker, &id_json, &message),
            _ => format!(
                "{{\"jsonrpc\":\"2.0\",\"id\":{id_json},\"error\":{{\"code\":-32602,\"message\":\"Invalid request parameters\",\"data\":\"\"}}}}"
            ),
        };
        writeln!(out, "{frame}").ok();
        out.flush().ok();
    }
}

fn initialize_frame(id_json: &str, message: &Value) -> String {
    let requested = message
        .pointer("/params/protocolVersion")
        .and_then(Value::as_str)
        .unwrap_or(LATEST_PROTOCOL_VERSION);
    let version = if SUPPORTED_PROTOCOL_VERSIONS.contains(&requested) {
        requested
    } else {
        LATEST_PROTOCOL_VERSION
    };
    format!(
        "{{\"jsonrpc\":\"2.0\",\"id\":{id_json},\"result\":{{\"protocolVersion\":\"{version}\",\
\"capabilities\":{{\"experimental\":{{}},\"prompts\":{{\"listChanged\":false}},\
\"resources\":{{\"subscribe\":false,\"listChanged\":false}},\
\"tools\":{{\"listChanged\":false}}}},\
\"serverInfo\":{{\"name\":\"{SERVER_NAME}\",\"version\":\"{SDK_VERSION}\"}}}}}}"
    )
}

/// Serialize the tools/call result envelope (§5). Success duplicates the
/// payload under `structuredContent.result` (the handlers return `str` and an
/// outputSchema exists — landmine 1); SDK-text errors ride `isError:true`
/// with no `structuredContent`.
fn call_result_frame(id_json: &str, text: &str, is_error: bool) -> String {
    let mut content_item = Map::new();
    content_item.insert("type".to_string(), json!("text"));
    content_item.insert("text".to_string(), json!(text));
    let mut result = Map::new();
    result.insert(
        "content".to_string(),
        Value::Array(vec![Value::Object(content_item)]),
    );
    if !is_error {
        let mut structured = Map::new();
        structured.insert("result".to_string(), json!(text));
        result.insert("structuredContent".to_string(), Value::Object(structured));
    }
    result.insert("isError".to_string(), json!(is_error));
    let result_json = serde_json::to_string(&Value::Object(result)).expect("serializable");
    format!("{{\"jsonrpc\":\"2.0\",\"id\":{id_json},\"result\":{result_json}}}")
}

fn tools_call_frame(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    id_json: &str,
    message: &Value,
) -> String {
    let name = message
        .pointer("/params/name")
        .and_then(Value::as_str)
        .unwrap_or("");
    let empty = json!({});
    let arguments = message.pointer("/params/arguments").unwrap_or(&empty);
    match dispatch(root, tracker, name, arguments) {
        Ok(payload) => call_result_frame(id_json, &payload, false),
        Err(text) => call_result_frame(id_json, &text, true),
    }
}

// Argument accessors over the coerced vector (defaults applied here, matching
// the Python signatures).
fn a_str(args: &[Arg], i: usize, default: &str) -> String {
    match &args[i] {
        Arg::Str(s) => s.clone(),
        _ => default.to_string(),
    }
}
fn a_opt_str(args: &[Arg], i: usize) -> Option<String> {
    match &args[i] {
        Arg::OptStr(v) => v.clone(),
        _ => None,
    }
}
fn a_opt_list_str(args: &[Arg], i: usize) -> Option<Vec<String>> {
    match &args[i] {
        Arg::OptListStr(v) => v.clone(),
        _ => None,
    }
}
fn a_int(args: &[Arg], i: usize, default: i64) -> i64 {
    match &args[i] {
        Arg::Int(v) => *v,
        _ => default,
    }
}
fn a_bool(args: &[Arg], i: usize, default: bool) -> bool {
    match &args[i] {
        Arg::Bool(v) => *v,
        _ => default,
    }
}

fn dispatch(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    name: &str,
    arguments: &Value,
) -> Result<String, String> {
    // ADR-033: the server budget is fixed at construction; the stdio CLI has
    // no flag, so it is always the default.
    let server_budget = budget::DEFAULT_BUDGET;
    // Freshen the read-model once per call (the corpus-change check every
    // tool answer rides, ADR-105); without the tracker every arm re-walks.
    let model = tracker.as_mut().map(|t| t.read_model(false));
    match name {
        "get_artifact" => {
            let params = [
                Param { name: "id", kind: Kind::Str, required: true },
                Param { name: "budget", kind: Kind::Int, required: false },
            ];
            let a = args::validate(name, "get_artifactArguments", &params, arguments)?;
            let effective = tools::effective_budget(server_budget, a_int(&a, 1, 0));
            Ok(sidecar::observe(name, || {
                tools::get_artifact(root, model, &a_str(&a, 0, ""), effective)
            }))
        }
        "search_artifacts" => {
            let params = [
                Param { name: "query", kind: Kind::Str, required: true },
                Param { name: "type", kind: Kind::OptStr, required: false },
                Param { name: "tags", kind: Kind::OptListStr, required: false },
                Param { name: "live_only", kind: Kind::Bool, required: false },
            ];
            let a = args::validate(name, "search_artifactsArguments", &params, arguments)?;
            let query = a_str(&a, 0, "");
            let artifact_type = a_opt_str(&a, 1);
            let tags = a_opt_list_str(&a, 2).unwrap_or_default();
            let live_only = a_bool(&a, 3, false);
            Ok(sidecar::observe(name, || {
                tools::search_artifacts(
                    root,
                    model,
                    &query,
                    artifact_type.as_deref(),
                    &tags,
                    live_only,
                    server_budget,
                )
            }))
        }
        "retrieve_grounding" => {
            let params = [
                Param { name: "task", kind: Kind::Str, required: true },
                Param { name: "scope", kind: Kind::Str, required: false },
                Param { name: "top_k", kind: Kind::Int, required: false },
                Param { name: "budget", kind: Kind::Int, required: false },
                Param { name: "live_only", kind: Kind::Bool, required: false },
            ];
            let a = args::validate(name, "retrieve_grounding_toolArguments", &params, arguments)?;
            let effective = tools::effective_budget(server_budget, a_int(&a, 3, 0));
            Ok(sidecar::observe(name, || {
                tools::retrieve_grounding(
                    root,
                    &a_str(&a, 0, ""),
                    &a_str(&a, 1, ""),
                    a_int(&a, 2, 5),
                    effective,
                    a_bool(&a, 4, true),
                )
            }))
        }
        "find_decisions" => {
            let params = [
                Param { name: "topic", kind: Kind::Str, required: false },
                Param { name: "path", kind: Kind::OptStr, required: false },
            ];
            let a = args::validate(name, "find_decisions_toolArguments", &params, arguments)?;
            let topic = a_str(&a, 0, "");
            let path = a_opt_str(&a, 1);
            Ok(sidecar::observe(name, || {
                tools::find_decisions_tool(root, model, &topic, path.as_deref(), server_budget)
            }))
        }
        "get_related" => {
            let params = [
                Param { name: "id", kind: Kind::Str, required: true },
                Param { name: "depth", kind: Kind::Int, required: false },
            ];
            let a = args::validate(name, "get_relatedArguments", &params, arguments)?;
            Ok(sidecar::observe(name, || {
                tools::get_related(root, model, &a_str(&a, 0, ""), a_int(&a, 1, 1), server_budget)
            }))
        }
        "get_summary" => {
            let params: [Param; 0] = [];
            args::validate(name, "get_summaryArguments", &params, arguments)?;
            Ok(sidecar::observe(name, || {
                tools::get_summary(root, model, server_budget)
            }))
        }
        _ => Err(format!("Unknown tool: {name}")),
    }
}
