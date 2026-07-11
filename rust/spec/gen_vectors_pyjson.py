#!/usr/bin/env python3
"""Generate oracle test vectors for rust/rac-engine/src/pyjson.rs.

Run with the oracle venv python (.venv-oracle/bin/python). Output is
deterministic: rust/rac-engine/tests/vectors/pyjson.json.

Each row: {"doc": <value>, "indent2": json.dumps(doc, indent=2),
"compact": json.dumps(doc, ensure_ascii=False)} — the two RAC dialects
(PORT-CONTRACT.d/07 §1). The doc itself round-trips through this file's
own JSON encoding; the int/float distinction survives (2 vs 2.0) because
serde_json preserves it at parse time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "rac-engine" / "tests" / "vectors" / "pyjson.json"

DOCS = [
    # scalars
    None, True, False, 0, 1, -1, 42, -9007199254740993, 2**63 - 1, 2**64 - 1,
    0.0, -0.0, 1.0, 2.0, 0.1, 1e-05, 1e20, 100.0, 1234567.0, 0.7, 3.3, 0.33,
    2.675, 5e-324, 9999999999999998.0, 123456789012345.6, 0.8571428571428571,
    -1e-05, 0.30000000000000004,
    "", "plain", "with \"quotes\"", "back\\slash", "tab\there\nnewline\rcr",
    "control\x00\x01\x1f\x08\x0c", "del\x7f", "café ünïcode →",
    "汉字 한글 עברית", "🎉 astral 𝔘", "em—dash ↳ ✗ ✅ ⚠️", "\xa0\xad",
    "/slash</script>", "​zwsp﻿bom",
    # containers
    [], {}, [[]], [{}], {"a": []}, {"a": {}}, [1], [1, 2, 3],
    ["a", "b"], [None, True, False], [0.1, 1, "x", None],
    {"a": 1}, {"a": 1, "b": 2}, {"b": 2, "a": 1},
    {"z": 1, "y": 2, "x": 3, "a": 4},   # insertion order, never sorted
    {"key with space": 1, "ключ": 2, "🎊": 3, "tab\tkey": 4},
    {"empty_list": [], "empty_dict": {}, "nested": {"deep": {"deeper": []}}},
    [[1, [2, [3, [4]]]]],
    {"a": [1, {"b": [2, {"c": []}]}]},
    # RAC-shaped payloads
    {
        "path": "rac/decisions/ADR-001-markdown-first.md",
        "id": "RAC-KTQ63DPSMF19",
        "type": "decision",
        "title": "ADR-001 Markdown First",
        "valid": True,
        "issues": [],
        "confidence": 0.8571428571428571,
        "tags": ["architecture", "markdown"],
    },
    {
        "summary": {
            "total": 417,
            "valid": 417,
            "invalid": 0,
            "average_requirements_per_feature": 3.3,
        },
        "unrecognized": {"count": 1, "files": [{"path": "notes — draft.md", "confidence": 0.67}]},
    },
    {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "rac",
                        "informationUri": "https://github.com/itsthelore/rac-core",
                        "version": "0.1.dev50+g21c8be403",
                        "rules": [{"id": "REL001"}, {"id": "VAL002"}],
                    }
                },
                "results": [
                    {
                        "ruleId": "VAL002",
                        "level": "warning",
                        "message": {"text": "missing field: 'status'"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "rac/caf%C3%A9%20note.md"},
                                    "region": {"startLine": 3},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    },
    {
        "id": "RAC-KTQ63DPSMF19",
        "title": "Décision — naïve résumé 🎉",
        "body": "line one\nline two\ttabbed\n",
        "score": 0.024390243902439025,
        "fused": 0.03278688524590164,
        "counts": {"requirements": 12, "decisions": 0},
    },
    # float/int edge mixes
    {"int": 2, "float": 2.0, "neg_zero": -0.0, "tiny": 5e-324, "big": 1e20},
    [1.0, 1, -1.0, -1, 0.5, 2, 1e16, 10000000000000000],
    {"scores": [0.1, 0.2, 0.30000000000000004]},
    # deep-ish nesting for indent arithmetic
    {"a": {"b": {"c": {"d": {"e": [1, 2, {"f": "g", "h": []}]}}}}},
    ["mixed", {"k": [True, None, 0.1, "🎈"]}, [], {}],
]

rows = [
    {
        "doc": doc,
        "indent2": json.dumps(doc, indent=2),
        "compact": json.dumps(doc, ensure_ascii=False),
    }
    for doc in DOCS
]

payload = {
    "generated_by": "rust/spec/gen_vectors_pyjson.py",
    "python": sys.version.split()[0],
    "rows": rows,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=1) + "\n")
print(f"wrote {OUT}: {len(rows)} rows")
