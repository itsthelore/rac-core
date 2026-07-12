#!/usr/bin/env python3
"""Generate `rac find` BM25F/RRF conformance vectors from the oracle
(`rac.services.resolve`) over the LIVE `rac/` corpus.

REGENERABLE: the vectors pin unrounded `bm25`/`fused` f64s (as raw IEEE-754
bit patterns), competition ranks, evidence, snippets, and final ordering for
a fixed corpus snapshot. Any change to `rac/` shifts them — rerun:

    cd /home/user/rac-core && .venv-oracle/bin/python rust/spec/gen_vectors_resolve.py

The Rust side (`rust/rac-engine/tests/resolve_vectors.rs`) replays every
query through `rac_engine::resolve::search_index` / `find_decisions` and
asserts EXACT f64 bit equality (PORT-CONTRACT.d/06 §7–9: the float operation
order is normative; a 1-ulp divergence must fail the suite, not round away).

Full precision is recovered from the oracle's own internals: corpus stats via
`_corpus_stats`, per-match bm25 via `_bm25f` (corpus-global stats are filter-
independent, §6), and fused via the RRF formula over the evidence's integer
ranks — the exact op sequence `_rank_and_build` uses. Each recomputation is
cross-checked against the rounded values the public API emitted.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

from rac.services import resolve as R
from rac.services.index import build_repository_index

REPO = Path(__file__).resolve().parents[2]  # /home/user/rac-core
OUT = Path(__file__).resolve().parents[1] / "rac-engine/tests/vectors/resolve.json"

DIRECTORY = "rac"

# Query plan: plain terms, prefix fragments, multi-term AND, duplicate tokens
# (the §7.1 landmine), unicode (ASCII-only tokenizer + casefold seams), camel
# seams, IDs/aliases, --type, --tag, and --decisions.
QUERIES: list[dict] = [
    # plain single terms
    {"query": "search"},
    {"query": "markdown"},
    {"query": "decision"},
    {"query": "roadmap"},
    {"query": "the"},
    {"query": "validate"},
    {"query": "cache"},
    {"query": "index"},
    {"query": "graph"},
    {"query": "telemetry"},
    {"query": "prompt"},
    {"query": "corpus"},
    {"query": "json"},
    {"query": "cli"},
    {"query": "schema"},
    {"query": "release"},
    {"query": "requirements"},
    {"query": "watchkeeper"},
    {"query": "explorer"},
    {"query": "enterprise"},
    # duplicate query tokens (df double-count + double per-term add, §7.1)
    {"query": "search search"},
    {"query": "the the the"},
    {"query": "markdown markdown search"},
    {"query": "cache cache"},
    {"query": "adr-037 adr-037"},
    # unicode: non-ASCII separators, casefold-only-in-resolve regime
    {"query": "café"},
    {"query": "éclair"},
    {"query": "İstanbul"},
    {"query": "Straße"},
    {"query": "index—cache"},
    # camel seams and mixed case
    {"query": "camelCase"},
    {"query": "IndexStore"},
    {"query": "readModel"},
    {"query": "MiXeD-Case_fooBAR"},
    # identifiers / aliases
    {"query": "ADR-037"},
    {"query": "adr-104"},
    {"query": "RAC-KTXTAF6ZKDK8"},
    {"query": "rac-ktq63dpsmf19"},
    # prefix fragments (one-directional prefix matching)
    {"query": "sear"},
    {"query": "relation"},
    {"query": "val"},
    {"query": "deriv"},
    # version-shaped
    {"query": "v0.22.0"},
    {"query": "0.7.2"},
    # empty-tokenizing (no matches, exit 0)
    {"query": "..."},
    {"query": "—"},
    # multi-term AND
    {"query": "tier search"},
    {"query": "derived index cache"},
    {"query": "token boundary matching"},
    {"query": "release gate"},
    {"query": "usage ping"},
    {"query": "graph export edges"},
    # --type (corpus stats stay corpus-global)
    {"query": "the", "type": "decision"},
    {"query": "search", "type": "roadmap"},
    {"query": "cache", "type": "unknown"},
    # --tag facet (whole-tag casefold, not tokenized)
    {"query": "the", "tags": ["architecture"]},
    {"query": "the", "tags": ["Architecture"]},
    {"query": "the", "tags": ["architecture", "technical"]},
    # --decisions (live filter after ranking; rank gaps preserved)
    {"query": "markdown", "decisions": True},
    {"query": "cache", "decisions": True},
]


def bits(x: float) -> int:
    """The raw IEEE-754 bit pattern of a float, as a u64."""
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def main() -> None:
    os.chdir(REPO)
    entries = build_repository_index(DIRECTORY).artifacts
    field_tokens = {e.path: R._field_tokens(e) for e in entries}

    cases = []
    for spec in QUERIES:
        query = spec["query"]
        artifact_type = spec.get("type")
        tags = spec.get("tags")
        decisions = bool(spec.get("decisions"))

        if decisions:
            result = R.find_decisions(DIRECTORY, query)
        else:
            result = R.search_index(entries, query, artifact_type=artifact_type, tags=tags)

        terms = R.tokenize(query)
        n, df, avglen, _ = R._corpus_stats(entries, terms, field_tokens)

        matches = []
        for m in result.matches:
            ev = m.evidence
            bm25 = R._bm25f(field_tokens[m.path], terms, n, df, avglen)
            fused = 1.0 / (R._RRF_K + ev["components"]["lexical_rank"]) + R._GRAPH_WEIGHT / (
                R._RRF_K + ev["components"]["graph_rank"]
            )
            # Cross-check the recomputed raw floats against the public API's
            # rounded emissions — a mismatch means this generator drifted.
            assert round(bm25, 6) == ev["components"]["bm25"], (query, m.path)
            assert round(fused, 6) == ev["score"], (query, m.path)
            matches.append(
                {
                    "path": m.path,
                    "id": m.id,
                    "type": m.type,
                    "field": ev["field"],
                    "terms": ev["terms"],
                    "tier": ev["tier"],
                    "section": m.section,
                    "snippet": m.snippet,
                    "lexical_rank": ev["components"]["lexical_rank"],
                    "graph_rank": ev["components"]["graph_rank"],
                    "inbound": ev["components"]["inbound"],
                    "bm25_bits": bits(bm25),
                    "fused_bits": bits(fused),
                }
            )

        cases.append(
            {
                "query": query,
                "type": artifact_type,
                "tags": list(tags) if tags else [],
                "decisions": decisions,
                "terms": terms,
                "n": n,
                "df": {t: df[t] for t in sorted(df)},
                "avglen_bits": {name: bits(avglen[name]) for name in avglen},
                "match_count": result.match_count,
                "matches": matches,
            }
        )

    payload = {
        "regenerable": True,
        "directory": DIRECTORY,
        "entry_count": len(entries),
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(c["match_count"] for c in cases)
    print(f"wrote {OUT} ({len(cases)} queries, {total} pinned matches)")


if __name__ == "__main__":
    main()
