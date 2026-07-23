#!/usr/bin/env python
"""Generate mdhtml (body_html) test vectors from the Python oracle.

Drives markdown-it-py 4.2.0 exactly as asdecided.services.export does
(`MarkdownIt("commonmark", {"html": False})`) over a C0-control-char grid —
every char U+0001-U+001F at every block position where Python `str.strip()`
semantics can diverge from ASCII trimming (markdown-it-py strips
heading/lheading/paragraph inline content with `str.strip()`, whose
whitespace set includes U+001C-U+001F; fuzz campaign 2, findings 009/036/039)
— for byte-exact replay by rust/rac-engine/tests/mdhtml_vectors.rs against
rac_engine::mdhtml::render.

Run with the oracle venv:
    .venv-oracle/bin/python rust/spec/gen_vectors_mdhtml.py

Output (committed):
    rust/rac-engine/tests/vectors/mdhtml.json
"""

from __future__ import annotations

import json
import os

from markdown_it import MarkdownIt

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VEC_DIR = os.path.join(REPO, "rust", "rac-engine", "tests", "vectors")

MD = MarkdownIt("commonmark", {"html": False})

CASES = []
NAMES = set()


def T(name, text):
    assert name not in NAMES, name
    NAMES.add(name)
    CASES.append({"name": name, "text": text, "html": MD.render(text)})


# The exact finding-039 repro body (list item followed by a line holding only
# U+001E, which Python str.strip() treats as whitespace).
T("finding-039-repro", "## Outcomes\n## Initiatives\n- PEW\n\x1e")
# Finding 036 shape (heading grid below generalizes it).
T("finding-036-repro", "## Context\n## Decision\n## Consequences\x0b")

# ---------------------------------------------------------------------------
# C0 grid: U+0001-U+001F x block positions.
#
# Positions cover the strip seams (tight/loose list items — bullet, ordered,
# nested — paragraphs, ATX and setext headings, blockquotes) at line starts,
# line ends, mid-line, and as whole trailing/interior lines.
# ---------------------------------------------------------------------------

POSITIONS = [
    ("li-trail-line", "- PEW\n{c}"),
    ("li-trail-line-nl", "- PEW\n{c}\n"),
    ("li-lead", "- {c}PEW\n"),
    ("li-end", "- PEW{c}\n"),
    ("li-line-between-items", "- PEW\n{c}\n- Q\n"),
    ("li-mid-content", "- PEW\n{c}X\n"),
    ("li-loose-trail", "- PEW\n\n- Q\n{c}"),
    ("ol-trail-line", "1. PEW\n{c}"),
    ("nested-li-trail", "- a\n  - PEW\n{c}"),
    ("bq-li-trail", "> - PEW\n> {c}\n"),
    ("para-trail-line", "PEW\n{c}"),
    ("para-lead", "{c}PEW\n"),
    ("para-interior-line", "PEW\n{c}\nQ\n"),
    ("para-inline", "PE{c}W\n"),
    ("para-only", "{c}\n"),
    ("atx-line-after", "# PEW\n{c}"),
    ("atx-inline-both", "# {c}PEW{c}\n"),
    ("setext-lead-trail", "{c}PEW{c}\n===\n"),
    ("bq-trail-line", "> PEW\n> {c}\n"),
]

for cp in range(0x01, 0x20):
    c = chr(cp)
    for pos, template in POSITIONS:
        T(f"c0-{cp:02x}-{pos}", template.format(c=c))

with open(os.path.join(VEC_DIR, "mdhtml.json"), "w", encoding="utf-8") as fh:
    json.dump({"cases": CASES}, fh, ensure_ascii=True, separators=(",", ":"))
    fh.write("\n")

print(f"mdhtml cases: {len(CASES)}")
