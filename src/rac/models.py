"""The Product AST and result types.

These dataclasses are the *only* thing validation, diffing, and future analysis
should operate on. The parser (``rac.parser``) is responsible for turning a
Markdown file into a :class:`Product`; everything downstream reads the AST, never
the raw text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass
class Requirement:
    """A single requirement line, e.g. ``[REQ-001] User can view data``."""

    id: str  # canonical ID, preserved exactly (e.g. "REQ-001")
    text: str  # the description following the ID
    line: int  # 1-based source line, for diagnostics


@dataclass
class MalformedRequirement:
    """A non-empty line under ``## Requirements`` that is not a valid requirement.

    Captured (rather than dropped) so validation can report *why* it is invalid
    instead of silently ignoring it.
    """

    raw: str  # the raw line text
    line: int
    # The parsed ID if one was found but is malformed (e.g. "REQ-1A"); None if
    # the line had no recognizable ID prefix at all.
    bad_id: str | None = None
    # True when an ID was present and well-formed but the description was blank.
    empty_text: bool = False


@dataclass
class Product:
    """The structured representation of a single requirement file."""

    title: str | None
    # Source lines of any *additional* top-level # titles (a file must have
    # exactly one). Empty in a well-formed file.
    extra_title_lines: list[int] = field(default_factory=list)
    problem: str | None = None  # None = section absent; "" = present but empty
    requirements: list[Requirement] = field(default_factory=list)
    malformed_requirements: list[MalformedRequirement] = field(default_factory=list)
    success_metrics: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    # Every ``##`` section as {normalized heading -> stripped body text}, in
    # document order. The canonical source of section content for all artifact
    # types: classification, inspection metadata, and validation read from here
    # rather than re-parsing the Markdown.
    sections: dict[str, str] = field(default_factory=dict)
    # Distinguish "section absent" from "section present but empty".
    has_problem_section: bool = False
    has_requirements_section: bool = False
    has_metrics_section: bool = False
    has_risks_section: bool = False
    source_path: str = ""


@dataclass
class Issue:
    """A validation finding."""

    severity: Severity
    code: str  # stable machine code, e.g. "missing-title", "ambiguous-verb"
    message: str  # human-readable explanation
    line: int | None = None


@dataclass
class RequirementChange:
    """A requirement whose text changed between two versions (same ID)."""

    id: str
    old_text: str
    new_text: str


@dataclass
class Diff:
    """The classified differences between two :class:`Product` ASTs."""

    added_requirements: list[Requirement] = field(default_factory=list)
    removed_requirements: list[Requirement] = field(default_factory=list)
    modified_requirements: list[RequirementChange] = field(default_factory=list)
    added_metrics: list[str] = field(default_factory=list)
    removed_metrics: list[str] = field(default_factory=list)
    added_risks: list[str] = field(default_factory=list)
    removed_risks: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """True when nothing changed across any comparison unit."""
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
