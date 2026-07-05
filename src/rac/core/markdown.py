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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from markdown_it import MarkdownIt

from .frontmatter import parse_frontmatter, split_frontmatter
from .limits import (
    MAX_CAPTURED_LINES,
    MAX_FIELD_CHARS,
    exceeds_byte_cap,
    max_file_bytes,
)
from .models import Issue, MalformedRequirement, Product, Requirement, SearchSection

if TYPE_CHECKING:
    from markdown_it.token import Token

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


@dataclass
class _WalkState:
    """The mutable accumulator threaded through one token walk.

    Holds every value the walk mutates: the current section context, the WS4
    body-capture budget (REQ-003), and the accumulating Product fields. The
    handlers below mutate ``self`` in place and :func:`parse` reads the finished
    state out into a :class:`Product`. Splitting the walk this way keeps each
    token kind's behavior in one small method instead of one interleaved loop;
    it changes no output.

    ``offset`` is the frontmatter line offset, added back to every reported line
    so diagnostics stay file-accurate.
    """

    offset: int
    title: str | None = None
    extra_title_lines: list[int] = field(default_factory=list)
    # Current recognized-section key ("problem"/…), None (title/pre-heading), or
    # "other" (an unrecognized ## heading).
    section: str | None = None
    # Normalized heading of the current ## section; None until the first ##.
    current_h2: str | None = None
    # Searchable sections in document order, heading/line text preserved as
    # stored (v0.10.3): the source of body-tier search snippets.
    search_sections: list[SearchSection] = field(default_factory=list)
    current_search: SearchSection | None = None
    problem_lines: list[str] = field(default_factory=list)
    requirement_lines: list[tuple[str, int]] = field(default_factory=list)
    metric_lines: list[str] = field(default_factory=list)
    risk_lines: list[str] = field(default_factory=list)
    # Generic body text per ## section: {normalized heading -> [stripped lines]}.
    section_bodies: dict[str, list[str]] = field(default_factory=dict)
    # WS4 body-capture budget (REQ-003): per-section char totals and the running
    # captured-line count, so one oversized field cannot dominate the Product.
    section_chars: dict[str, int] = field(default_factory=dict)
    captured_lines: int = 0
    truncated_fields: set[str] = field(default_factory=set)
    body_truncated: bool = False
    # Recognized-section presence (heading seen), distinct from "has body".
    has: dict[str, bool] = field(
        default_factory=lambda: {
            "problem": False,
            "requirements": False,
            "success_metrics": False,
            "risks": False,
        }
    )

    def open_heading(self, tok: Token, heading_text: str) -> None:
        """Begin the section a heading opens, resetting section context.

        h1 sets the title (a second h1 is recorded as an extra-title line, not a
        new title); h2 starts a tracked or generic section; deeper headings mark
        the body "other" so it is captured generically but not as a field.
        """
        if tok.tag == "h1":
            if self.title is None:
                self.title = heading_text.strip()
            else:
                self.extra_title_lines.append((tok.map[0] + 1 + self.offset) if tok.map else 0)
            self.section = None  # content directly under the title is ignored
            self.current_h2 = None
            self.current_search = None
        elif tok.tag == "h2":
            normalized = _normalize_heading(heading_text)
            self.current_h2 = normalized
            # Record the heading immediately so empty sections still appear in
            # product.sections (classification keys off heading presence).
            self.section_bodies.setdefault(normalized, [])
            # The searchable section carries the heading exactly as stored, so
            # body-tier snippets render the document's own heading.
            self.current_search = SearchSection(heading=heading_text.strip())
            self.search_sections.append(self.current_search)
            key = _SECTIONS.get(normalized)
            self.section = key
            if key is not None:
                self.has[key] = True
        else:
            self.section = "other"

    def capture_inline(self, tok: Token) -> None:
        """Route an inline token's content to the generic map and any field.

        Once the captured-line ceiling is hit the walk stops capturing entirely
        (WS4, REQ-003): the document is reported truncated and the parse
        completes rather than accumulating unboundedly.
        """
        if self.body_truncated:
            return
        # Generic body capture runs for every ## section (the canonical map);
        # it may trip the ceiling, which then also gates the field capture below.
        if self.current_h2 is not None:
            self._capture_generic_body(tok, self.current_h2)
        if self.body_truncated or self.section is None or self.section == "other":
            return
        self._capture_field(tok)

    def _capture_generic_body(self, tok: Token, heading: str) -> None:
        """Append the token's non-blank lines to ``section_bodies[heading]``.

        Enforces the WS4 budget: a line over the per-section char cap marks the
        field truncated and is dropped; reaching the total line ceiling stops
        all further capture. Interior ``\\r`` is stripped per line, so a CRLF
        body never carries a stray carriage return into ``sections``.
        """
        for raw in tok.content.split("\n"):
            stripped = raw.strip()
            if not stripped:
                continue
            if self.captured_lines >= MAX_CAPTURED_LINES:
                self.body_truncated = True
                break
            if self.section_chars.get(heading, 0) + len(stripped) > MAX_FIELD_CHARS:
                self.truncated_fields.add(heading)
                continue
            self.section_bodies.setdefault(heading, []).append(stripped)
            self.section_chars[heading] = self.section_chars.get(heading, 0) + len(stripped) + 1
            self.captured_lines += 1
            if self.current_search is not None:
                self.current_search.lines.append(stripped)

    def _capture_field(self, tok: Token) -> None:
        """Route a recognized section's content to its typed field accumulator."""
        start_line = (tok.map[0] + self.offset) if tok.map else 0
        lines = _content_lines(tok.content, start_line)
        if self.section == "problem":
            self.problem_lines.extend(t for t, _ in lines)
        elif self.section == "requirements":
            self.requirement_lines.extend(lines)
        elif self.section == "success_metrics":
            self.metric_lines.extend(t for t, _ in lines)
        elif self.section == "risks":
            self.risk_lines.extend(t for t, _ in lines)


