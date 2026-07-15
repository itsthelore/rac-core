# 19 — MCP HTTP transport: the `rac mcp --transport http` wire contract

Scope: the streamable-HTTP transport of `rac mcp` (ADR-098), ported to
`rac-mcp` (`src/http.rs`). Addendum 10 pins the stdio JSON-RPC surface and
declares HTTP out of its scope; this addendum pins HTTP. Source of truth:
`src/rac/mcp/transport.py` (the Python serving layer, which delegates to the
MCP SDK's streamable-HTTP transport in `stateless_http` + `json_response`
mode), CLI wiring `src/rac/cli.py` (`p_mcp` `--transport/--host/--port/--path`),
and the audit gate `src/rac/mcp/audit.py`.

## 0 — The parity surface, and what is deliberately not on it

ADR-098 defines the contract: "an HTTP response is payload-identical to stdio
for identical corpus bytes." So the parity surface is:

1. **Response body bytes.** For every request, the JSON-RPC frame in the HTTP
   response body is byte-identical to the stdio frame for the same request. The
   Rust HTTP transport enforces this by construction: it calls the *same*
   `process_request` frame processor as stdio (addendum 10 §2/§4/§5). Whatever
   stdio parity holds (PRIMARY 56, ORACLE-NEXT 76) holds for the HTTP body.
2. **HTTP status semantics** on the edge cases (§2 below).

Not on the parity surface (declared, mirroring addendum 10 §9's stance on
argparse usage-wrapping — the transport's incidental framing is not RAC's
contract):

- **uvicorn's envelope bytes.** The Python side is fronted by uvicorn, which
  emits `date:` and `server: uvicorn` headers and its own header order/casing.
  The Rust server emits its own minimal valid HTTP/1.1 envelope
  (`content-type: application/json`, `content-length`, `connection: close`).
  Header bytes are not compared.
- **Python error prose.** A malformed request body yields HTTP 400 on both, but
  the SDK's body carries Python's `json.JSONDecodeError` message
  ("Expecting property name enclosed in double quotes: line 1 column 2 …").
  That prose is Python-specific and not reproduced; the Rust body is its own
  `-32700 "Parse error"` frame. Status parity (400) is what is checked.

## 1 — Transport selection and defaults (from `cli.py` / `transport.py`)

`--transport {stdio,http}` (default `stdio`, byte-unchanged); `--host`
(default `127.0.0.1`, loopback — exposure is the deployment proxy's deliberate
act, ADR-085); `--port` (default `8000`); `--path` (default `/mcp`). Serving is
stateless per call (ADR-032): one JSON response per POST, no session store, no
`Mcp-Session-Id`.

## 2 — HTTP method / status map (captured empirically from the SDK)

| Request | Status | Body |
| --- | --- | --- |
| `POST <path>` valid request (has `id`) | 200 | JSON-RPC frame = stdio frame |
| `POST <path>` notification (no `id`) | 202 | empty |
| `POST <path>` no `Accept` header | 406 | empty |
| `POST <path>` `Content-Type` not JSON | 400 | empty |
| `POST <path>` malformed JSON | 400 | parse-error frame (prose differs, §0) |
| `DELETE <path>` | 405 | empty |
| other path | 404 | empty |

`Accept` need only admit JSON (`application/json`, `text/event-stream`, or
`*/*`) — `json_response` mode does not require the SSE type, matching the SDK
(an `application/json`-only `Accept` is accepted).

### GET — the one status divergence (reported, not failed)

The SDK answers `GET <path>` with 200 and opens an idle SSE stream (the server
never pushes on it, being stateless and read-only). The Rust server offers no
server-initiated stream and returns **405** — spec-permitted ("the server MAY
return 405 if it does not offer an SSE stream at this endpoint"), and the
covered POST-only clients are unaffected. Recorded as a documented divergence.

## 3 — Mandatory audit-on (ADR-084, ADR-098)

HTTP refuses to start without a *working* audit sink. `http::ensure_audit_sink`
mirrors `transport.ensure_audit_sink` + `audit.load_audit_config`:

- Read the `audit:` stanza from the nearest `.rac/config.yaml` at or above
  `--root` (walk up; no file / no `audit` section ⇒ disabled).
- Not enabled ⇒ exit non-zero with the ADR-084 message ("… Add an `audit:`
  stanza with `enabled: true` …").
- Enabled ⇒ resolve the path (`RAC_AUDIT_PATH` > config `path` >
  `$XDG_STATE_HOME/rac/audit.jsonl`), `mkdir -p` its parent, and prove it
  append-openable; otherwise exit non-zero ("… requires a writable audit log …").

stdio never calls this — audit stays config-driven and default-absent there.

## 4 — Attribution: `X-Lore-Principal` (ADR-098, ADR-084)

A caller asserts identity via the `X-Lore-Principal` request header
(case-insensitive). It is *attribution, not authentication*: recorded by the
audit sink, never verified, and never an access-control input — the response is
byte-identical whatever the header says (proven: body parity holds regardless of
the header). An unasserted call falls back to the recorder's resolution.

## 5 — Declared gaps (this port)

- **Per-call audit-line writing** rides the existing stubbed audit sidecar
  (addendum 10 records the Rust `rac-mcp` audit/telemetry sidecars as stubbed,
  wire-neutral). The HTTP port adds the mandatory-audit-on **startup gate** (§3)
  faithfully; emitting each call's audit line is the remaining follow-up.
- **GET SSE stream** — not offered (§2); 405 instead of an idle 200 stream.
- **Batch requests** (JSON array body) — not handled; single requests only.
- **Keep-alive** — the server sends `connection: close` per response.

## 6 — Referee

`rust/tools/mcp_http_parity.py` drives a Python and a Rust `--transport http`
server over real HTTP against an audit-enabled corpus and checks body bytes for
every request plus the §2 status map. Run in both modes:

```sh
python rust/tools/mcp_http_parity.py \
  --engine-a "../.venv-oracle/bin/rac mcp" --engine-b "target/release/rac-mcp"          # PRIMARY (5-tool)
python rust/tools/mcp_http_parity.py \
  --engine-a "<retrieval-oracle>/bin/rac mcp" --engine-b "target/release/rac-mcp" --six  # ORACLE-NEXT (6-tool)
```

Result: every body byte-identical and every status matched, both modes.
