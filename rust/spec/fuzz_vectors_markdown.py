#!/usr/bin/env python
"""Differential fuzz for the markdown port (phase-3 hook).

Generates seeded-random Markdown documents from a pool of block-structure
tokens, runs the oracle, and writes them in the markdown.json case schema to
rust/rac-engine/tests/vectors/markdown_fuzz.json (NOT committed). The Rust
test `markdown_fuzz.rs` replays the file when present and skips when absent.

Usage:
    .venv-oracle/bin/python rust/spec/fuzz_vectors_markdown.py [n_cases] [seed]
"""

from __future__ import annotations

import json
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE_DIR = os.path.join(REPO, "rust", "rac-engine")
os.chdir(ENGINE_DIR)
os.environ.pop("DECIDED_MAX_FILE_BYTES", None)

from asdecided.core import markdown as md  # noqa: E402
from asdecided.core.frontmatter import split_frontmatter  # noqa: E402

def product_value(p, text=None):
    """Same shape as gen_vectors_markdown.product_value (kept in sync)."""
    if text is not None:
        split = split_frontmatter(text)
        fm_raw = split.raw
        meta_issues = (
            [
                [
                    "error",
                    "malformed-frontmatter",
                    "frontmatter block opened with --- on line 1 but never closed",
                    1,
                ]
            ]
            if split.raw is None and split.unterminated
            else []
        )
    else:
        fm_raw = None
        meta_issues = []
    return {
        "title": p.title,
        "extra_title_lines": list(p.extra_title_lines),
        "problem": p.problem,
        "requirements": [[r.id, r.text, r.line] for r in p.requirements],
        "malformed_requirements": [
            [m.raw, m.line, m.bad_id, m.empty_text] for m in p.malformed_requirements
        ],
        "success_metrics": list(p.success_metrics),
        "risks": list(p.risks),
        "sections": [[k, v] for k, v in p.sections.items()],
        "search_sections": [[s.heading, list(s.lines)] for s in p.search_sections],
        "has": [
            p.has_problem_section,
            p.has_requirements_section,
            p.has_metrics_section,
            p.has_risks_section,
        ],
        "source_path": p.source_path,
        "frontmatter_raw": fm_raw,
        "metadata_issues": meta_issues,
        "parse_issues": [[i.severity, i.code, i.message, i.line] for i in p.parse_issues],
    }


def events_value(body):
    tokens = md._PARSER.parse(body)
    events = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            content = tokens[i + 1].content if i + 1 < len(tokens) else ""
            events.append(["h", tok.tag, tok.map[0] if tok.map else -1, content])
        elif tok.type == "inline" and not (i > 0 and tokens[i - 1].type == "heading_open"):
            events.append(["b", "", tok.map[0] if tok.map else -1, tok.content])
    return events

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 20260711

POOL = [
    "# ", "## ", "### ", "#### ", "###### ", "####### ", "#", "##",
    "> ", ">", ">> ", "- ", "* ", "+ ", "1. ", "1) ", "2. ", "10. ",
    "```", "~~~", "```py", "    ", "   ", "\t", " \t", "---", "===", "- - -",
    "___", "***",
    "Problem", "Requirements", "Success Metrics", "Risks", "PROBLEM",
    "problemß", "İstanbul", "Riſks", "title", "text words here", "lazy",
    "[REQ-001] desc", "[REQ-1A] bad", "[] none", "[ REQ-002 ]  d ",
    "[REQ-١٢٣] arabic", "[label]: /url", "[label]: <de st>", "[x]: javascript:x",
    "[x]: /u \"t", "\"title\"", "'t'", "(t)",
    "<!--", "-->", "<div>", "</div>", "<script>", "</script>", "<?", "?>",
    "<!X", "<![CDATA[", "]]>", "<custom-tag a=b>", "<pre>", "</pre>",
    "&colon;", "&amp;", "&#58;", "\\#", "\\[", "`code`", "**b**", "* i *",
    " ", "\x1c", "\x1f", "\x0b", "\x00", "\x85", " ", "ß", "é",
    "[", "]", ":", "(", ")", "<", ">", "\\",
]
SEP = ["", " ", "  ", "\t"]
EOL = ["\n", "\n", "\n", "\r\n", "\r", "\n\n"]

rng = random.Random(SEED)
cases = []
for i in range(N):
    n_lines = rng.randint(1, 14)
    parts = []
    for _ in range(n_lines):
        n_tok = rng.randint(1, 5)
        line = rng.choice(SEP).join(rng.choice(POOL) for _ in range(n_tok))
        parts.append(line + rng.choice(EOL))
    if rng.random() < 0.15:
        parts.insert(0, "---\nkey: v\n---\n" if rng.random() < 0.7 else "---\n")
    text = "".join(parts)
    if rng.random() < 0.1:
        text = text.rstrip("\n")
    product = md.parse(text, source_path="")
    split = split_frontmatter(text)
    cases.append(
        {
            "name": f"fuzz-{SEED}-{i:05d}",
            "kind": "text",
            "text": text,
            "cap": None,
            "source_path": "",
            "split": {
                "raw": split.raw,
                "line_offset": split.line_offset,
                "unterminated": split.unterminated,
            },
            "events": events_value(split.body),
            "product": product_value(product, text=text),
        }
    )

out = os.path.join(ENGINE_DIR, "tests", "vectors", "markdown_fuzz.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"cases": cases}, fh, ensure_ascii=True, separators=(",", ":"))
    fh.write("\n")
print(f"wrote {len(cases)} fuzz cases to {out}")
