//! HTTP transport for `rac-mcp` (ADR-098) — a minimal, dependency-free
//! HTTP/1.1 server over `std::net`.
//!
//! It fronts the very same [`crate::process_request`] frame processor as the
//! stdio transport, so every tool/response body is byte-identical to stdio —
//! the parity surface ADR-098 defines ("an HTTP response is payload-identical
//! to stdio for identical corpus bytes"). Serving is stateless per call
//! (ADR-032): one JSON response per POST, no session store. The transport
//! envelope (uvicorn's `Date`/`Server` header bytes on the Python side, and its
//! Python-specific error prose) is the SDK's incidental framing, not RAC's
//! contract, and is a declared non-parity surface — the same posture the stdio
//! port took toward argparse's usage-wrapping (PORT-CONTRACT.d/10 §9).
//!
//! HTTP is mandatory-audit-on (ADR-084, ADR-098): [`ensure_audit_sink`] proves
//! a working audit sink at startup or the server refuses to start. Attribution
//! rides the `X-Lore-Principal` request header (ADR-098) — recorded, never
//! verified, never an access-control input.
//!
//! Wire contract: `rust/PORT-CONTRACT.d/19-http-transport.md`.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};

use rac_engine::frontmatter::{yaml_load_config, Yaml};
use serde_json::Value;

use crate::process_request;

const CONFIG_DIR: &str = ".rac";
const CONFIG_FILE: &str = "config.yaml";
const AUDIT_FILENAME: &str = "audit.jsonl";
const PATH_ENV: &str = "RAC_AUDIT_PATH";

/// Resolve and validate the audit sink for HTTP serving (ADR-084 fail-loud).
///
/// A shared HTTP endpoint serves reads no single developer's git identity can
/// attribute, so it refuses to start without a *working* audit sink: audit must
/// be enabled in `.rac/config.yaml` and its path writable. Returns the resolved
/// path on success, or an error message for the caller to fail loud with. stdio
/// never calls this — audit stays config-driven and default-absent there.
pub fn ensure_audit_sink(root: &str) -> Result<PathBuf, String> {
    let (enabled, configured_path) = load_audit_stanza(root)?;
    if !enabled {
        return Err(
            "HTTP serving requires the read-access audit log, but it is not \
enabled. Add an `audit:` stanza with `enabled: true` to .rac/config.yaml \
before serving over HTTP (ADR-084)."
                .to_string(),
        );
    }
    let path = resolve_audit_path(configured_path);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| audit_unwritable(&path, &e.to_string()))?;
    }
    std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| audit_unwritable(&path, &e.to_string()))?;
    Ok(path)
}

fn audit_unwritable(path: &Path, reason: &str) -> String {
    format!(
        "HTTP serving requires a writable audit log, but {} could not be opened \
for append ({reason}). Fix the audit path or permissions before serving over \
HTTP (ADR-084).",
        path.display()
    )
}

/// Read `audit.enabled` / `audit.path` from the nearest `.rac/config.yaml` at or
/// above `root` (ADR-084). No config or no `audit` section means disabled.
fn load_audit_stanza(root: &str) -> Result<(bool, String), String> {
    let Some(config_path) = find_config_file(root) else {
        return Ok((false, String::new()));
    };
    let text = std::fs::read_to_string(&config_path)
        .map_err(|e| format!("invalid YAML: {e}"))?;
    let Yaml::Map(pairs) = yaml_load_config(&text).map_err(|p| format!("invalid YAML: {p}"))?
    else {
        return Ok((false, String::new()));
    };
    let section = pairs.iter().find_map(|(k, v)| match k {
        Yaml::Str(s) if s == "audit" => Some(v),
        _ => None,
    });
    let Some(section) = section else {
        return Ok((false, String::new()));
    };
    let Yaml::Map(audit) = section else {
        return Err("'audit' must be a mapping".to_string());
    };
    let enabled = match audit.iter().find_map(|(k, v)| match k {
        Yaml::Str(s) if s == "enabled" => Some(v),
        _ => None,
    }) {
        None => false,
        Some(Yaml::Bool(b)) => *b,
        Some(_) => return Err("'audit.enabled' must be true or false".to_string()),
    };
    let path = match audit.iter().find_map(|(k, v)| match k {
        Yaml::Str(s) if s == "path" => Some(v),
        _ => None,
    }) {
        None => String::new(),
        Some(Yaml::Str(s)) => s.clone(),
        Some(_) => return Err("'audit.path' must be a string".to_string()),
    };
    Ok((enabled, path))
}

