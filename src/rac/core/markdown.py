"""Turn a Markdown requirement file into a :class:`~rac.core.models.Product` AST.

We tokenize with ``markdown-it-py`` and walk the (flat) token stream, tracking the
current ``##`` section. This module performs *structural extraction only* — it does
not enforce any rules. All rule-checking lives in :mod:`rac.core.validation`, so that
diffing and future analysis share a single source of truth.

Heading matching is case-insensitive and whitespace-trimmed, so ``## problem`` and
``##  Problem `` both work.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

from .frontmatter import parse_frontmatter, split_frontmatter
from .models import Issue, MalformedRequirement, Product, Requirement, SearchSection

# A requirement line: a leading ``[...]`` ID token followed by description text.
# We capture anything inside the brackets so we can distinguish a *malformed* ID
# from a missing one, then validate the ID shape separately.
_BRACKET_RE = re.compile(r"^\[(?P<id>[^\]]*)\]\s*(?P<text>.*)$")
# Canonical requirement ID, e.g. REQ-001.
_CANONICAL_ID_RE = re.compile(r"^REQ-\d+$")

# Recognized section headings, normalized (stripped + casefolded).
_SECTIONS = {
    "problem": "problem",
    "requirements": "requirements",
    "success metrics": "success_metrics",
    "risks": "risks",
}


def _normalize_heading(text: str) -> str:
    return text.strip().casefold()


def _content_lines(content: str, start_line: int) -> list[tuple[str, int]]:
    """Split an inline token's content into ``(text, 1-based-line)`` pairs.

    ``start_line`` is the 0-based line where the enclosing block begins (from the
    token's ``.map``). Blank lines are dropped but still advance the line counter.
    """
    pairs: list[tuple[str, int]] = []
    for offset, raw in enumerate(content.split("\n")):
        stripped = raw.strip()
        if stripped:
            pairs.append((stripped, start_line + offset + 1))
    return pairs


def _classify_requirement_line(text: str, line: int) -> Requirement | MalformedRequirement:
    """Return either a :class:`Requirement` or :class:`MalformedRequirement`."""
    m = _BRACKET_RE.match(text)
    if not m:
        # No recognizable ``[...]`` prefix at all.
        return MalformedRequirement(raw=text, line=line, bad_id=None)
    req_id = m.group("id").strip()
    desc = m.group("text").strip()
    if not _CANONICAL_ID_RE.match(req_id):
        return MalformedRequirement(raw=text, line=line, bad_id=req_id)
    if not desc:
        return MalformedRequirement(raw=text, line=line, bad_id=req_id, empty_text=True)
    return Requirement(id=req_id, text=desc, line=line)


def parse(text: str, source_path: str = "") -> Product:
    """Parse Markdown ``text`` into a :class:`Product`.

    A leading YAML frontmatter block (ADR-025) is split off and parsed into
    ``product.metadata`` before the Markdown body is tokenized; every line
    number reported downstream is offset back to the original file so
    diagnostics stay file-accurate. Documents without frontmatter are parsed
    exactly as before.
    """
    split = split_frontmatter(text)
    offset = split.line_offset
    metadata = None
    metadata_issues: list[Issue] = []
    if split.raw is not None:
        metadata, metadata_issues = parse_frontmatter(split.raw)
    elif split.unterminated:
        metadata_issues.append(
            Issue(
                "error",
                "malformed-frontmatter",
                "frontmatter block opened with --- on line 1 but never closed",
                1,
            )
        )

    tokens = MarkdownIt("commonmark").parse(split.body)

    title: str | None = None
    extra_title_lines: list[int] = []
    section: str | None = None  # current tracked section key, or None/"other"
    current_h2: str | None = None  # normalized heading of the current ## section
    # Searchable sections in document order, original heading/line text preserved
    # (v0.10.3): the source of snippet text for body-tier search.
    search_sections: list[SearchSection] = []
    current_search: SearchSection | None = None

    problem_lines: list[str] = []
    requirement_lines: list[tuple[str, int]] = []
    metric_lines: list[str] = []
    risk_lines: list[str] = []
    # Generic body text per ## section: {normalized heading -> [stripped lines]}.
    section_bodies: dict[str, list[str]] = {}

    has = {
        "problem": False,
        "requirements": False,
        "success_metrics": False,
        "risks": False,
    }

    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            heading_text = tokens[i + 1].content if i + 1 < len(tokens) else ""
            if tok.tag == "h1":
                if title is None:
                    title = heading_text.strip()
                else:
                    extra_title_lines.append((tok.map[0] + 1 + offset) if tok.map else 0)
                section = None  # content directly under the title is ignored
                current_h2 = None
                current_search = None
            elif tok.tag == "h2":
                normalized = _normalize_heading(heading_text)
                current_h2 = normalized
                # Record the heading immediately so empty sections still appear
                # in product.sections (classification keys off heading presence).
                section_bodies.setdefault(normalized, [])
                # Searchable section carries the heading text exactly as stored,
                # so body-tier snippets render the document's own heading.
                current_search = SearchSection(heading=heading_text.strip())
                search_sections.append(current_search)
                key = _SECTIONS.get(normalized)
                section = key
                if key is not None:
                    has[key] = True
            else:
                section = "other"
            continue

        if tok.type != "inline":
            continue

        # Skip the inline that *is* a heading's text.
        if i > 0 and tokens[i - 1].type == "heading_open":
            continue

        # Generic body capture for every ## section (the canonical content map).
        if current_h2 is not None:
            for raw in tok.content.split("\n"):
                stripped = raw.strip()
                if stripped:
                    section_bodies.setdefault(current_h2, []).append(stripped)
                    if current_search is not None:
                        current_search.lines.append(stripped)

        if section is None or section == "other":
            continue

        start_line = (tok.map[0] + offset) if tok.map else 0
        lines = _content_lines(tok.content, start_line)

        if section == "problem":
            problem_lines.extend(t for t, _ in lines)
        elif section == "requirements":
            requirement_lines.extend(lines)
        elif section == "success_metrics":
            metric_lines.extend(t for t, _ in lines)
        elif section == "risks":
            risk_lines.extend(t for t, _ in lines)

    requirements: list[Requirement] = []
    malformed: list[MalformedRequirement] = []
    for line_text, line_no in requirement_lines:
        result = _classify_requirement_line(line_text, line_no)
        if isinstance(result, Requirement):
            requirements.append(result)
        else:
            malformed.append(result)

    # None = section absent; "" = present but empty; otherwise the joined text.
    problem = "\n".join(problem_lines).strip() if has["problem"] else None

    sections = {h: "\n".join(lines) for h, lines in section_bodies.items()}

    return Product(
        title=title,
        extra_title_lines=extra_title_lines,
        problem=problem,
        requirements=requirements,
        malformed_requirements=malformed,
        success_metrics=metric_lines,
        risks=risk_lines,
        sections=sections,
        search_sections=search_sections,
        has_problem_section=has["problem"],
        has_requirements_section=has["requirements"],
        has_metrics_section=has["success_metrics"],
        has_risks_section=has["risks"],
        source_path=source_path,
        metadata=metadata,
        metadata_issues=metadata_issues,
    )


def parse_file(path: str) -> Product:
    """Read ``path`` and parse it into a :class:`Product`."""
    with open(path, encoding="utf-8") as fh:
        return parse(fh.read(), source_path=path)
