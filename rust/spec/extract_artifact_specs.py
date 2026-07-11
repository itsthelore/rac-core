#!/usr/bin/env python3
"""Generate rust/spec/artifact-specs.json from the Python engine's specs.

A derived copy for the native-engine spike (roadmap:native-engine-spike):
reads ``rac.core.artifacts`` without modifying it and serialises
``ARTIFACT_SPECS`` (plus the relationship-section metadata the specs lean
on) to a language-neutral JSON file the Rust engine loads at build time.

This is a spike stand-in for the mainline artifact-specs-extraction item
(ADR-063 gate 1), where the Python engine itself would read the file. Here
Python stays the source of truth and this file is regenerated, never
hand-edited. Field order is the dataclass field order; spec order is the
``ARTIFACT_SPECS`` tuple order — both are contract surface for the Rust
loader and for diffing regenerations.

Usage: .venv-oracle/bin/python rust/spec/extract_artifact_specs.py
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from rac.core.artifacts import ARTIFACT_SPECS, RELATIONSHIP_DESCRIPTIONS


def spec_to_dict(spec) -> dict:
    out = {}
    for f in dataclasses.fields(spec):
        value = getattr(spec, f.name)
        if isinstance(value, tuple):
            value = list(value)
        elif isinstance(value, dict):
            value = {
                k: (list(v) if isinstance(v, tuple) else v) for k, v in value.items()
            }
        out[f.name] = value
    return out


def main() -> None:
    payload = {
        "generated_by": "rust/spec/extract_artifact_specs.py",
        "source": "rac.core.artifacts",
        "artifact_specs": [spec_to_dict(s) for s in ARTIFACT_SPECS],
        "relationship_descriptions": dict(RELATIONSHIP_DESCRIPTIONS),
    }
    target = Path(__file__).resolve().parent / "artifact-specs.json"
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {target} ({len(payload['artifact_specs'])} specs)")


if __name__ == "__main__":
    main()
