#!/usr/bin/env python
"""Generate validation test vectors from the Python oracle.

Drives rac.core.validation over every Markdown file in the live corpus and
the test fixtures, dumping the flat finding list for three configurations:

- bare:      validate(product)                        (no provider, no overrides)
- github:    validate(product, ticketing_provider="github")
- product:   validate_product(product, start=<file's parent>)  (repo config
             applied — ticketing provider + severity overrides, ADR-053)

Run with the oracle venv:
    .venv-oracle/bin/python rust/spec/gen_vectors_validate.py

Output (committed):
    rust/rac-engine/tests/vectors/validate.json

File paths are relative to rust/rac-engine (the cwd of `cargo test`); this
script chdirs there so the oracle sees identical path strings.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.chdir(REPO / "rust" / "rac-engine")

from rac.core.markdown import parse_file  # noqa: E402
from rac.core.validation import validate  # noqa: E402
from rac.services.validate import validate_product  # noqa: E402


def corpus_paths() -> list[str]:
    out: list[str] = []
    for root in ("rac", "tests"):
        base = REPO / root
        for p in sorted(base.rglob("*.md")):
            rel = p.relative_to(REPO)
            if any(part.startswith(".") for part in rel.parts):
                continue
            out.append("../../" + rel.as_posix())
    return out


def issue_rows(issues) -> list[list]:
    return [[i.severity, i.code, i.message, i.line] for i in issues]


def main() -> None:
    cases = []
    for path in corpus_paths():
        product = parse_file(path)
        cases.append(
            {
                "path": path,
                "bare": issue_rows(validate(product)),
                "github": issue_rows(validate(product, ticketing_provider="github")),
                "product": issue_rows(
                    validate_product(product, start=str(Path(path).parent))
                ),
            }
        )
    out = REPO / "rust" / "rac-engine" / "tests" / "vectors" / "validate.json"
    out.write_text(json.dumps({"cases": cases}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