def _split_requirements(
    lines: list[tuple[str, int]],
) -> tuple[list[Requirement], list[MalformedRequirement]]:
    """Partition captured requirement lines into valid and malformed."""
    requirements: list[Requirement] = []
    malformed: list[MalformedRequirement] = []
    for line_text, line_no in lines:
        result = _classify_requirement_line(line_text, line_no)
        if isinstance(result, Requirement):
            requirements.append(result)
        else:
            malformed.append(result)
    return requirements, malformed


def _budget_issues(state: _WalkState) -> list[Issue]:
    """Warnings for any WS4 truncation (REQ-003): served partial, not failed.

    Field truncations are emitted in sorted-heading order, then the body
    truncation, so the issue list is deterministic (ADR-002).
    """
    issues: list[Issue] = []
    for heading in sorted(state.truncated_fields):
        issues.append(
            Issue(
                "warning",
                "field-truncated",
                f"section {heading!r} exceeds the {MAX_FIELD_CHARS}-char field cap "
                "and was truncated",
            )
        )
    if state.body_truncated:
        issues.append(
            Issue(
                "warning",
                "body-truncated",
                f"document body exceeds the {MAX_CAPTURED_LINES}-line capture cap "
                "and was truncated",
            )
        )
    return issues


def parse(text: str, source_path: str = "") -> Product:
    """Parse Markdown ``text`` into a :class:`Product`.

    A leading YAML frontmatter block (ADR-025) is split off and parsed into
    ``product.metadata`` before the Markdown body is tokenized; every line
    number reported downstream is offset back to the original file so
    diagnostics stay file-accurate. Documents without frontmatter are parsed
    exactly as before.

    Input over the per-parse byte cap (REQ-001) is rejected before tokenizing
    and returned as a structured oversize issue, never an exception. The
    "parse cap" wording here is distinct from ``parse_file``'s "file cap" and
    is pinned — do not unify them.
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

    tokens = _PARSER.parse(split.body)
    state = _WalkState(offset=split.line_offset)
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            heading_text = tokens[i + 1].content if i + 1 < len(tokens) else ""
            state.open_heading(tok, heading_text)
        elif tok.type == "inline" and not (i > 0 and tokens[i - 1].type == "heading_open"):
            # An inline that is *not* a heading's own text is body content.
            state.capture_inline(tok)

    requirements, malformed = _split_requirements(state.requirement_lines)
    # None = section absent; "" = present but empty; otherwise the joined text.
    problem = "\n".join(state.problem_lines).strip() if state.has["problem"] else None
    sections = {h: "\n".join(lines) for h, lines in state.section_bodies.items()}

    return Product(
        title=state.title,
        extra_title_lines=state.extra_title_lines,
        problem=problem,
        requirements=requirements,
        malformed_requirements=malformed,
        success_metrics=state.metric_lines,
        risks=state.risk_lines,
        sections=sections,
        search_sections=state.search_sections,
        has_problem_section=state.has["problem"],
        has_requirements_section=state.has["requirements"],
        has_metrics_section=state.has["success_metrics"],
        has_risks_section=state.has["risks"],
        source_path=source_path,
        metadata=metadata,
        metadata_issues=metadata_issues,
        parse_issues=_budget_issues(state),
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
