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
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::time::{Duration, Instant};

use serde_json::Value;

use crate::{audit, process_request};

/// Connection-hardening bounds for the ADR-098 shared endpoint. None is a parity
/// surface: no covered request approaches them, and connection handling is a
/// declared non-parity concern (PORT-CONTRACT.d/19 §0). They exist so a slow,
/// idle, or oversized client cannot wedge or exhaust the single-threaded server.
const READ_TIMEOUT: Duration = Duration::from_secs(30);
const WRITE_TIMEOUT: Duration = Duration::from_secs(30);
/// Total wall-clock budget for reading one request. The per-recv timeouts above
/// bound an *idle* peer, but a slow-trickle client that sends one byte just
/// inside each window would otherwise hold the single-threaded loop for as long
/// as it keeps dribbling; this caps the whole read phase so the classic
/// many-slow-headers slowloris is bounded regardless. (A single never-terminated
/// header line is still bounded by MAX_HEADER_BYTES; the full fix is the
/// worker-pool follow-up.)
const MAX_REQUEST_READ: Duration = Duration::from_secs(60);
const MAX_HEADER_BYTES: u64 = 64 * 1024;
const MAX_HEADERS: usize = 200;
const MAX_BODY: usize = 8 * 1024 * 1024;

/// The `rac-mcp` parse-error frame for an unreadable body. Only the 400 status
/// is the parity surface (PORT-CONTRACT.d/19 §2); the body prose is the Rust
/// server's own (the SDK's Python `JSONDecodeError` text is not reproduced).
const PARSE_ERROR_FRAME: &str = "{\"jsonrpc\":\"2.0\",\"id\":\"server-error\",\"error\":{\"code\":-32700,\"message\":\"Parse error\"}}";

/// Prove a working audit sink for HTTP serving (ADR-084 fail-loud). Audit must
/// be enabled in `.rac/config.yaml` and its resolved path writable, or the
/// shared endpoint refuses to start. stdio never calls this — audit stays
/// config-driven and default-absent there.
pub fn ensure_audit_sink(config: &audit::AuditConfig) -> Result<(), String> {
    if !config.enabled {
        return Err(
            "HTTP serving requires the read-access audit log, but it is not \
enabled. Add an `audit:` stanza with `enabled: true` to .rac/config.yaml \
before serving over HTTP (ADR-084)."
                .to_string(),
        );
    }
    let path = audit::resolve_audit_path(&config.path);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| audit_unwritable(&path, &e.to_string()))?;
    }
    std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| audit_unwritable(&path, &e.to_string()))?;
    Ok(())
}

fn audit_unwritable(path: &std::path::Path, reason: &str) -> String {
    format!(
        "HTTP serving requires a writable audit log, but {} could not be opened \
for append ({reason}). Fix the audit path or permissions before serving over \
HTTP (ADR-084).",
        path.display()
    )
}

/// Serve `root` over streamable HTTP (stateless JSON mode) until interrupted.
/// Single-threaded: one request served to completion before the next, so the
/// per-server freshness tracker's mutable read-model is accessed serially
/// without locking (stateless reads are cheap — 28 ms cold on the live corpus).
/// Each connection's socket I/O is time-bounded and its request size is capped
/// ([`handle_connection`]), and request handling is panic-isolated, so no single
/// slow, oversized, or panicking client can wedge or abort the shared loop.
pub fn serve_http(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    recorder: &mut Option<audit::Recorder>,
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
    serve_listener(&listener, root, tracker, recorder, path);
    std::process::exit(0);
}