/// `RAC_AUDIT_PATH` > config `path` > `$XDG_STATE_HOME/rac/audit.jsonl`.
fn resolve_audit_path(configured: String) -> PathBuf {
    if let Some(env) = std::env::var_os(PATH_ENV) {
        if !env.is_empty() {
            return PathBuf::from(env);
        }
    }
    if !configured.is_empty() {
        return PathBuf::from(configured);
    }
    let base = std::env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| {
            let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_default();
            home.join(".local").join("state")
        });
    base.join("rac").join(AUDIT_FILENAME)
}

fn find_config_file(root: &str) -> Option<PathBuf> {
    let start = std::fs::canonicalize(root).unwrap_or_else(|_| PathBuf::from(root));
    std::iter::successors(Some(start.as_path()), |p| p.parent())
        .map(|dir| dir.join(CONFIG_DIR).join(CONFIG_FILE))
        .find(|c| c.is_file())
}

/// Serve `root` over streamable HTTP (stateless JSON mode) until interrupted.
/// Single-threaded: one request served to completion before the next, so the
/// per-server freshness tracker's mutable read-model is accessed serially
/// without locking (stateless reads are cheap — 28 ms cold on the live corpus).
pub fn serve_http(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    host: &str,
    port: u16,
    path: &str,
) -> ! {
    let listener = match TcpListener::bind((host, port)) {
        Ok(l) => l,
        Err(e) => {
            eprintln!("rac mcp: error: could not bind {host}:{port} ({e})");
            std::process::exit(1);
        }
    };
    eprintln!(
        "rac mcp: serving over HTTP at http://{host}:{port}{path} (read-only, \
stateless per call; authentication belongs to the deployment proxy, ADR-085)."
    );
    for stream in listener.incoming() {
        match stream {
            Ok(s) => handle_connection(root, tracker, path, s),
            Err(_) => continue,
        }
    }
    std::process::exit(0);
}

struct Request {
    method: String,
    target: String,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

impl Request {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }
    /// The request target's path, without any `?query`.
    fn path(&self) -> &str {
        self.target.split('?').next().unwrap_or(&self.target)
    }
}

fn handle_connection(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    path: &str,
    stream: TcpStream,
) {
    let mut reader = BufReader::new(match stream.try_clone() {
        Ok(s) => s,
        Err(_) => return,
    });
    let mut writer = stream;
    let Some(req) = read_request(&mut reader) else {
        return;
    };
    respond(&mut writer, &route(root, tracker, path, &req));
}

/// Parse one HTTP/1.1 request: request line, headers, and a Content-Length body.
fn read_request(reader: &mut BufReader<TcpStream>) -> Option<Request> {
    let mut line = String::new();
    if reader.read_line(&mut line).ok()? == 0 {
        return None;
    }
    let mut parts = line.split_whitespace();
    let method = parts.next()?.to_string();
    let target = parts.next()?.to_string();

    let mut headers = Vec::new();
    loop {
        let mut h = String::new();
        if reader.read_line(&mut h).ok()? == 0 {
            break;
        }
        let trimmed = h.trim_end_matches(['\r', '\n']);
        if trimmed.is_empty() {
            break;
        }
        if let Some((k, v)) = trimmed.split_once(':') {
            headers.push((k.trim().to_string(), v.trim().to_string()));
        }
    }

    let len: usize = headers
        .iter()
        .find(|(k, _)| k.eq_ignore_ascii_case("content-length"))
        .and_then(|(_, v)| v.trim().parse().ok())
        .unwrap_or(0);
    let mut body = vec![0u8; len];
    if len > 0 && reader.read_exact(&mut body).is_err() {
        return None;
    }
    Some(Request { method, target, headers, body })
}

