#!/usr/bin/env python
"""Generate markdown-module test vectors from the Python oracle.

Drives rac.core.markdown (markdown-it-py 4.2.0 block parsing + the section
walk) over synthetic contract edge cases and the full live corpus, dumping
the complete extracted structure for byte-exact replay by the Rust port
(rust/rac-engine/tests/markdown_vectors.rs).

Run with the oracle venv:
    .venv-oracle/bin/python rust/spec/gen_vectors_markdown.py

Outputs (committed):
    rust/rac-engine/tests/vectors/markdown.json         (synthetic cases)
    rust/rac-engine/tests/vectors/markdown_corpus.json  (live corpus products)

File-kind cases use paths relative to rust/rac-engine (the cwd of `cargo
test`); this script chdirs there so the oracle sees identical path strings.
"""

from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE_DIR = os.path.join(REPO, "rust", "rac-engine")
VEC_DIR = os.path.join(ENGINE_DIR, "tests", "vectors")
FILES_DIR = os.path.join(VEC_DIR, "files")

os.makedirs(FILES_DIR, exist_ok=True)
os.chdir(ENGINE_DIR)
os.environ.pop("RAC_MAX_FILE_BYTES", None)

from rac.core import limits  # noqa: E402
from rac.core import markdown as md  # noqa: E402
from rac.core.frontmatter import split_frontmatter  # noqa: E402


def product_value(p, text=None):
    """Dump a Product in the exact shape the Rust test rebuilds.

    ``text`` is the decoded document text when known (None for degraded
    file products); frontmatter_raw / metadata_issues (unterminated only)
    are derived from split_frontmatter so parse_frontmatter's own issues
    (the WS2 frontmatter module's concern) never enter this vector.
    """
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
    """The consumed token surface: heading_open(tag, line, inline text) and
    body inline (line, raw content) events, in stream order."""
    tokens = md._PARSER.parse(body)
    events = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            content = tokens[i + 1].content if i + 1 < len(tokens) else ""
            events.append(["h", tok.tag, tok.map[0] if tok.map else -1, content])
        elif tok.type == "inline" and not (i > 0 and tokens[i - 1].type == "heading_open"):
            events.append(["b", "", tok.map[0] if tok.map else -1, tok.content])
    return events


CASES = []
NAMES = set()


def T(name, text, cap=None, source_path="", events=True):
    assert name not in NAMES, name
    NAMES.add(name)
    if cap is not None:
        os.environ["RAC_MAX_FILE_BYTES"] = str(cap)
    try:
        product = md.parse(text, source_path=source_path)
    finally:
        os.environ.pop("RAC_MAX_FILE_BYTES", None)
    split = split_frontmatter(text)
    case = {
        "name": name,
        "kind": "text",
        "text": text,
        "cap": cap,
        "source_path": source_path,
        "split": {
            "raw": split.raw,
            "line_offset": split.line_offset,
            "unterminated": split.unterminated,
        },
        "events": events_value(split.body) if events else None,
        "product": product_value(product, text=text),
    }
    CASES.append(case)


def F(name, path, cap=None, degraded=False):
    assert name not in NAMES, name
    NAMES.add(name)
    if cap is not None:
        os.environ["RAC_MAX_FILE_BYTES"] = str(cap)
    try:
        product = md.parse_file(path)
    finally:
        os.environ.pop("RAC_MAX_FILE_BYTES", None)
    text = None
    if not degraded:
        with open(path, "rb") as fh:
            data = fh.read()
        text = data.decode("utf-8", errors="replace")
    CASES.append(
        {
            "name": name,
            "kind": "file",
            "path": path,
            "cap": cap,
            "product": product_value(product, text=text),
        }
    )


def C(name, raw):
    """max_file_bytes() with RAC_MAX_FILE_BYTES set to `raw` (None = unset)."""
    assert name not in NAMES, name
    NAMES.add(name)
    if raw is None:
        os.environ.pop("RAC_MAX_FILE_BYTES", None)
    else:
        os.environ["RAC_MAX_FILE_BYTES"] = raw
    try:
        cap = limits.max_file_bytes()
    finally:
        os.environ.pop("RAC_MAX_FILE_BYTES", None)
    CASES.append({"name": name, "kind": "cap", "raw": raw, "expected": str(cap)})


# ---------------------------------------------------------------------------
# Group A — ATX headings
# ---------------------------------------------------------------------------