/// The accept loop, split from the bind/announce so tests can drive it over a
/// pre-bound `127.0.0.1:0` listener without the diverging `serve_http` wrapper.
fn serve_listener(
    listener: &TcpListener,
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    recorder: &mut Option<audit::Recorder>,
    path: &str,
) {
    for stream in listener.incoming() {
        match stream {
            Ok(s) => handle_connection(root, tracker, recorder, path, s),
            Err(_) => continue,
        }
    }
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

/// Outcome of parsing one request off the wire.
enum ReadOutcome {
    /// A well-formed request to route.
    Ok(Request),
    /// A hardening rejection to answer, then close (e.g. a 413 for an oversized
    /// body). Distinct from `Abort` so the client gets a status, not a hang.
    Reject(Response),
    /// Malformed, truncated, or oversized past recovery: drop the connection.
    Abort,
}

fn handle_connection(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    recorder: &mut Option<audit::Recorder>,
    path: &str,
    stream: TcpStream,
) {
    // Bound every socket operation: a client that connects and sends nothing, or
    // reads its response slowly, must not stall the serial accept loop for every
    // other client (slowloris). The timeouts are set on the socket before it is
    // cloned, so both the read half and the write half inherit them.
    if stream.set_read_timeout(Some(READ_TIMEOUT)).is_err()
        || stream.set_write_timeout(Some(WRITE_TIMEOUT)).is_err()
    {
        return;
    }
    let mut reader = BufReader::new(match stream.try_clone() {
        Ok(s) => s,
        Err(_) => return,
    });
    let mut writer = stream;
    let deadline = Instant::now() + MAX_REQUEST_READ;
    let resp = match read_request(&mut reader, deadline) {
        ReadOutcome::Ok(req) => {
            // Isolate any panic reachable from a request (an engine `expect` on a
            // hostile corpus edge, or a future bug) so it becomes a 500 for this
            // one client instead of aborting the shared server for all of them —
            // the isolation uvicorn gives the Python side.
            match catch_unwind(AssertUnwindSafe(|| route(root, tracker, recorder, path, &req))) {
                Ok(r) => r,
                Err(_) => {
                    // A panic can leave the server-lifetime FreshnessTracker
                    // desynced: read_model()'s detect() commits the advanced
                    // manifest BEFORE apply() parses (freshness.rs), so a parse
                    // panic advances the manifest without updating the model.
                    // Diffing against that advanced manifest on the next request
                    // would find nothing changed and serve the STALE model
                    // indefinitely. Drop the tracker instead, so the next request
                    // rebuilds from scratch (or serves a fresh walk) — a loud
                    // rebuild/500 beats silently serving stale results.
                    *tracker = None;
                    Response { status: "500 Internal Server Error", body: None }
                }
            }
        }
        ReadOutcome::Reject(resp) => resp,
        ReadOutcome::Abort => return,
    };
    respond(&mut writer, &resp);
}

/// Parse one HTTP/1.1 request: request line, headers, and a Content-Length body.
/// The request line + header block is bounded to `MAX_HEADER_BYTES`/`MAX_HEADERS`
/// and the body allocation is capped at `MAX_BODY`, so no single client can grow
/// the server's memory without limit.
fn read_request(reader: &mut BufReader<TcpStream>, deadline: Instant) -> ReadOutcome {
    // Read the request line and headers through a byte-capped view so an
    // unterminated line or a header flood cannot grow memory without bound.
    let mut head = reader.by_ref().take(MAX_HEADER_BYTES);

    let mut line = String::new();
    match head.read_line(&mut line) {
        Ok(0) => return ReadOutcome::Abort, // EOF before any request
        Ok(_) => {}
        Err(_) => return ReadOutcome::Abort,
    }
    let mut parts = line.split_whitespace();
    let (Some(method), Some(target)) = (parts.next(), parts.next()) else {
        return ReadOutcome::Abort;
    };
    let method = method.to_string();
    let target = target.to_string();

    let mut headers = Vec::new();
    let mut terminated = false;
    loop {
        // Total-read deadline: caps a slow-trickle client that dribbles one
        // header line per idle-window without ever tripping the per-recv timeout.
        if Instant::now() >= deadline {
            return ReadOutcome::Abort;
        }
        let mut h = String::new();
        match head.read_line(&mut h) {
            Ok(0) => break, // EOF or header budget exhausted
            Ok(_) => {}
            Err(_) => return ReadOutcome::Abort,
        }
        let trimmed = h.trim_end_matches(['\r', '\n']);
        if trimmed.is_empty() {
            terminated = true;
            break;
        }
        if headers.len() >= MAX_HEADERS {
            return ReadOutcome::Abort; // header flood
        }
        if let Some((k, v)) = trimmed.split_once(':') {
            headers.push((k.trim().to_string(), v.trim().to_string()));
        }
    }
    // The header block must close with a blank line; if the budget or the
    // connection ended first, do not trust a partial parse.
    if !terminated {
        return ReadOutcome::Abort;
    }
    // The `head` byte-cap borrow ends here (its last use was the header loop),
    // so the body reads from the now-unbounded `reader` below.

    let len: usize = headers
        .iter()
        .find(|(k, _)| k.eq_ignore_ascii_case("content-length"))
        .and_then(|(_, v)| v.trim().parse().ok())
        .unwrap_or(0);
    // Never size a body buffer from an unbounded client-declared length: reject
    // oversized bodies before allocating a single byte. Covered MCP frames are
    // tiny, so no covered request is ever rejected here.
    if len > MAX_BODY {
        return ReadOutcome::Reject(Response { status: "413 Payload Too Large", body: None });
    }
    let mut body = vec![0u8; len];
    if len > 0 && reader.read_exact(&mut body).is_err() {
        return ReadOutcome::Abort;
    }
    ReadOutcome::Ok(Request { method, target, headers, body })
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
    recorder: &mut Option<audit::Recorder>,
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
        "POST" => route_post(root, tracker, recorder, req),
        _ => Response { status: "405 Method Not Allowed", body: None },
    }
}

