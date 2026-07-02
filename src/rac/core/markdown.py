"""Turn Markdown text into a :class:`~rac.core.models.Product` AST.

This is the deterministic bottom of the engine: everything downstream —
classification, validation, relationships, services, MCP, CLI, golden output —
reads the ``Product`` this module builds, never the raw text. The shape of that
AST is therefore a contract, even though nothing here prints.

The parser tokenizes with ``markdown-it-py`` and walks the flat token stream,
tracking the current ``##`` section. It performs *structural extraction only* —
no rule checking (that lives in :mod:`rac.core.validation`) — so diffing and
analysis share one source of truth. Working from markdown-it tokens rather than
raw lines is load-bearing: list tokenization strips the ``- `` marker before we
see ``tok.content``, which is why a bulleted ``- [REQ-001] ...`` and a plain
``[REQ-001] ...`` classify identically.

Heading matching is case-insensitive and whitespace-trimmed.
"""

from __future__ import annotations

import os
import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .frontmatter import parse_frontmatter, split_frontmatter
from .limits import (
    MAX_CAPTURED_LINES,
    MAX_FIELD_CHARS,
    exceeds_byte_cap,
    max_file_bytes,
)
from .models import Issue, MalformedRequirement, Product, Requirement, SearchSection

# One shared parser for every ``parse`` call (ADR-059). Constructing a
# ``MarkdownIt`` compiles its regexes and introspects its rule chains, while
# ``parse`` itself is stateless across calls — reuse roughly halves the engine's
# dominant cost while producing byte-identical tokens. Never build one per call.
_PARSER = MarkdownIt("commonmark")

# A requirement line: a leading ``[...]`` ID token, then description text. The
# brackets capture *anything*, so a malformed ID can be told apart from a missing
# one and validated separately. No nested quantifiers — this runs against every
# body line and must stay linear (REQ-004).
_BRACKET_RE = re.compile(r"^\[(?P<id>[^\]]*)\]\s*(?P<text>.*)$")
# Canonical requirement ID, e.g. REQ-001.
_CANONICAL_ID_RE = re.compile(r"^REQ-\d+$")

# Recognized headings, normalized (stripped + casefolded) -> the Product field
# they feed. Any other ``##`` is captured generically but carries no typed list.
_SECTIONS = {
    "problem": "problem",
    "requirements": "requirements",
    "success metrics": "success_metrics",
    "risks": "risks",
}


def _normalize_heading(text: str) -> str:
    return text.strip().casefold()


def _heading_text(tokens: list[Token], i: int) -> str:
    """Text of the heading opened at ``tokens[i]``.

    In a commonmark stream a ``heading_open`` is always followed by its inline
    content token; the bound guards the tail of the stream defensively.
    """
    return tokens[i + 1].content if i + 1 < len(tokens) else ""


def _content_lines(content: str, start_line: int) -> list[tuple[str, int]]:
    """Split inline content into ``(stripped_text, 1-based file line)`` pairs.

    ``start_line`` is the block's 0-based start (from ``tok.map``, already offset
    back to the file). Blank lines are dropped but still advance the counter, so
    reported line numbers stay accurate.
    """
    pairs: list[tuple[str, int]] = []
    for offset, raw in enumerate(content.split("\n")):
        stripped = raw.strip()
        if stripped:
            pairs.append((stripped, start_line + offset + 1))
    return pairs


def _classify_requirement_line(text: str, line: int) -> Requirement | MalformedRequirement:
    """Sort one requirement line into a valid or malformed requirement.

    Malformed in three distinct ways, each recorded rather than dropped so
    validation can report it: no ``[...]`` prefix, a non-canonical ID, or a
    canonical ID with empty description text.
    """
    m = _BRACKET_RE.match(text)
    if not m:
        return MalformedRequirement(raw=text, line=line, bad_id=None)
    req_id = m.group("id").strip()
    desc = m.group("text").strip()
    if not _CANONICAL_ID_RE.match(req_id):
        return MalformedRequirement(raw=text, line=line, bad_id=req_id)
    if not desc:
        return MalformedRequirement(raw=text, line=line, bad_id=req_id, empty_text=True)
    return Requirement(id=req_id, text=desc, line=line)


def _oversize_issue(cap: int) -> Issue:
    """The single oversize finding, shared by the in-memory and file paths."""
    return Issue(
        "error",
        "artifact-oversize",
        f"artifact exceeds the {cap}-byte file cap (set RAC_MAX_FILE_BYTES to raise it)",
        1,
    )


