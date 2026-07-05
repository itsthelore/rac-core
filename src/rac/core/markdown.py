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
from markdown_it.token import Token

from .frontmatter import parse_frontmatter, split_frontmatter
from .limits import (
    MAX_CAPTURED_LINES,
    MAX_FIELD_CHARS,
    exceeds_byte_cap,
    max_file_bytes,
)
from .models import Issue, MalformedRequirement, Product, Requirement, SearchSection

if TYPE_CHECKING:  # type-only; keeps this module a leaf that reads no metadata at runtime
    from .metadata import ArtifactMetadata

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


def _split_metadata(text: str) -> tuple[ArtifactMetadata | None, list[Issue], str, int]:
    """Separate the leading YAML frontmatter envelope from the Markdown body.

    Returns ``(metadata, metadata_issues, body, line_offset)``. The envelope and
    the body are distinct concerns (ADR-025): metadata parsing happens here so
    the body walk below stays purely structural, and the line offset it returns
    keeps every downstream diagnostic pinned to the original file's line numbers.
    An opening ``---`` that never closes is body text carrying a single
    ``malformed-frontmatter`` issue, so the defect is reported without losing the
    document.
    """
    split = split_frontmatter(text)
    if split.raw is not None:
        metadata, metadata_issues = parse_frontmatter(split.raw)
        return metadata, metadata_issues, split.body, split.line_offset
    if split.unterminated:
        return (
            None,
            [
                Issue(
                    "error",
                    "malformed-frontmatter",
                    "frontmatter block opened with --- on line 1 but never closed",
                    1,
                )
            ],
            split.body,
            split.line_offset,
        )
    return None, [], split.body, split.line_offset


