#!/usr/bin/env python
"""Generate classification test vectors from the Python oracle.

Drives rac.core.classification over every Markdown file in the live corpus
(rac/) and the test fixtures (tests/), dumping the full score breakdown and
the chosen classification for byte-exact replay by the Rust port
(rust/rac-engine/tests/classify_vectors.rs).

Run with the oracle venv:
    .venv-oracle/bin/python rust/spec/gen_vectors_classify.py

Output (committed):
    rust/rac-engine/tests/vectors/classify.json

File paths are relative to rust/rac-engine (the cwd of `cargo test`); this
script chdirs there so the oracle sees identical path strings.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Walk the frozen snapshot (COUNCIL-REVIEW B3), not the live `rac/`/`tests/`, so
# a docs commit no longer invalidates the cargo suite. Run from the snapshot
# root and emit "rac/..."/"tests/..." paths — identical to the live tree, so
# the Rust test (which chdirs here too) reads the same strings.
CORPUS_ROOT = REPO / "rust" / "fixtures" / "corpus"
os.chdir(CORPUS_ROOT)

from rac.core.classification import classify, score_artifacts  # noqa: E402
from rac.core.markdown import parse_file  # noqa: E402


def corpus_paths() -> list[str]:
    out: list[str] = []
    for root in ("rac", "tests"):
        base = CORPUS_ROOT / root
        for p in sorted(base.rglob("*.md")):
            rel = p.relative_to(CORPUS_ROOT)
            if any(part.startswith(".") for part in rel.parts):
                continue
            out.append(rel.as_posix())
    return out


def main() -> None:
    cases = []
    for path in corpus_paths():
        product = parse_file(path)
        scores = score_artifacts(product)
        c = classify(product)
        cases.append(
            {
                "path": path,
                "type": c.type,
                # repr() of the rounded double — the exact value the JSON
                # writer would emit; compared against py_float_repr(py_round).
                "confidence_repr": repr(c.confidence),
                "present_sections": c.present_sections,
                "missing_sections": c.missing_sections,
                "scores": [
                    {
                        "name": s.name,
                        "matched_required": s.matched_required,
                        "matched_recommended": s.matched_recommended,
                        "missing": s.missing,
                        "points_repr": repr(s.points),
                        "ceiling_repr": repr(s.ceiling),
                        "fit_repr": repr(s.fit),
                    }
                    for s in scores
                ],
            }
        )
    out = REPO / "rust" / "rac-engine" / "tests" / "vectors" / "classify.json"
    out.write_text(json.dumps({"cases": cases}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
