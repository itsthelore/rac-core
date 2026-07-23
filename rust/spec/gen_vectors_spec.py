#!/usr/bin/env python3
"""Generate artifact-spec test vectors from the live oracle registry.

Dumps `asdecided.core.artifacts.ARTIFACT_SPECS` (and the canonical
`RELATIONSHIP_SECTIONS`) in a stable, order-preserving JSON shape. The Rust
test loads the embedded `artifact-specs.json`, then asserts every field matches
this vector — so a drift between the embedded copy, the live Python registry,
and the Rust load is caught in one place.

Run with the oracle venv:
    .venv-oracle/bin/python rust/spec/gen_vectors_spec.py
"""

from __future__ import annotations

import json
from pathlib import Path

from asdecided.core.artifacts import ARTIFACT_SPECS
from asdecided.services.references import RELATIONSHIP_SECTIONS

OUT = Path(__file__).resolve().parents[1] / "rac-engine/tests/vectors/spec.json"


def spec_to_dict(s) -> dict:
    return {
        "name": s.name,
        "display": s.display,
        "required": list(s.required),
        "recommended": list(s.recommended),
        "optional": list(s.optional),
        # metadata / guidance / starter_bodies / descriptions / synonyms are
        # ordered maps — emit as ordered [key, value] pairs to pin iteration.
        "metadata": [[k, list(v)] for k, v in s.metadata.items()],
        "retired_status": list(s.retired_status),
        "descriptions": [[k, v] for k, v in s.descriptions.items()],
        "guidance": [[k, list(v)] for k, v in s.guidance.items()],
        "synonyms": [[k, v] for k, v in s.synonyms.items()],
        "id_field": s.id_field,
        "starter_bodies": [[k, v] for k, v in s.starter_bodies.items()],
        "expected": list(s.expected),
    }


def main() -> None:
    payload = {
        "artifact_specs": [spec_to_dict(s) for s in ARTIFACT_SPECS],
        "names": [s.name for s in ARTIFACT_SPECS],
        "relationship_sections": list(RELATIONSHIP_SECTIONS),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(payload['artifact_specs'])} specs)")


if __name__ == "__main__":
    main()