ATX_LINES = [
    "# Title",
    "## Risks",
    "### deep",
    "#### four",
    "##### five",
    "###### six",
    "####### seven",
    "#nospace",
    "#5 bolts",
    "#",
    "##",
    "###",
    "## Risks ##",
    "## Risks ####   ",
    "## Risks #",
    "## Risks # trailing words",
    "## Risks #x",
    "## Risks ##\t",
    "#\tFoo",
    "#\t",
    "# \t mixed \t ",
    "## has \\# escaped",
    "\\## not heading",
    "## **Bold** `code` [link](x) *em*",
    "## AT&amp;T &#65;",
    "##   ",
    "## text #closer# not",
    "##\ttab text\t##",
    "#place # hash # runs #",
    "# # #",
]
for i, line in enumerate(ATX_LINES):
    T(f"atx-{i:02d}", line + "\n\nbody text\n")
for i, lead in enumerate([" ", "  ", "   ", "    ", "\t", " \t"]):
    T(f"atx-indent-{i}", lead + "## Indented\n\nbody\n")
T("atx-eof-no-newline", "## Risks")
T("atx-only-hashes-eof", "##")
T("atx-crlf-heading", "## Risks ##\r\n\r\nbody\r\n")

# ---------------------------------------------------------------------------
# Group B — document skeletons / walk semantics
# ---------------------------------------------------------------------------

CANONICAL = """# Product X

## Problem

Users cannot export data.
It hurts adoption.

## Requirements

[REQ-001] User can export CSV
[REQ-002] User can export JSON

## Success Metrics

Export usage > 50%

## Risks

Export may be slow
"""
T("doc-canonical", CANONICAL)
T("doc-canonical-crlf", CANONICAL.replace("\n", "\r\n"))
T("doc-canonical-cr", CANONICAL.replace("\n", "\r"))
T("doc-no-title", CANONICAL.replace("# Product X\n\n", ""))
T("doc-two-titles", "# One\n\ncontent under h1\n\n# Two\n\n## Problem\n\ntext\n")
T("doc-empty-title-blocks", "#\n\n# Real Title\n\nbody\n")
T("doc-title-only", "# Just Title\n")
T("doc-h3-under-h2", "# T\n\n## Problem\n\np1\n\n### Sub\n\np2 under h3\n\n## Risks\n\nr1\n")
T("doc-h3-before-h2", "# T\n\n### Early\n\ndropped text\n\n## Problem\n\nkept\n")
T("doc-h1-resets", "# T\n\n## Problem\n\np1\n\n# Mid Title\n\nlost text\n\n## Risks\n\nr1\n")
T("doc-content-before-heading", "leading paragraph\n\n# T\n\n## Problem\n\nx\n")
T(
    "doc-duplicate-problem",
    "# T\n\n## Problem\n\nfirst\n\n## PROBLEM\n\nsecond\n\n## problem \n\nthird\n",
)
T("doc-empty-sections", "# T\n\n## Problem\n\n## Requirements\n\n## Risks\n")
T("doc-empty-h2-heading", "# T\n\n##\n\nunder empty heading\n\n## Problem\n\nx\n")
T("doc-only-h2s", "## Alpha\n\na\n\n## Beta\n\nb\n\n## Alpha\n\nmerged\n")
T("doc-success-metrics-case", "# T\n\n## SUCCESS METRICS\n\nm1\n\n## sUcCeSs MeTrIcS\n\nm2\n")
T("doc-unrecognized-sections", "# T\n\n## Overview\n\no1\no2\n\n## Notes\n\nn1\n")
T("doc-h2-inline-markup-problem", "# T\n\n## `Problem`\n\nnot recognized\n")
T("doc-h2-problem-colon", "# T\n\n## Problem:\n\nnot recognized either\n")
T("doc-multiline-paragraph", "## Notes\n\nline one\nline two  \nline three\\\nline four\thard\n")
T("doc-hard-breaks-in-problem", "## Problem\n\nfoo  \n  bar\\\nbaz  \nqux\n")

# casefold traps
T("fold-problem-eszett", "## PROBLEMß\n\nx\n")
T("fold-eszett-section", "## Straße\n\nx\n")
T("fold-istanbul", "## İstanbul\n\nx\n")
T("fold-sigma", "## ΠΡΟΒΛΗΜΑΣ\n\nx\n")
T("fold-kelvin-risks", "## RISKSK\n\nx\n")
T("fold-longs-risks", "## Riſks\n\nx\n")  # 'ſ' casefolds to 's' -> "risks"!
T("fold-problem-upper", "## PROBLEM\n\nupper recognized\n")

# python-whitespace strip traps (U+001C-U+001F, NBSP, U+0085)
T("ws-1c-heading", "## \x1cProblem\x1f\n\nx\n")
T("ws-1d-1e-heading", "## \x1d\x1eRisks\x1d\n\nrisk line\n")
T("ws-nbsp-trailing", "## Problem \n\nx\n")
T("ws-nbsp-interior", "## Problem x\n\nx\n")
T("ws-85-heading", "## Requirements\n\n[REQ-001] a\n")
T("ws-body-1c", "## Problem\n\n\x1cpadded line\x1f\n")
T("ws-body-vt-ff", "## Problem\n\n\x0bline with vt\x0c\n")
T("ws-2028-in-line", "## Problem\n\nbefore after\n")
T("ws-bom-start", "\ufeff# Title\n\n## Problem\n\nx\n")
T("ws-200b", "## Problem\u200b\n\nx\n")