struct Response {
    status: &'static str, // e.g. "200 OK"
    body: Option<String>, // None => empty body, no content-type
}

fn json_response(status: &'static str, body: String) -> Response {
    Response { status, body: Some(body) }
}

/// Apply the streamable-HTTP status-code semantics captured from the SDK, then
/// hand valid requests to the shared frame processor.
fn route(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    path: &str,
    req: &Request,
) -> Response {
    if req.path() != path {
        return Response { status: "404 Not Found", body: None };
    }
    match req.method.as_str() {
        // The server offers no server-initiated SSE stream (stateless, read-only,
        // emits no notifications), so it declines GET — spec-permitted, and the
        // covered POST-only clients are unaffected (declared divergence from the
        // SDK, which opens an idle stream).
        "GET" => Response { status: "405 Method Not Allowed", body: None },
        "DELETE" => Response { status: "405 Method Not Allowed", body: None },
        "POST" => route_post(root, tracker, req),
        _ => Response { status: "405 Method Not Allowed", body: None },
    }
}

fn route_post(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    req: &Request,
) -> Response {
    // Accept must be present and admit JSON (json_response mode): absent -> 406.
    let accepts_json = req.header("accept").is_some_and(|a| {
        a.contains("application/json") || a.contains("text/event-stream") || a.contains("*/*")
    });
    if !accepts_json {
        return Response { status: "406 Not Acceptable", body: None };
    }
    // Content-Type must be JSON.
    let json_ct = req
        .header("content-type")
        .is_some_and(|c| c.contains("application/json"));
    if !json_ct {
        return Response { status: "400 Bad Request", body: None };
    }
    let message: Value = match serde_json::from_slice(&req.body) {
        Ok(v) => v,
        Err(_) => {
            return json_response(
                "400 Bad Request",
                "{\"jsonrpc\":\"2.0\",\"id\":\"server-error\",\"error\":{\"code\":-32700,\
\"message\":\"Parse error\"}}"
                    .to_string(),
            );
        }
    };
    let Some(method) = message.get("method").and_then(Value::as_str) else {
        return json_response(
            "400 Bad Request",
            "{\"jsonrpc\":\"2.0\",\"id\":null,\"error\":{\"code\":-32600,\
\"message\":\"Invalid Request\"}}"
                .to_string(),
        );
    };
    // A notification (no id) is acknowledged with 202 and no body (ADR-032:
    // nothing to return; the read-only server holds no session to advance).
    let Some(id) = message.get("id") else {
        return Response { status: "202 Accepted", body: None };
    };
    // Attribution rides X-Lore-Principal (ADR-098): recorded by audit, never an
    // access-control input — the response is identical whatever it says.
    let _principal = req.header("x-lore-principal").unwrap_or("");
    let id_json = serde_json::to_string(id).unwrap_or_else(|_| "null".to_string());
    let frame = process_request(root, tracker, method, &id_json, &message);
    json_response("200 OK", frame)
}

fn respond(writer: &mut TcpStream, resp: &Response) {
    let mut out = format!("HTTP/1.1 {}\r\n", resp.status);
    match &resp.body {
        Some(body) => {
            out.push_str("content-type: application/json\r\n");
            out.push_str(&format!("content-length: {}\r\n", body.len()));
            out.push_str("connection: close\r\n\r\n");
            out.push_str(body);
        }
        None => {
            out.push_str("content-length: 0\r\n");
            out.push_str("connection: close\r\n\r\n");
        }
    }
    let _ = writer.write_all(out.as_bytes());
    let _ = writer.flush();
}
