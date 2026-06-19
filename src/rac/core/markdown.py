"""Turn a Markdown requirement file into a :class:`~rac.core.models.Product` AST.

We tokenize with ``markdown-it-py`` and walk the (flat) token stream, tracking the
current ``##`` section. This module performs *structural extraction only* — it does
not enforce any rules. All rule-checking lives in :mod:`rac.core.validation`, so that
diffing and future analysis share a single source of truth.

Heading matching is case-insensitive and whitespace-trimmed, so ``## problem`` and
``##  Problem `` both work.
"""

from __future__ import annotations

import os
import re

from markdown_it import MarkdownIt

from .frontmatter import parse_frontmatter, split_frontmatter
from .limits import (
    MAX_CAPTURED_LINES,
    MAX_FIELD_CHARS,
    exceeds_byte_cap,
    max_file_bytes,
)
from .models import Issue, MalformedRequirement, Product, Requirement, SearchSection

# A single shared parser, built once and reused for every ``parse`` call.
# Constructing a ``MarkdownIt`` is expensive — it compiles the linkify regexes
# and introspects its rule chains on every instantiation — whereas ``parse`` is
# stateless across calls (each call builds its own parse state). Parsing is the
# engine's dominant cost (every corpus walk, validation, portfolio summary,
# relationship analysis, and MCP tool call flows through it), so reusing the
# parser roughly halves that cost while producing byte-identical tokens.
_PARSER = MarkdownIt("commonmark")

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


def _degraded_product(source_path: str, issues: list[Issue]) -> Product:
    """A minimal Product carrying only parse-level issues (WS4, REQ-005).

    Returned when input is rejected before the body is parsed (oversize, or an
    unreadable file): an empty artifact that classifies as Unknown and fails
    validation via its ``parse_issues``, so the defect is reported and the
    corpus walk continues past it rather than crashing.
    """
    return Product(title=None, source_path=source_path, parse_issues=issues)


def parse(text: str, source_path: str = "") -> Product:
    """Parse Markdown ``text`` into a :class:`Product`.

    A leading YAML frontmatter block (ADR-025) is split off and parsed into
    ``product.metadata`` before the Markdown body is tokenized; every line
    number reported downstream is offset back to the original file so
    diagnostics stay file-accurate. Documents without frontmatter are parsed
    exactly as before.

    Input over the per-parse byte cap (REQ-001) is rejected before tokenizing
    and returned as a structured oversize issue, never an exception.
    """
    cap = max_file_bytes()
    if exceeds_byte_cap(text, cap):
        return _degraded_product(
            source_path,
            [
                Issue(
                    "error",
                    "artifact-oversize",
                    f"artifact exceeds the {cap}-byte parse cap "
                    "(set RAC_MAX_FILE_BYTES to raise it)",
                    1,
                )
            ],
        )

    parse_issues: list[Issue] = []
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

    tokens = _PARSER.parse(split.body)

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
    # Body-capture caps (WS4, REQ-003): per-section char budget and a total
    # captured-line ceiling so one oversized field cannot dominate the Product.
    # Generous enough that no real artifact is affected; inert below the caps.
    section_chars: dict[str, int] = {}
    captured_lines = 0
    truncated_fields: set[str] = set()
    body_truncated = False

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

        # Once the total captured-line ceiling is hit, stop capturing any further
        # body (generic or recognized): the document is reported truncated and the
        # parse completes rather than accumulating unboundedly (WS4, REQ-003).
        if body_truncated:
            continue

        # Generic body capture for every ## section (the canonical content map).
        if current_h2 is not None:
            for raw in tok.content.split("\n"):
                stripped = raw.strip()
                if not stripped:
                    continue
                if captured_lines >= MAX_CAPTURED_LINES:
                    body_truncated = True
                    break
                if section_chars.get(current_h2, 0) + len(stripped) > MAX_FIELD_CHARS:
                    truncated_fields.add(current_h2)
                    continue
                section_bodies.setdefault(current_h2, []).append(stripped)
                section_chars[current_h2] = section_chars.get(current_h2, 0) + len(stripped) + 1
                captured_lines += 1
                if current_search is not None:
                    current_search.lines.append(stripped)

        if body_truncated or section is None or section == "other":
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

    # Body-cap findings (WS4, REQ-003): a truncated field or document is reported
    # as a warning — the artifact is served partial, not failed outright.
    for heading in sorted(truncated_fields):
        parse_issues.append(
            Issue(
                "warning",
                "field-truncated",
                f"section {heading!r} exceeds the {MAX_FIELD_CHARS}-char field cap "
                "and was truncated",
            )
        )
    if body_truncated:
        parse_issues.append(
            Issue(
                "warning",
                "body-truncated",
                f"document body exceeds the {MAX_CAPTURED_LINES}-line capture cap "
                "and was truncated",
            )
        )

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
        parse_issues=parse_issues,
    )


def parse_file(path: str) -> Product:
    """Read ``path`` and parse it into a :class:`Product` (WS4-hardened).

    Bounds work before reading the whole file into memory (REQ-001) and degrades
    gracefully on adversarial input (REQ-005): an oversize file, an unreadable
    file, or non-UTF-8 bytes yields a structured issue, never an exception that
    would crash a serving path or abort the corpus walk.
    """
    cap = max_file_bytes()
    try:
        # Size-check the path first, then read at most the cap (+1 to detect a
        # file that grew between stat and read, or a symlink to something larger).
        size = os.path.getsize(path)
        if size > cap:
            return _degraded_product(path, [_oversize_issue(cap)])
        with open(path, "rb") as fh:
            data = fh.read(cap + 1)
    except OSError as exc:
        return _degraded_product(
            path, [Issue("error", "unreadable-artifact", f"cannot read artifact: {exc}", 1)]
        )
    if len(data) > cap:
        return _degraded_product(path, [_oversize_issue(cap)])

    try:
        text = data.decode("utf-8")
        product = parse(text, source_path=path)
    except UnicodeDecodeError:
        # Non-UTF-8 / partial sequences: decode lossily so the parse still
        # completes, and report the encoding defect for review (REQ-005, REQ-009).
        product = parse(data.decode("utf-8", errors="replace"), source_path=path)
        product.parse_issues.append(
            Issue("warning", "non-utf8-content", "artifact is not valid UTF-8; decoded lossily", 1)
        )
    return product


def _oversize_issue(cap: int) -> Issue:
    return Issue(
        "error",
        "artifact-oversize",
        f"artifact exceeds the {cap}-byte file cap (set RAC_MAX_FILE_BYTES to raise it)",
        1,
    )