# NUL
T("nul-in-heading", "## Prob\x00lem\n\nx\n")
T("nul-in-body", "## Problem\n\na\x00b\n")

# ---------------------------------------------------------------------------
# Group C — setext headings
# ---------------------------------------------------------------------------

T("setext-h1", "Title\n=====\n\nbody\n")
T("setext-h2", "Sub\n---\n\nbody\n")
T("setext-h2-single-dash", "Sub\n-\n\nbody\n")
T("setext-trap-paragraph", "Some paragraph\n---\n")
T("setext-trap-problem", "## Problem\nthe text\n---\n")
T("setext-trap-problem-blank", "## Problem\n\nthe text\n---\nafter\n")
T("setext-multiline", "line one\nline two\n===\n\nbody\n")
T("setext-in-list", "- Sub\n  ---\n")
T("setext-in-blockquote", "> Quoted\n> ---\n")
T("setext-underline-spaces", "Title\n===   \n")
T("setext-underline-3-indent", "Title\n   ===\n")
T("setext-underline-4-indent", "Title\n    ===\n\nmore\n")
T("setext-lazy-blockquote", "> start\nlazy\n---\n")
T("setext-eq-vs-dash", "A\n==\n\nB\n--\n")
T("setext-after-blank", "para\n\nTitle\n===\n")
T("setext-dash-space-dash", "Text\n- - -\n")
T("setext-problem-body-dash", "## Problem\n\nreal body\n\n---\n")
T("setext-hr-alone", "---\n")
T("setext-hr-underscores", "___\n\ntext\n")
T("setext-hr-stars", "* * *\n")
T("setext-empty-eq", "===\n")
T("setext-risks-lower", "risks\n---\n\nrisk body?\n")  # phantom 'risks' h2 section!
T("setext-problem-word", "Problem\n=======\n")  # h1 title "Problem"
T("setext-marker-run-space", "Sub\n--- ---\n")  # not setext (space between runs) -> hr? no: '--- ---' -> hr

# ---------------------------------------------------------------------------
# Group D — fenced code blocks
# ---------------------------------------------------------------------------

T("fence-basic", "```\n# hidden heading\n[REQ-001] hidden\n```\n\n## Problem\n\nx\n")
T("fence-tilde", "~~~\n## hidden\n~~~\n\nvisible\n")
T("fence-info", "```python\ncode()\n```\n")
T("fence-info-backtick", "``` a`b\nnot a fence\n```\n")
T("fence-tilde-info-backtick", "~~~ a`b\nstill fence\n~~~\n")
T("fence-unclosed", "```\n## hidden forever\nmore\n")
T("fence-close-shorter", "````\ncode\n```\nstill code\n````\nafter\n")
T("fence-close-longer", "```\ncode\n`````\nafter\n")
T("fence-close-with-info", "```\ncode\n``` x\nstill inside\n```\nout\n")
T("fence-close-trailing-ws", "```\ncode\n```   \nafter\n")
T("fence-indented-3", "   ```\n   code\n   ```\nafter\n")
T("fence-indented-4", "    ```\n    looks like fence\n    ```\n")
T("fence-in-list", "- item\n  ```\n  ## hidden\n  ```\n- next\n")
T("fence-in-blockquote", "> ```\n> ## hidden\n> ```\n")
T("fence-interrupts-paragraph", "para text\n```\ncode\n```\n")
T("fence-two-chars", "``\nnot fence\n``\n")
T("fence-marker-mix", "```\ncode\n~~~\nstill code\n```\nout\n")
T("fence-empty", "```\n```\n")
T("fence-eof-marker", "```")
T("fence-blockquote-outdent", "> ```\ntest\n```\n")

# ---------------------------------------------------------------------------
# Group E — indented code blocks
# ---------------------------------------------------------------------------

T("icode-heading-invisible", "## Requirements\n\n    [REQ-001] x\n")
T("icode-hash-line", "    # not a heading\n\n## Problem\n\nx\n")
T("icode-tab", "\t# tab code\n\nafter\n")
T("icode-lazy-continuation", "para start\n    not code, lazy\n")
T("icode-after-blank", "para\n\n    code line\n    code line 2\nafter\n")
T("icode-mixed-tabs", "  \t# still code\n")
T("icode-blank-interior", "    code a\n\n    code b\nafter\n")
T("icode-in-list-8", "- item\n\n        code in item\n")
T("icode-3-spaces-not-code", "   ## Heading3sp\n")
T("icode-under-section", "## Problem\n\ntext\n\n    coded requirement vanishes\n\nmore text\n")