def _degraded_product(source_path: str, issues: list[Issue]) -> Product:
    """A minimal Product carrying only parse-level issues (WS4, REQ-005).

    Returned when input is rejected before the body is parsed (oversize or
    unreadable): it classifies as Unknown and fails validation through its
    ``parse_issues``, so the defect is reported and the corpus walk continues
    past it rather than crashing.
    """
    return Product(title=None, source_path=source_path, parse_issues=issues)


class _ProductBuilder:
    """Mutable accumulator for one walk of the flat token stream.

    Holds the state a single ``parse`` builds up, so the two body-capture
    concerns read as separate methods: a *generic* content map for every ``##``
    section (also the source of body-tier search text) and the *typed* lists for
    the four recognized sections. The two paths deliberately differ — the generic
    map is char-capped and line-numbered-free; the typed lists are line-numbered
    and uncapped, so downstream rules see a full field even when the map was
    truncated for size.
    """

    def __init__(self, offset: int) -> None:
        # `offset` restores file-accurate line numbers through a frontmatter block.
        self._offset = offset

        self.title: str | None = None
        self.extra_title_lines: list[int] = []
        # Searchable sections in document order, original heading/line text kept.
        self.search_sections: list[SearchSection] = []

        self.problem_lines: list[str] = []
        self.requirement_lines: list[tuple[str, int]] = []
        self.metric_lines: list[str] = []
        self.risk_lines: list[str] = []
        self.has = {
            "problem": False,
            "requirements": False,
            "success_metrics": False,
            "risks": False,
        }

        # Generic per-``##`` content map: {normalized heading -> [stripped lines]}.
        self.section_bodies: dict[str, list[str]] = {}
        # Body caps (WS4, REQ-003): a per-section char budget and a global
        # captured-line ceiling, so one hostile field can't dominate the Product.
        # Generous in production; inert below the caps.
        self.section_chars: dict[str, int] = {}
        self.captured_lines = 0
        self.truncated_fields: set[str] = set()
        self.body_truncated = False

        # Walk cursor.
        self._section: str | None = None  # recognized key, None, or "other"
        self._current_h2: str | None = None
        self._current_search: SearchSection | None = None

    def open_heading(self, tok: Token, text: str) -> None:
        """Enter the section a heading opens and reset the cursor accordingly."""
        if tok.tag == "h1":
            if self.title is None:
                self.title = text.strip()
            else:
                # A second title is a defect; record its file line for validation.
                self.extra_title_lines.append((tok.map[0] + 1 + self._offset) if tok.map else 0)
            # Content directly under a title belongs to no section.
            self._section = None
            self._current_h2 = None
            self._current_search = None
        elif tok.tag == "h2":
            normalized = _normalize_heading(text)
            self._current_h2 = normalized
            # setdefault so an empty ## still appears in `sections`: classification
            # keys off heading presence, not body content.
            self.section_bodies.setdefault(normalized, [])
            self._current_search = SearchSection(heading=text.strip())
            self.search_sections.append(self._current_search)
            key = _SECTIONS.get(normalized)
            self._section = key
            if key is not None:
                self.has[key] = True
        else:
            # h3+ marks "other" but keeps the enclosing ## cursor, so a nested
            # subsection's body folds into its parent ## section (Trap 7).
            self._section = "other"

    def capture(self, tok: Token) -> None:
        """Fold one inline body token into the generic map and any typed list."""
        # Generic map runs for every ## section and may trip the line ceiling
        # part-way through this token, which then skips the typed capture below.
        if self._current_h2 is not None:
            self._capture_generic(tok, self._current_h2)

        if self.body_truncated or self._section is None or self._section == "other":
            return

        start_line = (tok.map[0] + self._offset) if tok.map else 0
        lines = _content_lines(tok.content, start_line)
        if self._section == "problem":
            self.problem_lines.extend(text for text, _ in lines)
        elif self._section == "requirements":
            self.requirement_lines.extend(lines)
        elif self._section == "success_metrics":
            self.metric_lines.extend(text for text, _ in lines)
        elif self._section == "risks":
            self.risk_lines.extend(text for text, _ in lines)

    def _capture_generic(self, tok: Token, heading: str) -> None:
        for raw in tok.content.split("\n"):
            stripped = raw.strip()
            if not stripped:
                continue
            if self.captured_lines >= MAX_CAPTURED_LINES:
                # Global ceiling hit: stop capturing anything further, here and
                # for the rest of the document (the caller short-circuits too).
                self.body_truncated = True
                return
            if self.section_chars.get(heading, 0) + len(stripped) > MAX_FIELD_CHARS:
                # This field is over its char budget: drop the line from the map
                # but keep walking (the typed list still takes the full field).
                self.truncated_fields.add(heading)
                continue
            self.section_bodies.setdefault(heading, []).append(stripped)
            self.section_chars[heading] = self.section_chars.get(heading, 0) + len(stripped) + 1
            self.captured_lines += 1
            if self._current_search is not None:
                self._current_search.lines.append(stripped)