fn route_post(
    root: &str,
    tracker: &mut Option<rac_engine::freshness::FreshnessTracker>,
    recorder: &mut Option<audit::Recorder>,
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
    // Chunked bodies are not decoded — every covered client sends Content-Length
    // (the referee always does), so a chunk-framed body is never read and would
    // be misread as empty. Reject it explicitly as a parse error, after the
    // Accept/Content-Type gates so their precedence is unchanged; this yields the
    // same 400 the empty-body path already produced (unsupported; declared in
    // PORT-CONTRACT.d/19 §5).
    if req
        .header("transfer-encoding")
        .is_some_and(|te| te.to_ascii_lowercase().contains("chunked"))
    {
        return json_response("400 Bad Request", PARSE_ERROR_FRAME.to_string());
    }
    let message: Value = match serde_json::from_slice(&req.body) {
        Ok(v) => v,
        Err(_) => return json_response("400 Bad Request", PARSE_ERROR_FRAME.to_string()),
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
    let principal = req.header("x-lore-principal");
    let id_json = serde_json::to_string(id).unwrap_or_else(|_| "null".to_string());
    let frame = process_request(root, tracker, method, &id_json, &message, recorder.as_mut(), principal);
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpStream;

    /// Spawn the serial server over an ephemeral port with no tracker/recorder
    /// (fresh-walk, no audit): this targets the connection layer — the frame
    /// contents are the oracle parity referee's job. Returns the bound port.
    fn spawn_server() -> u16 {
        let root = std::env::temp_dir()
            .join(format!("rac-mcp-http-test-{}", std::process::id()))
            .to_string_lossy()
            .into_owned();
        let _ = std::fs::create_dir_all(&root);
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            let mut tracker: Option<rac_engine::freshness::FreshnessTracker> = None;
            let mut recorder: Option<audit::Recorder> = None;
            serve_listener(&listener, &root, &mut tracker, &mut recorder, "/mcp");
        });
        port
    }

    /// Send raw bytes, tolerate a mid-write reset (the server may close on a
    /// hostile request before we finish writing), and return the response bytes.
    fn send(port: u16, raw: &[u8]) -> Vec<u8> {
        let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
        s.set_write_timeout(Some(Duration::from_secs(5))).unwrap();
        let _ = s.write_all(raw);
        let _ = s.flush();
        let mut buf = Vec::new();
        let _ = s.read_to_end(&mut buf); // EOF or reset on a dropped connection
        buf
    }

    fn status_line(resp: &[u8]) -> String {
        let end = resp.windows(2).position(|w| w == b"\r\n").unwrap_or(resp.len());
        String::from_utf8_lossy(&resp[..end]).into_owned()
    }

    fn post(len_header: &str, body: &[u8]) -> Vec<u8> {
        let mut req = format!(
            "POST /mcp HTTP/1.1\r\nhost: x\r\naccept: application/json\r\n\
content-type: application/json\r\ncontent-length: {len_header}\r\n\r\n"
        )
        .into_bytes();
        req.extend_from_slice(body);
        req
    }

    // The hardening paths (timeouts, body cap, header cap, panic isolation) are
    // NOT covered by the oracle parity referee — no covered request approaches
    // them — so they would regress silently. This exercises them natively.
    #[test]
    fn hardened_http_paths() {
        let port = spawn_server();

        // 1) A normal initialize POST is served 200 (baseline through the new
        //    bounded read path). `initialize` needs no corpus.
        let body = br#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}"#;
        let ok = post(&body.len().to_string(), body);
        assert!(
            status_line(&send(port, &ok)).contains("200 OK"),
            "normal POST should be 200"
        );

        // 2) An oversized Content-Length is rejected 413 before any allocation.
        let over = post("999999999999", b"");
        assert!(
            status_line(&send(port, &over)).contains("413"),
            "oversized Content-Length should be 413"
        );

        // 3) A header flood past MAX_HEADERS drops the connection (no response).
        let mut flood = b"POST /mcp HTTP/1.1\r\n".to_vec();
        for i in 0..MAX_HEADERS + 50 {
            flood.extend_from_slice(format!("x-{i}: {}\r\n", "A".repeat(64)).as_bytes());
        }
        flood.extend_from_slice(b"\r\n");
        assert!(
            !String::from_utf8_lossy(&send(port, &flood)).contains("200"),
            "header flood should be dropped, not served"
        );

        // 4) The server survived every hostile probe and still serves 200.
        assert!(
            status_line(&send(port, &ok)).contains("200 OK"),
            "server should still serve after hostile probes"
        );
    }

    #[test]
    fn request_helpers() {
        let req = Request {
            method: "POST".into(),
            target: "/mcp?q=1&r=2".into(),
            headers: vec![("Content-Type".into(), "application/json".into())],
            body: vec![],
        };
        assert_eq!(req.path(), "/mcp"); // query stripped
        assert_eq!(req.header("content-type"), Some("application/json")); // case-insensitive
        assert_eq!(req.header("x-absent"), None);
    }
}