# ---------------------------------------------------------------------------
# Group F — HTML blocks (7 kinds)
# ---------------------------------------------------------------------------

T("html-pre", "<pre>\n## hidden\n</pre>\n\n## Problem\n\nx\n")
T("html-script", "<script>\nvar x = '## nope';\n</script>\nafter\n")
T("html-script-close-same-line", "<script>alert(1)</script>\npara after\n")
T("html-style-upper", "<STYLE>\n## hidden\n</STYLE>\nafter\n")
T("html-textarea", "<textarea>\n## hidden\n</textarea>\n")
T("html-comment", "<!--\n## hidden\n-->\n\n## Risks\n\nr\n")
T("html-comment-oneline", "<!-- note --> trailing\npara\n")
T("html-pi", "<?php\n## hidden\n?>\nafter\n")
T("html-decl", "<!DOCTYPE html>\npara\n")
T("html-decl-multiline", "<!X\n## hidden\n>\nafter\n")
T("html-cdata", "<![CDATA[\n## hidden\n]]>\nafter\n")
T("html-type6-div", "<div>\n## hidden until blank\n\n## Problem\n\nx\n")
T("html-type6-close", "</div>\ntext continues\n\npara\n")
T("html-type6-attrs", "<div class=\"x\" id='y'>\nhidden\n\nvisible\n")
T("html-type6-self-close", "<hr/>\nhidden line\n\nvisible\n")
T("html-type6-interrupts", "para before\n<div>\nhidden\n\nafter blank\n")
T("html-type7-custom", "<custom-tag attr=\"v\">\nhidden until blank\n\nvisible\n")
T("html-type7-close-tag", "</custom-tag>\nhidden\n\nvisible\n")
T("html-type7-no-interrupt", "para before\n<custom-tag>\nstill same paragraph\n")
T("html-type7-trailing-text", "<custom-tag> trailing\nparagraph (not html block)\n")
T("html-type7-unquoted", "<x-y a=b/>\nhidden\n\nvisible\n")
T("html-type7-bad-attr", "<x-y a=>\nnot a block, paragraph\n")
T("html-invalid-tag", "<1div>\nparagraph\n")
T("html-lt-alone", "<\nparagraph\n")
T("html-eszett-address", "<addreß>\nparagraph or block?\n")
T("html-longs-script", "<ſcript>\nhidden?\n")
T("html-kelvin-lin", "<linK>\nhidden?\n")
T("html-h2-tag", "<h2>\nhidden\n\nvisible\n")
T("html-header-tag", "<header>\nhidden\n\nvisible\n")
T("html-heading-after-comment", "<!-- c -->\n## Problem\n\nx\n")
T("html-indented", "   <div>\nhidden\n\nvisible\n")
T("html-in-blockquote", "> <div>\n> hidden\n\nvisible\n")
T("html-nbsp-attr-sep", "<div class=x>\nline2\n\nafter\n")
T("html-script-nested-section", "## Problem\n\n<script>\n## Risks\n</script>\nstill problem?\n")
T("html-inline-not-block", "text with <b>inline html</b> kept raw\n")

# ---------------------------------------------------------------------------
# Group G — blockquotes
# ---------------------------------------------------------------------------

T("bq-heading", "> ## Risks\n> - risk one\n")
T("bq-problem-section", "> ## Problem\n>\n> quoted problem text\n")
T("bq-nested", ">> deep quote\n>> ## Requirements\n>> [REQ-001] nested req\n")
T("bq-lazy", "> start of quote\nlazy continuation line\n")
T("bq-lazy-setext", "> para\n===\n")
T("bq-empty-line-inside", "> a\n>\n> b\n")
T("bq-terminated-by-heading", "> quote\n## Problem\n\nx\n")
T("bq-terminated-by-hr", "> quote\n---\nafter\n")
T("bq-terminated-by-fence", "> quote\n```\ncode\n```\n")
T("bq-terminated-by-list", "> quote\n- item\n")
T("bq-3-space-indent", "   > indented quote\n")
T("bq-4-space-indent", "    > code not quote\n")
T("bq-no-space", ">tight quote\n")
T("bq-tab-after-marker", ">\ttab quote\n")
T("bq-tab-mod3", "  >\ttab after two spaces\n")
T("bq-marker-only", ">\n")
T("bq-requirements", "> ## Requirements\n> [REQ-001] quoted requirement\n> [bad] line\n")
T("bq-in-list", "- > quoted in list\n  > second line\n")
T("bq-list-inside", "> - one\n> - two\n")
T("bq-empty-then-text", ">\ntext after empty quote line\n")
T("bq-double-space-marker", ">  spaced content\n")
T("bq-outdent-list", "1. anything\n   > current blockquote\n2. checking this line\n")
T("bq-crlf", "> ## Risks\r\n> - risk one\r\n")