@dataclass
class _BodyAccumulator:
    """Mutable state for one token-stream walk (a single ``parse`` call).

    Extracted from ``parse`` so the walk's ten-odd interdependent accumulators
    live behind two feed methods rather than as loose locals: the body-capture
    caps (``MAX_FIELD_CHARS`` per section, ``MAX_CAPTURED_LINES`` total) and the
    recognized-section collection then read as one coherent object.

    The two cap constants are read as module globals inside the methods (never
    captured as arguments or instance copies) so the ``max_file_bytes`` / cap
    monkeypatch seam that the robustness suite drives on this module still bites.
    """

    title: str | None = None
    # Source lines of any *additional* top-level # titles (exactly one is valid).
    extra_title_lines: list[int] = field(default_factory=list)
    # Current recognized-section key ("problem"/…), None, or the "other" sentinel.
    section: str | None = None
    # Normalized heading of the current ## section, driving generic body capture.
    current_h2: str | None = None
    # Searchable sections in document order, heading/lines preserved as written.
    search_sections: list[SearchSection] = field(default_factory=list)
    current_search: SearchSection | None = None

    problem_lines: list[str] = field(default_factory=list)
    requirement_lines: list[tuple[str, int]] = field(default_factory=list)
    metric_lines: list[str] = field(default_factory=list)
    risk_lines: list[str] = field(default_factory=list)
    # Generic body text per ## section: {normalized heading -> [stripped lines]}.
    section_bodies: dict[str, list[str]] = field(default_factory=dict)
    section_chars: dict[str, int] = field(default_factory=dict)
    captured_lines: int = 0
    truncated_fields: set[str] = field(default_factory=set)
    body_truncated: bool = False
    has: dict[str, bool] = field(
        default_factory=lambda: {
            "problem": False,
            "requirements": False,
            "success_metrics": False,
            "risks": False,
        }
    )

    def feed_heading(self, tok: Token, heading_text: str, offset: int) -> None:
        """Advance section tracking on a ``heading_open`` token."""
        if tok.tag == "h1":
            if self.title is None:
                self.title = heading_text.strip()
            else:
                self.extra_title_lines.append((tok.map[0] + 1 + offset) if tok.map else 0)
            self.section = None  # content directly under the title is ignored
            self.current_h2 = None
            self.current_search = None
        elif tok.tag == "h2":
            normalized = _normalize_heading(heading_text)
            self.current_h2 = normalized
            # Record the heading immediately so empty sections still appear in
            # product.sections (classification keys off heading presence).
            self.section_bodies.setdefault(normalized, [])
            # Searchable section carries the heading exactly as stored, so
            # body-tier snippets render the document's own heading.
            self.current_search = SearchSection(heading=heading_text.strip())
            self.search_sections.append(self.current_search)
            key = _SECTIONS.get(normalized)
            self.section = key
            if key is not None:
                self.has[key] = True
        else:
            self.section = "other"

    def feed_inline(self, tok: Token, offset: int) -> None:
        """Capture body text from an ``inline`` token under the current section."""
        # Once the total captured-line ceiling is hit, stop capturing any further
        # body (generic or recognized): the document is reported truncated and the
        # parse completes rather than accumulating unboundedly (WS4, REQ-003).
        if self.body_truncated:
            return

        # Generic body capture for every ## section (the canonical content map).
        if self.current_h2 is not None:
            self._capture_body(tok, self.current_h2)

        if self.body_truncated or self.section is None or self.section == "other":
            return

        start_line = (tok.map[0] + offset) if tok.map else 0
        lines = _content_lines(tok.content, start_line)
        if self.section == "problem":
            self.problem_lines.extend(t for t, _ in lines)
        elif self.section == "requirements":
            self.requirement_lines.extend(lines)
        elif self.section == "success_metrics":
            self.metric_lines.extend(t for t, _ in lines)
        elif self.section == "risks":
            self.risk_lines.extend(t for t, _ in lines)

    def _capture_body(self, tok: Token, h2: str) -> None:
        """Append this inline's non-blank lines to the current section's body.

        A line is captured only after clearing both caps, in document order; the
        matching ``search_sections`` append is interleaved at the same point so a
        capped document truncates its search lines identically to its body lines
        (the search snippet/scoring goldens depend on this exact coupling).
        """
        for raw in tok.content.split("\n"):
            stripped = raw.strip()
            if not stripped:
                continue
            if self.captured_lines >= MAX_CAPTURED_LINES:
                self.body_truncated = True
                break
            if self.section_chars.get(h2, 0) + len(stripped) > MAX_FIELD_CHARS:
                self.truncated_fields.add(h2)
                continue
            self.section_bodies.setdefault(h2, []).append(stripped)
            self.section_chars[h2] = self.section_chars.get(h2, 0) + len(stripped) + 1
            self.captured_lines += 1
            if self.current_search is not None:
                self.current_search.lines.append(stripped)


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
        return _degraded_product(source_path, [_oversize_issue(cap, "parse")])

    metadata, metadata_issues, body, offset = _split_metadata(text)
    tokens = _PARSER.parse(body)

    acc = _BodyAccumulator()
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            heading_text = tokens[i + 1].content if i + 1 < len(tokens) else ""
            acc.feed_heading(tok, heading_text, offset)
        elif tok.type == "inline" and not (i > 0 and tokens[i - 1].type == "heading_open"):
            # An inline that *is* a heading's text is skipped; everything else is body.
            acc.feed_inline(tok, offset)

    requirements: list[Requirement] = []
    malformed: list[MalformedRequirement] = []
    for line_text, line_no in acc.requirement_lines:
        result = _classify_requirement_line(line_text, line_no)
        if isinstance(result, Requirement):
            requirements.append(result)
        else:
            malformed.append(result)

    # None = section absent; "" = present but empty; otherwise the joined text.
    problem = "\n".join(acc.problem_lines).strip() if acc.has["problem"] else None
    sections = {h: "\n".join(lines) for h, lines in acc.section_bodies.items()}

    # Body-cap findings (WS4, REQ-003): a truncated field or document is reported
    # as a warning — the artifact is served partial, not failed outright. Field
    # warnings emit in sorted order, then the body warning last.
    parse_issues: list[Issue] = []
    for heading in sorted(acc.truncated_fields):
        parse_issues.append(
            Issue(
                "warning",
                "field-truncated",
                f"section {heading!r} exceeds the {MAX_FIELD_CHARS}-char field cap "
                "and was truncated",
            )
        )
    if acc.body_truncated:
        parse_issues.append(
            Issue(
                "warning",
                "body-truncated",
                f"document body exceeds the {MAX_CAPTURED_LINES}-line capture cap "
                "and was truncated",
            )
        )

    return Product(
        title=acc.title,
        extra_title_lines=acc.extra_title_lines,
        problem=problem,
        requirements=requirements,
        malformed_requirements=malformed,
        success_metrics=acc.metric_lines,
        risks=acc.risk_lines,
        sections=sections,
        search_sections=acc.search_sections,
        has_problem_section=acc.has["problem"],
        has_requirements_section=acc.has["requirements"],
        has_metrics_section=acc.has["success_metrics"],
        has_risks_section=acc.has["risks"],
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
            return _degraded_product(path, [_oversize_issue(cap, "file")])
        with open(path, "rb") as fh:
            data = fh.read(cap + 1)
    except OSError as exc:
        return _degraded_product(
            path, [Issue("error", "unreadable-artifact", f"cannot read artifact: {exc}", 1)]
        )
    if len(data) > cap:
        return _degraded_product(path, [_oversize_issue(cap, "file")])

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


def _oversize_issue(cap: int, kind: str) -> Issue:
    """The single ``artifact-oversize`` issue, shared by the in-parse and file paths.

    ``kind`` names the cap that rejected the input ("parse" for the in-memory
    ``parse`` guard, "file" for the on-disk ``parse_file`` size check); only the
    noun differs between the two, and no test or golden pins the message text.
    """
    return Issue(
        "error",
        "artifact-oversize",
        f"artifact exceeds the {cap}-byte {kind} cap (set RAC_MAX_FILE_BYTES to raise it)",
        1,
    )
