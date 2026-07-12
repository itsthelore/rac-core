#!/usr/bin/env python3
"""mcp_parity — two-server byte-parity referee for the `rac mcp` stdio surface.

Drives two MCP servers as subprocesses under identical env/cwd over the case
basket in `rust/mcp-parity-cases.json` and compares per the rule in
`rust/PORT-CONTRACT.d/10-mcp-surface.md` §9:

- `tools/call` and `tools/list` response frames: byte-equal, whole line.
- `initialize`: structural — `serverInfo.name == "lore"`, identical
  capabilities object, protocol-version echo of the pinned request;
  `serverInfo.version` is declared-normalized (an SDK version string).
- stderr, audit/telemetry files, cache contents, latency: never compared.

Scoreboards (`scoreboard.json` + `scoreboard.md`) are pure functions of the
case outcomes — no timestamps — so two runs over identical server behavior
produce byte-identical scoreboards. Exit 0 iff every selected case (and every
initialize) passes; 1 on any failure; 2 on usage/setup errors.

Usage:
  mcp_parity.py --engine-a "<cmd>" --engine-b "<cmd>" \
      [--cases rust/mcp-parity-cases.json] [--out rust/mcp-parity-out] \
      [--exclude-tags six,list] [--filter substr] [--perf]

Engine commands are shell-split; the harness appends `--root <abs-root>`.
Oracle-vs-oracle mode is just both engines set to the same oracle. `--perf`
skips parity and reports startup-to-first-result plus per-call medians
(7 runs) for get_summary and retrieve_grounding, per engine.
"""

from __future__ import annotations

import argparse
import json
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "mcp-parity-harness", "version": "0.0.1"}
READ_TIMEOUT = 120  # seconds per response line


