#!/usr/bin/env python3
"""Generate `rac retrieve` conformance vectors from the ORACLE-NEXT oracle
(`rac.services.retrieve`, branch `grounding-retrieval-surface`,
version 0.1.dev55+gf2091befd) over the LIVE `rac/` corpus and the retrieval
fixture corpora under `rust/fixtures/retrieve/`.

REGENERABLE: any change to `rac/` or the fixtures shifts the vectors — rerun
with the ORACLE-NEXT venv python:

    cd /home/user/rac-core && \
      <oracle-next-venv>/bin/python rust/spec/gen_vectors_retrieve.py

Each case pins the exact budget-capped serialization
(`rac.mcp.budget.serialize` — the byte payload `rac retrieve --json` emits)
and the human rendering (`rac.output.render_retrieve_human` over
`json.loads(serialized)`), for one `(directory, task, scope, top_k, budget,
live_only)` request. The Rust side (`rust/rac-engine/tests/
retrieve_vectors.rs`) replays every case through
`rac_engine::retrieve::{retrieve_grounding, serialize}` and
`rac_engine::output::render_retrieve_human` and asserts byte equality.
"""

from __future__ import annotations

import json
from pathlib import Path

from rac.mcp.budget import serialize
from rac.output import render_retrieve_human
from rac.services.retrieve import retrieve_grounding

REPO = Path(__file__).resolve().parents[2]  # /home/user/rac-core
OUT = Path(__file__).resolve().parents[1] / "rac-engine/tests/vectors/retrieve.json"

RAC = "rac"
CHAIN = "rust/fixtures/retrieve/chain"
MIXED = "rust/fixtures/retrieve/mixed"
RESOLVE_FX = "tests/fixtures/resolve"

# (directory, task, scope, top_k, budget, live_only)
CASES: list[dict] = [
    # --- live rac/ corpus: plain keyword retrieval, defaults -----------------
    {"dir": RAC, "task": "markdown"},
    {"dir": RAC, "task": "search"},
    {"dir": RAC, "task": "index cache"},
    {"dir": RAC, "task": "release versioning"},
    {"dir": RAC, "task": "telemetry"},
    {"dir": RAC, "task": "guide budget"},
    # supersedes substitution on the live corpus (ADR-076 -> ADR-111 etc.)
    {"dir": RAC, "task": "calver"},
    {"dir": RAC, "task": "calver", "live_only": False},
    {"dir": RAC, "task": "release versioning calver", "top_k": 8},
    # scope binding over the live corpus (repo root = .rac/config.yaml)
    {"dir": RAC, "task": "search", "scope": "src/rac/services/resolve.py"},
    {"dir": RAC, "task": "budget", "scope": "src/rac/mcp/server.py"},
    {"dir": RAC, "task": "zzz-no-keyword-hits", "scope": "src/rac/services/resolve.py"},
    {"dir": RAC, "task": "markdown", "scope": "does/not/exist.py"},
    {"dir": RAC, "task": "markdown", "scope": "../outside.py"},
    {"dir": RAC, "task": "markdown", "scope": "/etc/passwd"},
    # Repo-relative on purpose: an absolute scope would bake this machine's
    # checkout path into the pinned payload bytes and break on any other
    # checkout (CI runs from a different root). Relative scope still
    # exercises the same binding channel and echoes portably.
    {"dir": RAC, "task": "markdown", "scope": "src/rac/cli.py"},
    # top-k / budget shaping
    {"dir": RAC, "task": "markdown", "top_k": 1},
    {"dir": RAC, "task": "markdown", "top_k": 2, "budget": 400},
    {"dir": RAC, "task": "markdown", "budget": 500},
    {"dir": RAC, "task": "markdown", "budget": 120},
    {"dir": RAC, "task": "markdown", "budget": 60},
    {"dir": RAC, "task": "markdown", "budget": 1},
    {"dir": RAC, "task": "markdown", "top_k": 25, "budget": 2000},
    # unicode tasks (ASCII-only tokenizer seams) + empty results
    {"dir": RAC, "task": "café"},
    {"dir": RAC, "task": "İstanbul Straße"},
    {"dir": RAC, "task": "index—cache"},
    {"dir": RAC, "task": "zzz no such term anywhere"},
    {"dir": RAC, "task": ""},
    {"dir": RAC, "task": "it's a 'quoted' task"},
    # --- chain fixture: supersedes chains + scope stratification -------------
    {"dir": CHAIN, "task": "widget"},
    {"dir": CHAIN, "task": "widget", "live_only": False},
    {"dir": CHAIN, "task": "widget storage"},
    {"dir": CHAIN, "task": "storage", "scope": "src/api/handlers.py"},
    {"dir": CHAIN, "task": "naming", "scope": "docs/guide.md"},
    {"dir": CHAIN, "task": "zzz", "scope": "src/api/"},
    {"dir": CHAIN, "task": "zzz", "scope": "src/api/deep/nested/mod.py"},
    {"dir": CHAIN, "task": "widget", "scope": "src/lib/other.py"},
    {"dir": CHAIN, "task": "widget", "top_k": 1, "budget": 200},
    {"dir": CHAIN, "task": "frobnication pipeline", "live_only": False},
    {"dir": CHAIN, "task": "frobnication pipeline"},
    # --- mixed fixture: per-type retirement, unicode, CRLF excerpts ----------
    {"dir": MIXED, "task": "gadget"},
    {"dir": MIXED, "task": "gadget", "live_only": False},
    {"dir": MIXED, "task": "gadget sync"},
    {"dir": MIXED, "task": "gadget sync", "live_only": False},
    {"dir": MIXED, "task": "café Straße"},
    {"dir": MIXED, "task": "gadget", "budget": 300},
    {"dir": MIXED, "task": "gadget", "top_k": 2, "budget": 150},
    {"dir": MIXED, "task": "gadget", "top_k": 3, "budget": 40},
    {"dir": MIXED, "task": "crlf design"},
    # --- resolve fixture corpus (no supersedes, no scope decl) ---------------
    {"dir": RESOLVE_FX, "task": "markdown"},
    {"dir": RESOLVE_FX, "task": "markdown", "scope": "src/anything.py"},
    {"dir": RESOLVE_FX, "task": "markdown", "budget": 90},
]


def main() -> None:
    import os

    os.chdir(REPO)
    out_cases = []
    for case in CASES:
        directory = case["dir"]
        task = case["task"]
        scope = case.get("scope")
        top_k = case.get("top_k", 5)
        budget = case.get("budget", 10_000)
        live_only = case.get("live_only", True)
        payload = retrieve_grounding(
            directory,
            task,
            scope=scope,
            top_k=top_k,
            budget=budget,
            live_only=live_only,
        )
        serialized = serialize(payload, budget)
        human = render_retrieve_human(json.loads(serialized))
        out_cases.append(
            {
                "directory": directory,
                "task": task,
                "scope": scope,
                "top_k": top_k,
                "budget": budget,
                "live_only": live_only,
                "serialized": serialized,
                "human": human,
            }
        )
    OUT.write_text(
        json.dumps(
            {
                "oracle": "rac.services.retrieve (grounding-retrieval-surface)",
                "oracle_version": "0.1.dev55+gf2091befd",
                "case_count": len(out_cases),
                "cases": out_cases,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(out_cases)} cases -> {OUT}")


if __name__ == "__main__":
    main()