# ---------------------------------------------------------------------------
# Group H — lists
# ---------------------------------------------------------------------------

T("list-bullet-dash", "- one\n- two\n")
T("list-bullet-star", "* one\n* two\n")
T("list-bullet-plus", "+ one\n+ two\n")
T("list-marker-change", "- one\n* two\n+ three\n")
T("list-ordered-dot", "1. one\n2. two\n")
T("list-ordered-paren", "1) one\n2) two\n")
T("list-ordered-start-3", "3. three\n4. four\n")
T("list-ordered-10-digits", "1234567890. too many digits\n")
T("list-ordered-9-digits", "123456789. nine digits ok\n")
T("list-heading-inside", "- ## Risks\n- risk-ish item\n")
T("list-heading-nested", "- outer\n  - ## Problem\n    inner text\n")
T("list-requirements", "## Requirements\n\n- [REQ-001] bullet requirement\n- [REQ-002] another\n")
T("list-requirements-ordered", "## Requirements\n\n1. [REQ-001] ordered requirement\n")
T("list-item-5-spaces", "-     five spaces after marker\n")
T("list-item-tab", "-\ttab after marker\n")
T("list-empty-item", "-\n\n    foo\n")
T("list-empty-item-then-text", "-\n  text\n")
T("list-nested-3", "- a\n  - b\n    - c\n")
T("list-loose", "- a\n\n- b\n")
T("list-interrupt-paragraph", "para\n- item\n")
T("list-ordered-interrupt-not-1", "para\n2. item\n")
T("list-ordered-interrupt-1", "para\n1. item\n")
T("list-empty-interrupt", "para\n-\n")
T("list-terminated-by-hr", "- one\n- - -\n- two\n")
T("list-no-space-marker", "-test\n")
T("list-indent-continuation", "- item\n  continued\n\n  second para of item\n")
T("list-outdent-code-special", "  - item 1\n   - item 2\n    - item 3\n     - item 4\n      - paragraph cont\n")
T("list-setext-inside", "- Sub\n  ---\n  after setext in item\n")
T("list-blockquote-inside", "- > quote in item\n")
T("list-tab-content", "- item\n\twith tab continuation\n")
T("list-crlf", "- one\r\n- two\r\n")

# deep nesting to hit maxNesting=20
deep = ""
for d in range(12):
    deep += "  " * 0 + "> " * (d + 1) + f"level {d}\n"
T("nest-blockquotes-12", deep)
T("nest-blockquotes-25", "".join("> " * (d + 1) + f"l{d}\n" for d in range(25)))
T(
    "nest-list-blockquote-heading",
    "- > - > - > - > - > - > - > - > - > - > ## Deep Heading\n",
)
T("nest-max-heading-hidden", "> " * 30 + "## Beyond Cap\n")

# ---------------------------------------------------------------------------
# Group I — reference definitions
# ---------------------------------------------------------------------------

T("ref-basic", "[label]: /url \"title\"\n\n## Problem\n\nx\n")
T("ref-consumes-line", "## Problem\n\n[label]: /url\nremaining text\n")
T("ref-req-landmine", "## Requirements\n\n[REQ-001]: description eaten as reference\n")
T("ref-req-landmine-title", "## Requirements\n\n[REQ-001]: dest \"title\"\n")
T("ref-not-ref-req", "## Requirements\n\n[REQ-001] normal requirement\n")
T("ref-angle-dest", "[foo]: <bar baz>\n\ntext\n")
T("ref-multiline-title", "[foo]: /url \"title\nspanning\nlines\"\n\nafter\n")
T("ref-title-rollback", "[foo]: /url \"title\" garbage\n")
T("ref-dest-only-garbage", "[foo]: /url garbage\n")
T("ref-empty-label", "[]: /url\n")
T("ref-ws-label", "[   ]: /url\n")
T("ref-javascript", "[x]: javascript:alert(1)\n")
T("ref-vbscript", "[x]: VBScript:beep\n")
T("ref-file", "[x]: file:///etc/passwd\n")
T("ref-data-bad", "[x]: data:text/html;base64,x\n")
T("ref-data-image", "[x]: data:image/png;base64,iVBOR\n")
T("ref-entity-colon", "[x]: javascript&colon;alert(1)\n")
T("ref-entity-numeric", "[x]: javascript&#58;alert(1)\n")
T("ref-entity-hex", "[x]: javascript&#x3A;alert(1)\n")
T("ref-entity-unknown", "[x]: proto&nosuchentity;rest\n")
T("ref-backslash-escape", "[x]: dest\\)with\\(parens\n")
T("ref-paren-dest", "[x]: (unbalanced\n")
T("ref-multiline-label", "[foo\nbar]: /url\n\nafter\n")
T("ref-label-newline-escape", "[foo\\\nbar]: /url\n")
T("ref-duplicate", "[a]: /one\n[a]: /two\n\ntext\n")
T("ref-then-heading", "[a]: /url\n## Problem\n\nx\n")
T("ref-in-section-consumed", "## Risks\n\n[risk-ref]: /url\nrisk line after ref\n")
T("ref-nested-bracket", "[a[b]: /url\n")
T("ref-no-colon", "[label] /url\n")
T("ref-title-paren", "[x]: /url (paren title)\n")
T("ref-title-single", "[x]: /url 'single title'\n")
T("ref-dest-control", "[x]: de\x01st\n")
T("ref-33-parens", "[x]: " + "(" * 33 + "d" + ")" * 33 + "\n")
T("ref-in-blockquote", "> [ref]: /url\n> text\n")

