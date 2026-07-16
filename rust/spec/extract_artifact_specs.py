#!/usr/bin/env python3
"""Drift gate for the shared artifact-spec registry (ADR-063 Guard 1).

Historically this script *generated* ``rust/spec/artifact-specs.json`` from the
Python engine — the spec was one-directional, extracted from Python and read
only by Rust. Guard 1 inverted that: ``src/rac/spec/artifact-specs.json`` is now
the single shared, language-neutral source both engines read (Python loads
``ARTIFACT_SPECS`` from it at import; the Rust engine embeds the same bytes via
``include_str!``).

With the file as the source, drift can no longer happen *between an engine and
the file* — both read it. What this gate guards instead is that the shared file
still reconstructs the exact registry the engine contract expects: it loads the
file the way ``rac.core.artifacts`` does, re-derives the ordered dataclass shape,
and checks it against the live ``ARTIFACT_SPECS`` (same object, so this also
proves the loader stays wired to the shared file) and against the frozen oracle
golden vector ``rust/rac-engine/tests/vectors/spec.json``. Any hand-edit of the
shared file that changes a section, enum, order, or description is caught here.

The upstream source of truth is ``itsthelore/rac-spec``; the in-repo shared file
is the vendored copy. A separate cross-repo sync check (see the ADR) keeps the
two byte-identical.

Usage: .venv-oracle/bin/python rust/spec/extract_artifact_specs.py
Exit 0 = no drift; exit 1 = the shared file disagrees with the registry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rac.core.artifacts import ARTIFACT_SPECS, RELATIONSHIP_DESCRIPTIONS

REPO = Path(__file__).resolve().parents[2]
SHARED = REPO / "src/rac/spec/artifact-specs.json"
GOLDEN = REPO / "rust/rac-engine/tests/vectors/spec.json"


def _spec_rows(specs) -> list:
    return [
        {
            "name": s.name,
            "display": s.display,
            "required": list(s.required),
            "recommended": list(s.recommended),
            "optional": list(s.optional),
            "metadata": [[k, list(v)] for k, v in s.metadata.items()],
            "retired_status": list(s.retired_status),
            "descriptions": [[k, v] for k, v in s.descriptions.items()],
            "guidance": [[k, list(v)] for k, v in s.guidance.items()],
            "synonyms": [[k, v] for k, v in s.synonyms.items()],
            "id_field": s.id_field,
            "starter_bodies": [[k, v] for k, v in s.starter_bodies.items()],
            "expected": list(s.expected),
        }
        for s in specs
    ]


def main() -> int:
    payload = json.loads(SHARED.read_text(encoding="utf-8"))

    # 1. The shared file carries the two registry keys the engines consume.
    if set(payload) < {"artifact_specs", "relationship_descriptions"}:
        print(f"FAIL: {SHARED} missing a registry key", file=sys.stderr)
        return 1

    # 2. The live registry (loaded from the shared file) matches the frozen
    #    oracle golden vector — pins section sets, enums, order, descriptions.
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    live = _spec_rows(ARTIFACT_SPECS)
    if live != golden["artifact_specs"]:
        print("FAIL: ARTIFACT_SPECS drifted from the oracle golden vector", file=sys.stderr)
        return 1
    if [s.name for s in ARTIFACT_SPECS] != golden["names"]:
        print("FAIL: spec order drifted", file=sys.stderr)
        return 1

    # 3. Relationship descriptions round-trip in order.
    if list(RELATIONSHIP_DESCRIPTIONS.items()) != list(
        payload["relationship_descriptions"].items()
    ):
        print("FAIL: relationship descriptions drifted", file=sys.stderr)
        return 1

    print(
        f"OK: shared registry {SHARED.name} reconstructs the oracle registry "
        f"({len(ARTIFACT_SPECS)} specs, {len(RELATIONSHIP_DESCRIPTIONS)} relationship descriptions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