def parse(text: str, source_path: str = "") -> Product:
    """Parse Markdown ``text`` into a :class:`Product`.

    A leading YAML frontmatter block (ADR-025) is split off and parsed into
    ``product.metadata`` before the body is tokenized; every reported line number
    is offset back to the original file so diagnostics stay accurate. Input over
    the per-parse byte cap (REQ-001) is rejected before tokenizing and returned
    as a structured oversize issue, never an exception.
    """
    cap = max_file_bytes()
    if exceeds_byte_cap(text, cap):
        return _degraded_product(source_path, [_oversize_issue(cap)])

    split = split_frontmatter(text)
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

    builder = _ProductBuilder(split.line_offset)
    tokens = _PARSER.parse(split.body)
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            builder.open_heading(tok, _heading_text(tokens, i))
            continue
        if tok.type != "inline":
            continue
        # Skip the inline that *is* a heading's text. The i > 0 bound keeps a
        # leading inline from reading tokens[-1] and wrongly skipping (Trap C2).
        if i > 0 and tokens[i - 1].type == "heading_open":
            continue
        # Once the global line ceiling trips, stop capturing any further body.
        if builder.body_truncated:
            continue
        builder.capture(tok)

    requirements: list[Requirement] = []
    malformed: list[MalformedRequirement] = []
    for line_text, line_no in builder.requirement_lines:
        result = _classify_requirement_line(line_text, line_no)
        if isinstance(result, Requirement):
            requirements.append(result)
        else:
            malformed.append(result)

    # None = section absent; "" = present but empty; else the joined text.
    problem = "\n".join(builder.problem_lines).strip() if builder.has["problem"] else None
    sections = {h: "\n".join(lines) for h, lines in builder.section_bodies.items()}

    # Body-cap findings (WS4, REQ-003): a truncated field or document is a warning
    # — the artifact is served partial, not failed outright.
    parse_issues: list[Issue] = []
    for heading in sorted(builder.truncated_fields):
        parse_issues.append(
            Issue(
                "warning",
                "field-truncated",
                f"section {heading!r} exceeds the {MAX_FIELD_CHARS}-char field cap "
                "and was truncated",
            )
        )
    if builder.body_truncated:
        parse_issues.append(
            Issue(
                "warning",
                "body-truncated",
                f"document body exceeds the {MAX_CAPTURED_LINES}-line capture cap "
                "and was truncated",
            )
        )

    return Product(
        title=builder.title,
        extra_title_lines=builder.extra_title_lines,
        problem=problem,
        requirements=requirements,
        malformed_requirements=malformed,
        success_metrics=builder.metric_lines,
        risks=builder.risk_lines,
        sections=sections,
        search_sections=builder.search_sections,
        has_problem_section=builder.has["problem"],
        has_requirements_section=builder.has["requirements"],
        has_metrics_section=builder.has["success_metrics"],
        has_risks_section=builder.has["risks"],
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
        # Size-check first, then read at most cap+1 bytes — the +1 catches a file
        # that grew between stat and read, or a symlink to something larger.
        if os.path.getsize(path) > cap:
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
        product = parse(data.decode("utf-8"), source_path=path)
    except UnicodeDecodeError:
        # Non-UTF-8 / partial sequences: decode lossily so the parse still
        # completes, and report the encoding defect for review (REQ-005, REQ-009).
        product = parse(data.decode("utf-8", errors="replace"), source_path=path)
        product.parse_issues.append(
            Issue("warning", "non-utf8-content", "artifact is not valid UTF-8; decoded lossily", 1)
        )
    return product