# ---------------------------------------------------------------------------
# Group J — tabs / CRLF / unicode
# ---------------------------------------------------------------------------

T("tab-heading-content", "#\tTabbed\ttitle\t\n")
T("tab-list-blockquote", "> -\tlist in quote with tab\n")
T("tab-code-partial-expand", "\t\tfoobar\n")
T("tab-after-two-spaces", "  \tcode via tab stop\n")
T("tab-paragraph-interior", "a\tb\tc\n")
T("crlf-mixed", "## Problem\r\ntext\rmore\nend\r\n")
T("cr-only-doc", "# T\r\r## Problem\rtext\r")
T("unicode-emoji-heading", "## \U0001f600 Emoji\n\nbody\n")
T("unicode-combining-heading", "## étude\n\nx\n")
T("unicode-cyrillic", "## Проблема\n\nтекст\n")
T("unicode-cjk", "## 問題\n\n中文正文\n")
T("unicode-rtl", "## مشكلة\n\nbody\n")
T("unicode-surrogate-pair-title", "# \U0001F4A9 Title\n")
T(
    "req-unicode-digits",
    "## Requirements\n\n[REQ-١٢٣] arabic-indic id\n[REQ-１２] fullwidth id\n[REQ-1٢2] mixed digits\n",
)
T("req-superscript-not-digit", "## Requirements\n\n[REQ-²] superscript two\n")

# ---------------------------------------------------------------------------
# Group K — requirement line classification
# ---------------------------------------------------------------------------

REQ_BODIES = [
    ("plain", "[REQ-001] User can view data"),
    ("spaced", "[ REQ-001 ]   spaced desc  "),
    ("empty-brackets", "[] no id"),
    ("lowercase-id", "[req-1] lower"),
    ("bad-suffix", "[REQ-1A] bad digits"),
    ("no-digits", "[REQ-] nothing"),
    ("empty-desc", "[REQ-001]"),
    ("ws-desc", "[REQ-001]    "),
    ("no-brackets", "REQ-001 without brackets"),
    ("not-at-start", "see [REQ-001] later"),
    ("double-brackets", "[a][b] text"),
    ("nested-close", "[ab]cd] text"),
    ("leading-zero", "[REQ-007] leading zeros ok"),
    ("huge-number", "[REQ-99999999999999999999] huge"),
    ("tab-sep", "[REQ-002]\ttab description"),
    ("nbsp-sep", "[REQ-003] nbsp description"),
    ("fs-sep", "[REQ-004]\x1cfield sep description"),
    ("markup-desc", "[REQ-005] **bold** desc `code`"),
    ("id-interior-space", "[REQ 001] space in id"),
    ("multiline-under", "[REQ-006] first\ncontinuation same paragraph"),
]
for tag_, body in REQ_BODIES:
    T(f"req-{tag_}", f"## Requirements\n\n{body}\n")
T("req-blank-lines-numbering", "## Requirements\n\n[REQ-001] one\n\n\n[REQ-002] two after blanks\n")
T("req-in-loose-list", "## Requirements\n\n- [REQ-001] one\n\n- [REQ-002] two\n")
T("req-line-numbers-nested", "# T\n\n## Requirements\n\npreamble\n[REQ-001] a\n[bad line\n[REQ-002] b\n")

# ---------------------------------------------------------------------------
# Group L — frontmatter
# ---------------------------------------------------------------------------

