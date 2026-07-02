"""The Product AST and result dataclasses.

Everything downstream of the parser — classification, validation, diffing,
relationship analysis, the MCP surface, the CLI — reads these types, never the
raw Markdown. That makes the *shape* of this AST a contract: field names, field
order (several types are built positionally), and defaults are all load-bearing.

All types here are plain ``@dataclass`` instances: mutable (the parser and the
diff service append to their list fields in place) and unslotted (nothing relies
on ``__slots__``, and slotting would interfere with the positional/keyword
construction callers depend on).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    # Type-only import: ``ArtifactMetadata`` lives in ``rac.core.metadata``,
    # which imports from this module. Importing it for real would close a cycle;
    # ``from __future__ import annotations`` keeps the annotation a string.
    from .metadata import ArtifactMetadata

# The two severities an Issue can carry. A Literal (not an Enum) so issues stay
# trivially serialisable and compare directly against bare strings in tests.
Severity = Literal["error", "warning"]


@dataclass
class Requirement:
    """A well-formed requirement line, e.g. ``[REQ-001] User can view data``.

    Built positionally by the parser, so the ``id, text, line`` order is part of
    the contract.
    """

    id: str  # canonical requirement ID, preserved verbatim (zero-padding kept)
    text: str  # the description following the bracketed ID
    line: int  # 1-based source line, for diagnostics


@dataclass
class MalformedRequirement:
    """A non-empty line under ``## Requirements`` that is not a valid requirement.

    Kept rather than dropped so validation can explain *why* the line was
    rejected instead of silently ignoring it. The optional flags record how far
    parsing got: ``bad_id`` is the recognised-but-malformed ID (None when the
    line had no ID prefix at all), and ``empty_text`` marks a valid ID whose
    description was blank.
    """

    raw: str
    line: int
    bad_id: str | None = None
    empty_text: bool = False


@dataclass
class SearchSection:
    """One ``##`` section's searchable content, original text preserved.

    Distinct from :attr:`Product.sections` (which casefolds the heading and
    joins the body for classification): the body search tier needs the heading
    exactly as written and each non-blank body line stripped but otherwise
    verbatim, in document order, so snippets render the document's own words.
    """

    heading: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Product:
    """The structured representation of a single artifact file.

    ``title`` is the sole required field and stays first; every other field
    carries a default so a Product can be built from a title alone (including on
    the degraded-parse path). Fields here are only ever *added* — renaming or
    removing one breaks a downstream reader.
    """

    title: str | None
    # Source lines of any *extra* top-level ``#`` titles. A well-formed file has
    # exactly one, so this is empty; entries flag the duplicates for validation.
    extra_title_lines: list[int] = field(default_factory=list)
    # None distinguishes "section absent" from "" ("present but empty").
    problem: str | None = None
    requirements: list[Requirement] = field(default_factory=list)
    malformed_requirements: list[MalformedRequirement] = field(default_factory=list)
    success_metrics: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    # Every ``##`` section as {normalised heading -> joined body}, in document
    # order. The canonical source of section text for all artifact types:
    # classification, inspection, and validation read from here, never the raw
    # Markdown.
    sections: dict[str, str] = field(default_factory=dict)
    # The same sections with original-case headings and per-line body text, for
    # the body search tier — kept apart from ``sections`` so that one can
    # normalise headings and join bodies without disturbing snippet rendering.
    search_sections: list[SearchSection] = field(default_factory=list)
    # Presence flags that distinguish "absent" from "present but empty".
    has_problem_section: bool = False
    has_requirements_section: bool = False
    has_metrics_section: bool = False
    has_risks_section: bool = False
    source_path: str = ""
    # Canonical machine-operational metadata from the YAML frontmatter envelope
    # (ADR-025); None for legacy artifacts without a frontmatter block.
    metadata: ArtifactMetadata | None = None
    # Frontmatter parse/schema findings, surfaced by validation — kept apart
    # from body analysis because the envelope and the artifact are distinct
    # concerns.
    metadata_issues: list[Issue] = field(default_factory=list)
    # Parser-level robustness findings: oversize input, a truncated field,
    # non-UTF-8 content, or an unreadable file. A degraded Product carries these
    # so it is reported (and skipped) rather than crashing the corpus walk.
    parse_issues: list[Issue] = field(default_factory=list)


@dataclass
class Issue:
    """A single finding.

    Constructed positionally throughout the codebase and tests
    (``Issue("error", "code", "message", 1)``), so this field order is contract.
    """

    severity: Severity
    code: str  # stable machine code, e.g. "malformed-frontmatter"
    message: str  # human-readable explanation
    line: int | None = None


@dataclass
class RequirementChange:
    """A requirement whose text changed between two versions of an artifact."""

    id: str
    old_text: str
    new_text: str


@dataclass
class Diff:
    """The classified differences between two :class:`Product` ASTs.

    The diff service default-constructs this and appends to the list fields in
    place, so every field defaults to an empty list.
    """

    added_requirements: list[Requirement] = field(default_factory=list)
    removed_requirements: list[Requirement] = field(default_factory=list)
    modified_requirements: list[RequirementChange] = field(default_factory=list)
    added_metrics: list[str] = field(default_factory=list)
    removed_metrics: list[str] = field(default_factory=list)
    added_risks: list[str] = field(default_factory=list)
    removed_risks: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """True when no comparison unit changed."""
        return not any(
            (
                self.added_requirements,
                self.removed_requirements,
                self.modified_requirements,
                self.added_metrics,
                self.removed_metrics,
                self.added_risks,
                self.removed_risks,
            )
        )
