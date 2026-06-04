"""Artifact inspection — classify a Markdown document and report its structure.

`rac inspect <file>` answers, for a single document: *what kind of artifact is
this, how confident are we, and which expected sections are present / missing?*
It is strictly observational — it never modifies content and never recommends
changes (that is v0.5 `improve`'s job). Classification is a pure heuristic over
the document's ``##`` section headings (ADR-002: AI-optional); it consumes the
shared schemas in :mod:`rac.artifacts`.
"""

from __future__ import annotations

from dataclasses import dataclass

from markdown_it import MarkdownIt

from .artifacts import ARTIFACT_SPECS
from .parser import _normalize_heading

# Below this best-fit score, the document is reported as Unknown rather than
# forced into a type. Unknown is a valid, successful outcome — not an error.
CONFIDENCE_THRESHOLD = 0.5


@dataclass
class DocumentSections:
    """The structural skeleton of a document: its title and ``##`` headings."""

    title: str | None
    headings: list[str]  # normalized h2 section names, in document order


@dataclass
class InspectionResult:
    """Typed inspection result (ADR-003).

    Section names are stored normalized (e.g. ``"success metrics"``); the
    renderers format them for display/JSON. ``to_dict`` is the JSON contract and
    is intentionally additive-friendly — future keys (e.g. ``schema_version``)
    can be added without breaking existing consumers.
    """

    type: str  # artifact name, or "unknown"
    confidence: float  # 0.0 – 1.0
    present_sections: list[str]
    missing_sections: list[str]

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "confidence": self.confidence,
            "present_sections": [_snake(s) for s in self.present_sections],
            "missing_sections": [_snake(s) for s in self.missing_sections],
        }


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


def classify(sections: DocumentSections) -> InspectionResult:
    """Pick the best-fit artifact type for ``sections`` (or Unknown)."""
    best_spec = None
    best_fit = 0.0
    best_required_hits = -1

    for spec in ARTIFACT_SPECS:
        mapped = {spec.aliases.get(h, h) for h in sections.headings}
        required_hits = sum(1 for s in spec.required if s in mapped)
        recommended_hits = sum(1 for s in spec.recommended if s in mapped)
        raw = required_hits + 0.5 * recommended_hits
        ceiling = len(spec.required) + 0.5 * len(spec.recommended)
        fit = raw / ceiling if ceiling else 0.0
        # Highest fit wins; ties broken by more required matches, then by the
        # order of ARTIFACT_SPECS (we only replace on a strict improvement).
        if (fit, required_hits) > (best_fit, best_required_hits):
            best_fit, best_required_hits, best_spec = fit, required_hits, spec

    confidence = round(best_fit, 2)

    if best_spec is None or best_fit < CONFIDENCE_THRESHOLD or best_required_hits == 0:
        return InspectionResult(
            type="unknown",
            confidence=confidence,
            present_sections=list(sections.headings),
            missing_sections=[],
        )

    mapped = {best_spec.aliases.get(h, h) for h in sections.headings}
    present = [s for s in best_spec.expected if s in mapped]
    missing = [s for s in best_spec.expected if s not in mapped]
    return InspectionResult(
        type=best_spec.name,
        confidence=confidence,
        present_sections=present,
        missing_sections=missing,
    )


def inspect_text(text: str) -> InspectionResult:
    return classify(extract_sections(text))


def inspect_file(path: str) -> InspectionResult:
    with open(path, encoding="utf-8") as fh:
        return inspect_text(fh.read())