T("fm-basic", "---\nid: RAC-1\ntype: decision\n---\n# T\n\n## Problem\n\nx\n")
T("fm-dots-closer", "---\nid: RAC-2\n...\n# T\n")
T("fm-unterminated", "---\nid: RAC-3\n# T\n\n## Problem\n\nx\n")
T("fm-empty-block", "---\n---\n# T\n")
T("fm-immediate-dots", "---\n...\nbody\n")
T("fm-opener-spaces", "  ---  \nid: x\n---\n# T\n")
T("fm-closer-spaces", "---\nid: x\n  ...  \n# T\n")
T("fm-crlf", "---\r\nid: RAC-4\r\n---\r\n# T\r\n\r\n## Risks\r\n\r\nr1\r\n")
T("fm-line-offset-reqs", "---\na: 1\nb: 2\n---\n## Requirements\n\n[REQ-001] offset check\n")
T("fm-line-offset-extra-title", "---\nx: y\n---\n# One\n\n# Two\n")
T("fm-not-first-line", "\n---\nnot frontmatter\n---\n")
T("fm-dash-body-setext", "---\nkey: v\n---\nSetext?\n---\n")
T("fm-only-opener", "---\n")
T("fm-opener-is-hr", "text\n---\nmore\n")
T("fm-fs-opener", "\x1c---\nid: x\n---\nbody\n")

# ---------------------------------------------------------------------------
# Group M — budget caps (WS4)
# ---------------------------------------------------------------------------

big = "x" * 262144
T("cap-exact-fit", f"## Alpha\n\n{big}\n\ny\n", events=False)
T(
    "cap-per-line-skip",
    "## Beta\n\n" + "a" * 200000 + "\n\n" + "b" * 200000 + "\n\n" + "c" * 10 + "\n",
    events=False,
)
T("cap-problem-divergence", "## Problem\n\nshort\n\n" + "p" * 300000 + "\n\ntail\n", events=False)
T(
    "cap-shared-duplicate-budget",
    "## Zeta\n\n" + "q" * 200000 + "\n\n## ZETA\n\n" + "r" * 200000 + "\n\ns3\n",
    events=False,
)
T(
    "cap-two-sections-sorted",
    "## zeta\n\n" + "z" * 262145 + "\n\n## alpha\n\n" + "a" * 262145 + "\n",
    events=False,
)
# line ceiling: 50000 lines fill the budget, later content is dropped but
# later headings still register
many = "\n".join(f"l{i}" for i in range(50001))
T(
    "cap-line-ceiling",
    "## Bulk\n\n" + many + "\n\n## Problem\n\nnever captured\n\n## Risks\n",
    events=False,
)
T("cap-oversize-text", "# Title\n\n## Problem\n\nx\n", cap=10)
T("cap-oversize-boundary-exact", "12345", cap=5)
T("cap-oversize-boundary-over", "123456", cap=5)
T("cap-multibyte-boundary", "é" * 3, cap=5)  # 6 utf-8 bytes > 5
T("cap-multibyte-under", "é" * 2, cap=5)

# ---------------------------------------------------------------------------
# Group N — misc / hr
# ---------------------------------------------------------------------------

T("hr-dashes", "---\ntext\n")
T("hr-spaced", " - - - \ntext\n")
T("hr-underscore", "___\n")
T("hr-star-4", "****\n")
T("hr-mixed-invalid", "--*\n")
T("hr-two-only", "--\n")
T("empty-doc", "")
T("blank-doc", "\n\n\n")
T("space-doc", "   \n\t\n")
T("single-word", "word")
T("heading-eof", "## Problem")
T("body-after-heading-eof", "## Problem\nx")
T("weird-1", "#\n#\n#\n")
T("weird-2", "## a\n## a\n## a\n")
T("weird-3", "- \n- \n")
T("weird-4", ">\n>\n")
T("weird-5", "[\n")
T("weird-6", "[]\n")
T("weird-7", "&amp;\n")
T("weird-8", "\\\n")

# source_path passthrough
T("source-path-set", "# T\n", source_path="some/path.md")

# ---------------------------------------------------------------------------
# Cap (env parsing) cases
# ---------------------------------------------------------------------------

C("cap-unset", None)
C("cap-10", "10")
C("cap-spaces", "  1048576  ")
C("cap-underscore", "1_0_0")
C("cap-underscore-bad", "_10")
C("cap-underscore-trail", "10_")
C("cap-double-underscore", "1__0")
C("cap-plus", "+42")
C("cap-neg", "-5")
C("cap-zero", "0")
C("cap-empty", "")
C("cap-junk", "abc")
C("cap-hex", "0x10")
C("cap-float", "1.5")
C("cap-newline", "10\n")
C("cap-arabic", "٣٤")
C("cap-fullwidth", "１００")
C("cap-nbsp-pad", " 100 ")
C("cap-fs-pad", "\x1c5")
C("cap-big", "99999999999999999999")

# ---------------------------------------------------------------------------
# File cases (paths relative to rust/rac-engine)
# ---------------------------------------------------------------------------

def _write(rel, data):
    path = os.path.join(ENGINE_DIR, rel)
    with open(path, "wb") as fh:
        fh.write(data)