class Server:
    """One MCP server subprocess with the neutralized environment."""

    def __init__(self, cmd: list[str], root: str, xdg_dir: Path):
        import os

        env = dict(os.environ)
        for name, sub in (
            ("HOME", "home"),
            ("XDG_STATE_HOME", "state"),
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_CACHE_HOME", "cache"),
        ):
            d = xdg_dir / sub
            d.mkdir(parents=True, exist_ok=True)
            env[name] = str(d)
        # Canonical comparison path (contract §0a, "Oracle defect found"): the
        # Python oracle's cache-on serving diverges from its own no-cache path
        # on duplicate-token queries (df dedup inconsistency, an ADR-112
        # violation). Pin BOTH servers to the no-cache engine path — the same
        # path every other parity claim in this spike compares against. The
        # Rust server ignores the variable (it re-reads per call, ADR-032).
        env["RAC_NO_CACHE"] = "1"
        self.proc = subprocess.Popen(
            [*cmd, "--root", root],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(REPO_ROOT),
            env=env,
        )
        self.reqid = 0

    def send(self, method: str, params: dict, notification: bool = False) -> None:
        obj: dict = {"jsonrpc": "2.0"}
        if not notification:
            self.reqid += 1
            obj["id"] = self.reqid
        obj["method"] = method
        if params is not None:
            obj["params"] = params
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        assert self.proc.stdin is not None
        self.proc.stdin.write(line.encode("utf-8"))
        self.proc.stdin.flush()

    def recv(self) -> bytes:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout unexpectedly")
        return line

    def call(self, method: str, params: dict) -> bytes:
        self.send(method, params)
        return self.recv()

    def initialize(self) -> bytes:
        frame = self.call(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self.send("notifications/initialized", None, notification=True)
        return frame

    def close(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def check_initialize(frame: bytes, label: str) -> list[str]:
    """Structural checks per contract §9 rule 3. Returns failure notes."""
    notes: list[str] = []
    try:
        obj = json.loads(frame)
    except json.JSONDecodeError:
        return [f"{label}: initialize frame is not JSON"]
    result = obj.get("result", {})
    if result.get("protocolVersion") != PROTOCOL_VERSION:
        notes.append(f"{label}: protocolVersion echo mismatch: {result.get('protocolVersion')}")
    info = result.get("serverInfo", {})
    if info.get("name") != "lore":
        notes.append(f"{label}: serverInfo.name != 'lore': {info.get('name')}")
    if not isinstance(info.get("version"), str) or not info.get("version"):
        notes.append(f"{label}: serverInfo.version missing")
    caps = result.get("capabilities")
    expected_caps = {
        "experimental": {},
        "prompts": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False},
        "tools": {"listChanged": False},
    }
    if caps != expected_caps:
        notes.append(f"{label}: capabilities shape mismatch: {caps}")
    return notes


def load_cases(path: Path, exclude_tags: set[str], name_filter: str | None):
    spec = json.loads(path.read_text(encoding="utf-8"))
    roots: dict[str, str] = spec["roots"]
    cases = []
    for case in spec["cases"]:
        tags = set(case.get("tags", []))
        if tags & exclude_tags:
            continue
        if name_filter and name_filter not in case["id"]:
            continue
        cases.append(case)
    return roots, cases


def resolve_root(roots: dict[str, str], key: str, out_dir: Path) -> str:
    raw = roots[key]
    if raw == "<EMPTY>":
        d = out_dir / "empty-root"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    return str((REPO_ROOT / raw).resolve())


def run_engine(cmd: list[str], label: str, roots, cases, out_dir: Path):
    """Run every case sequentially, one server per root (grouped, in case
    order). Returns (init_frames_by_root, frames_by_case_id)."""
    order: list[str] = []
    for case in cases:
        if case["root"] not in order:
            order.append(case["root"])
    init_frames: dict[str, bytes] = {}
    frames: dict[str, bytes] = {}
    for root_key in order:
        root = resolve_root(roots, root_key, out_dir)
        server = Server(cmd, root, out_dir / f"xdg-{label}")
        try:
            init_frames[root_key] = server.initialize()
            for case in cases:
                if case["root"] != root_key:
                    continue
                frames[case["id"]] = server.call(case["method"], case.get("params", {}))
        finally:
            server.close()
    return init_frames, frames


def write_scoreboard(out_dir: Path, rows: list[dict]) -> bool:
    passed = sum(1 for r in rows if r["status"] == "pass")
    failed = [r for r in rows if r["status"] != "pass"]
    board = {
        "summary": {"total": len(rows), "passed": passed, "failed": len(failed)},
        "cases": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scoreboard.json").write_text(
        json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# MCP parity scoreboard",
        "",
        f"- total: {len(rows)}",
        f"- passed: {passed}",
        f"- failed: {len(failed)}",
        "",
        "| case | root | mode | status |",
        "| --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(f"| {r['id']} | {r['root']} | {r['mode']} | {r['status']} |")
    if failed:
        lines.append("")
        lines.append("## Failures")
        for r in failed:
            lines.append("")
            lines.append(f"### {r['id']}")
            for note in r.get("notes", []):
                lines.append(f"- {note}")
    (out_dir / "scoreboard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return not failed


def first_diff(a: bytes, b: bytes) -> str:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            lo = max(0, i - 60)
            return (
                f"first diff at byte {i}: "
                f"A=...{a[lo:i + 80]!r} B=...{b[lo:i + 80]!r}"
            )
    return f"length differs: A={len(a)} B={len(b)}"


def run_parity(args) -> int:
    exclude = {t for t in (args.exclude_tags or "").split(",") if t}
    roots, cases = load_cases(Path(args.cases), exclude, args.filter)
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd_a = shlex.split(args.engine_a)
    cmd_b = shlex.split(args.engine_b)
    init_a, frames_a = run_engine(cmd_a, "a", roots, cases, out_dir)
    init_b, frames_b = run_engine(cmd_b, "b", roots, cases, out_dir)

    rows: list[dict] = []
    for root_key in init_a:
        notes = check_initialize(init_a[root_key], "A") + check_initialize(
            init_b[root_key], "B"
        )
        rows.append(
            {
                "id": f"initialize:{root_key}",
                "root": root_key,
                "mode": "structural",
                "status": "pass" if not notes else "fail",
                **({"notes": notes} if notes else {}),
            }
        )
    for case in cases:
        a = frames_a[case["id"]]
        b = frames_b[case["id"]]
        if a == b:
            rows.append(
                {"id": case["id"], "root": case["root"], "mode": "bytes", "status": "pass"}
            )
        else:
            rows.append(
                {
                    "id": case["id"],
                    "root": case["root"],
                    "mode": "bytes",
                    "status": "fail",
                    "notes": [first_diff(a, b)],
                }
            )
    ok = write_scoreboard(out_dir, rows)
    print(
        f"mcp_parity: {sum(1 for r in rows if r['status'] == 'pass')}/{len(rows)} passed"
        f" -> {out_dir}/scoreboard.md"
    )
    return 0 if ok else 1


PERF_RUNS = 7


def perf_engine(cmd: list[str], root: str, out_dir: Path, label: str) -> dict:
    startups: list[float] = []
    summary_calls: list[float] = []
    retrieve_calls: list[float] = []
    retrieve_supported = True
    for _ in range(PERF_RUNS):
        t0 = time.perf_counter()
        server = Server(cmd, root, out_dir / f"xdg-perf-{label}")
        try:
            server.initialize()
            startups.append(time.perf_counter() - t0)
            t = time.perf_counter()
            server.call("tools/call", {"name": "get_summary", "arguments": {}})
            summary_calls.append(time.perf_counter() - t)
            t = time.perf_counter()
            frame = server.call(
                "tools/call",
                {"name": "retrieve_grounding", "arguments": {"task": "add a new MCP tool"}},
            )
            if b"Unknown tool" in frame:
                retrieve_supported = False
            else:
                retrieve_calls.append(time.perf_counter() - t)
        finally:
            server.close()
    med = lambda xs: round(statistics.median(xs) * 1000, 2) if xs else None
    return {
        "startup_to_first_result_ms_median": med(startups),
        "get_summary_ms_median": med(summary_calls),
        "retrieve_grounding_ms_median": med(retrieve_calls) if retrieve_supported else None,
        "runs": PERF_RUNS,
    }


def run_perf(args) -> int:
    roots, _ = load_cases(Path(args.cases), set(), None)
    root = resolve_root(roots, args.perf_root, Path(args.out))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for label, spec in (("engine-a", args.engine_a), ("engine-b", args.engine_b)):
        report[label] = {"cmd": spec, **perf_engine(shlex.split(spec), root, out_dir, label)}
    (out_dir / "perf.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine-a", required=True, help="command for server A (root appended)")
    p.add_argument("--engine-b", required=True, help="command for server B (root appended)")
    p.add_argument("--cases", default=str(REPO_ROOT / "rust" / "mcp-parity-cases.json"))
    p.add_argument("--out", default=str(REPO_ROOT / "rust" / "mcp-parity-out"))
    p.add_argument("--exclude-tags", default="", help="comma-separated tags to skip")
    p.add_argument("--filter", default=None, help="substring filter on case ids")
    p.add_argument("--perf", action="store_true", help="perf mode instead of parity")
    p.add_argument("--perf-root", default="live", help="root key for perf mode")
    args = p.parse_args()
    if args.perf:
        return run_perf(args)
    return run_parity(args)


if __name__ == "__main__":
    sys.exit(main())
