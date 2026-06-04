"""Artifact inspection — classify Markdown documents and report their structure.

`rac inspect <file>` answers, for a single document: *what kind of artifact is
this, how confident are we, and which expected sections are present / missing?*
`rac inspect <dir>` aggregates that across a directory into type counts. It is
strictly observational — it never modifies content and never recommends changes
(that is a future `improve` command's job). Classification is a pure heuristic
over the document's ``##`` section headings (ADR-002: AI-optional), consuming the
shared schemas in :mod:`rac.artifacts`.
"""

from __future__ import annotations

from dataclasses import dataclass

from markdown_it import MarkdownIt

from .artifacts import ARTIFACT_SPECS
from .parser import _normalize_heading
from .stats import find_markdown_files

# Below this best-fit score, the document is reported as Unknown rather than
# forced into a type. Unknown is a valid, successful outcome — not an error.
CONFIDENCE_THRESHOLD = 0.5


@dataclass
class DocumentSections:
    """The structural skeleton of a document: its title and ``##`` headings."""

    title: str | None
    headings: list[str]  # normalized h2 section names, in document order


@dataclass
class TypeScore:
    """How well a document fits one artifact type — the explainable breakdown."""

    name: str
    display: str
    matched_required: list[str]
    matched_recommended: list[str]
    missing: list[str]
    points: float  # matched_required + 0.5 * matched_recommended
    ceiling: float  # |required| + 0.5 * |recommended|
    fit: float  # points / ceiling, 0.0 – 1.0 (unrounded)


@dataclass
class InspectionResult:
    """Typed single-file inspection result (ADR-003).

    Section names are stored normalized (e.g. ``"success metrics"``); renderers
    format them. ``to_dict`` is the JSON contract and is additive-friendly.
    """

    type: str  # artifact name, or "unknown"
    confidence: float  # 0.0 – 1.0 (rounded to 2dp)
    present_sections: list[str]
    missing_sections: list[str]

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "confidence": self.confidence,
            "present_sections": [_snake(s) for s in self.present_sections],
            "missing_sections": [_snake(s) for s in self.missing_sections],
        }


@dataclass
class FileInspection:
    """One file's result inside a directory inspection (flat — path/type/conf)."""

    path: str
    type: str
    confidence: float


@dataclass
class DirectoryInspection:
    """Aggregated inspection across a directory of Markdown files."""

    directory: str
    recursive: bool
    files: list[FileInspection]

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def counts(self) -> dict[str, int]:
        # Known types first (in ARTIFACT_SPECS order), then unknown.
        counts = {spec.name: 0 for spec in ARTIFACT_SPECS}
        counts["unknown"] = 0
        for f in self.files:
            counts[f.type] = counts.get(f.type, 0) + 1
        return counts

    @property
    def unknown_count(self) -> int:
        return self.counts.get("unknown", 0)


def _snake(section: str) -> str:
    return section.replace(" ", "_")


def extract_sections(text: str) -> DocumentSections:
    """Pull the ``#`` title and ordered, normalized ``##`` headings from Markdown."""
    tokens = MarkdownIt("commonmark").parse(text)
    title: str | None = None
    headings: list[str] = []
    for i, tok in enumerate(tokens):
        if tok.type != "heading_open":
            continue
        content = tokens[i + 1].content if i + 1 < len(tokens) else ""
        if tok.tag == "h1" and title is None:
            title = content.strip()
        elif tok.tag == "h2":
            headings.append(_normalize_heading(content))
    return DocumentSections(title=title, headings=headings)


def score_artifacts(sections: DocumentSections) -> list[TypeScore]:
    """Score the document against every artifact type, best fit first.

    Synonyms (e.g. "success criteria" -> "success metrics") are applied before
    matching, so they contribute to the score deterministically.
    """
    scores: list[TypeScore] = []
    for spec in ARTIFACT_SPECS:
        mapped = {spec.synonyms.get(h, h) for h in sections.headings}
        matched_required = [s for s in spec.required if s in mapped]
        matched_recommended = [s for s in spec.recommended if s in mapped]
        missing = [s for s in spec.expected if s not in mapped]
        points = len(matched_required) + 0.5 * len(matched_recommended)
        ceiling = len(spec.required) + 0.5 * len(spec.recommended)
        fit = points / ceiling if ceiling else 0.0
        scores.append(
            TypeScore(
                name=spec.name,
                display=spec.display,
                matched_required=matched_required,
                matched_recommended=matched_recommended,
                missing=missing,
                points=points,
                ceiling=ceiling,
                fit=fit,
            )
        )
    # Best fit first; ties broken by more required matches, then ARTIFACT_SPECS
    # order (stable sort preserves it).
    scores.sort(key=lambda t: (t.fit, len(t.matched_required)), reverse=True)
    return scores


def classify(sections: DocumentSections) -> InspectionResult:
    """Pick the best-fit artifact type for ``sections`` (or Unknown)."""
    scores = score_artifacts(sections)
    best = scores[0] if scores else None

    if best is None or best.fit < CONFIDENCE_THRESHOLD or not best.matched_required:
        return InspectionResult(
            type="unknown",
            confidence=round(best.fit, 2) if best else 0.0,
            present_sections=list(sections.headings),
            missing_sections=[],
        )

    return InspectionResult(
        type=best.name,
        confidence=round(best.fit, 2),
        present_sections=best.matched_required + best.matched_recommended,
        missing_sections=best.missing,
    )


def inspect_text(text: str) -> InspectionResult:
    return classify(extract_sections(text))


def inspect_file(path: str) -> InspectionResult:
    with open(path, encoding="utf-8") as fh:
        return inspect_text(fh.read())


def inspect_directory(directory: str, recursive: bool = True) -> DirectoryInspection:
    """Inspect every Markdown file under ``directory`` and aggregate the types."""
    files = []
    for path in find_markdown_files(directory, recursive=recursive):
        result = inspect_file(str(path))
        files.append(
            FileInspection(path=str(path), type=result.type, confidence=result.confidence)
        )
    return DirectoryInspection(directory=directory, recursive=recursive, files=files)