_write("tests/vectors/files/normal.md", CANONICAL.encode("utf-8"))
_write(
    "tests/vectors/files/frontmatter.md",
    b"---\nid: RAC-F\n---\n# File Title\n\n## Risks\n\nrisk one\n",
)
_write("tests/vectors/files/empty.md", b"")
_write(
    "tests/vectors/files/non-utf8.md",
    b"# T\xe2\x82\n\n## Problem\n\nbad \xff byte \xc3( here\n\x80abc\n",
)
_write("tests/vectors/files/oversize.md", b"x" * 100)
_write("tests/vectors/files/crlf.md", CANONICAL.replace("\n", "\r\n").encode("utf-8"))

F("file-normal", "tests/vectors/files/normal.md")
F("file-frontmatter", "tests/vectors/files/frontmatter.md")
F("file-empty", "tests/vectors/files/empty.md")
F("file-non-utf8", "tests/vectors/files/non-utf8.md")
F("file-crlf", "tests/vectors/files/crlf.md")
F("file-missing", "tests/vectors/files/definitely-missing.md", degraded=True)
F("file-missing-nested", "tests/vectors/no-such-dir/x.md", degraded=True)
F("file-directory", "tests/vectors/files", degraded=True)
F("file-oversize-cap", "tests/vectors/files/oversize.md", cap=50, degraded=True)
F("file-under-cap", "tests/vectors/files/oversize.md", cap=100)
F("file-cap-1", "tests/vectors/files/normal.md", cap=1, degraded=True)

# ---------------------------------------------------------------------------
# Parametrized sweeps
# ---------------------------------------------------------------------------

# recognized-section headings across whitespace/case variants
for i, h in enumerate(
    [
        "problem",
        "PROBLEM",
        " Problem ",
        "\tProblem\t",
        "Problem ",
        "\x1cProblem",
        "requirements",
        "Requirements ",
        "success metrics",
        "Success  Metrics",  # double interior space: NOT recognized
        "SUCCESS METRICS",
        "risks",
        "RISKS ",
        "risks",
    ]
):
    T(f"sweep-section-{i:02d}", f"# T\n\n##{h and ' ' or ''}{h}\n\nbody line\n")

# tab-stop expansion sweep in list markers
for i in range(8):
    T(f"sweep-tab-list-{i}", " " * i + "-\tafter tab\n")

# fence marker length / indent sweep
for n in (3, 4, 5):
    T(f"sweep-fence-len-{n}", "`" * n + "\n## hidden\n" + "`" * n + "\nafter\n")
    T(f"sweep-tilde-len-{n}", "~" * n + "\nhidden\n" + "~" * n + "\nafter\n")

# blockquote marker offset sweep (spaces before '>')
for i in range(4):
    T(f"sweep-bq-indent-{i}", " " * i + "> ## Risks\n" + " " * i + "> line\n")

# ordered marker sweep
for i, m in enumerate(["1.", "1)", "9.", "10.", "0.", "01."]):
    T(f"sweep-ol-{i}", f"{m} item one\n{m[:-1]}{m[-1]} item two\n")

# entity sweep in heading raw content
for i, e in enumerate(["&amp;", "&#65;", "&#x41;", "&unknown;", "&;", "&#xZZ;"]):
    T(f"sweep-entity-{i}", f"## Head {e} tail\n\nbody {e} text\n")

assert len(CASES) >= 400, f"only {len(CASES)} synthetic cases"

with open(os.path.join(VEC_DIR, "markdown.json"), "w", encoding="utf-8") as fh:
    json.dump({"cases": CASES}, fh, ensure_ascii=True, separators=(",", ":"))
    fh.write("\n")

# ---------------------------------------------------------------------------
# Live corpus: every .md under rac/ and tests/
# ---------------------------------------------------------------------------

corpus_cases = []
# Frozen snapshot of the corpus (COUNCIL-REVIEW B3), not the live rac//tests/,
# so a docs commit no longer invalidates the cargo suite; live-corpus coverage
# stays in the parity tier.
_CORPUS = os.path.join(REPO, "rust", "fixtures", "corpus")
corpus_roots = [os.path.join(_CORPUS, "rac"), os.path.join(_CORPUS, "tests")]
paths = []
for root in corpus_roots:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                paths.append(os.path.join(dirpath, fn))
paths.sort()
for abspath in paths:
    rel = os.path.relpath(abspath, ENGINE_DIR)
    with open(abspath, "rb") as fh:
        data = fh.read()
    text = data.decode("utf-8", errors="replace")
    product = md.parse_file(rel)
    corpus_cases.append(
        {
            "name": rel,
            "kind": "file",
            "path": rel,
            "cap": None,
            "product": product_value(product, text=text),
        }
    )

with open(os.path.join(VEC_DIR, "markdown_corpus.json"), "w", encoding="utf-8") as fh:
    json.dump({"cases": corpus_cases}, fh, ensure_ascii=True, separators=(",", ":"))
    fh.write("\n")

print(f"synthetic cases: {len(CASES)}")
print(f"corpus cases: {len(corpus_cases)}")
