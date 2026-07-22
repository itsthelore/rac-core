#!/usr/bin/env python3
"""Mutation-sequence referee (INDEX-PLAN B6): drive the oracle server and
decided-mcp — BOTH cache-on — over one shared corpus while editing, adding, and
deleting files between tool calls; every frame must byte-match. Duplicate-
token queries are excluded (contract §0a oracle defect)."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_parity  # noqa: E402

mcp_parity.Server.cache_on = True

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "rust/fixtures/index/repo"

work = Path(tempfile.mkdtemp(prefix="mcp-mutate-"))
corpus = work / "repo"
shutil.copytree(FIXTURE, corpus)
root = str(corpus / "rac")

servers = {
    "oracle": mcp_parity.Server(
        [str(REPO / ".venv-oracle/bin/rac"), "mcp"], root, work / "xdg-a"
    ),
    "native": mcp_parity.Server(
        [str(REPO / "rust/target/release/decided-mcp")], root, work / "xdg-b"
    ),
}
for s in servers.values():
    s.send(
        "initialize",
        {
            "protocolVersion": mcp_parity.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": mcp_parity.CLIENT_INFO,
        },
    )
    s.recv()
    s.send("notifications/initialized", None, notification=True)


def call(name, arguments):
    frames = {}
    for key, s in servers.items():
        s.send("tools/call", {"name": name, "arguments": arguments})
        frames[key] = s.recv()
    if frames["oracle"] != frames["native"]:
        print(f"FAIL {name} {arguments}")
        print(mcp_parity.first_diff(frames["oracle"], frames["native"]))
        sys.exit(1)
    print(f"PASS {name} {json.dumps(arguments)[:60]}")


def w(rel, text):
    (corpus / rel).write_text(text)


steps = 0
call("get_summary", {})
call("search_artifacts", {"query": "widget cache"})
call("get_artifact", {"id": "FIX-0DEC1CACHE00"})

# edit: flip a body line in an existing decision
w("rac/decisions/adr-3-no-scope.md", (corpus / "rac/decisions/adr-3-no-scope.md").read_text().replace("opt-in", "mandatory-opt-in"))
call("search_artifacts", {"query": "mandatory"})
call("get_summary", {})

# add: a new live decision with scope
w("rac/decisions/adr-6-new.md", "# ADR-6: Widget Sharding\n\n## Context\n\nSharding widgets.\n\n## Decision\n\nShard by tenant.\n\n## Consequences\n\nRebalancing needed.\n\n## Status\n\nAccepted\n\n## Applies To\n\n- src/shard/**\n")
call("search_artifacts", {"query": "sharding"})
call("find_decisions", {"topic": "sharding"})
call("find_decisions", {"path": "src/shard/ring.py"})
call("get_related", {"id": "FIX-0REQ1SYNC000", "depth": 2})

# delete: remove the duplicate pair's second file
(corpus / "rac/dup/two.md").unlink()
call("get_artifact", {"id": "FIX-IDX-DUP"})
call("search_artifacts", {"query": "duplicate"})
call("get_summary", {})

# rapid double mutation between calls
w("rac/notes/unknown.md", "Completely new scratch notes.\n\n## Fresh Heading\n\n- turbo line\n")
(corpus / "rac/decisions/adr-2-retired.md").unlink()
call("search_artifacts", {"query": "turbo"})
call("find_decisions", {"topic": "widget"})
call("get_summary", {})

for s in servers.values():
    s.proc.stdin.close()
    s.proc.wait(timeout=10)
shutil.rmtree(work)
print("mutation referee: ALL FRAMES BYTE-IDENTICAL")
