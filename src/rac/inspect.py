"""Artifact inspection — classify Markdown documents and report their structure.

`rac inspect <file>` answers, for a single document: *what kind of artifact is
this, how confident are we, and which expected sections are present / missing?*
For Decisions it also surfaces lightweight metadata (status, category, supersedes)
when present. `rac inspect <dir>` aggregates the type across a directory into
counts. It is strictly observational — it never modifies content and never
recommends changes (that is a future `improve` command's job). Classification is
delegated to :mod:`rac.classification` (the shared, AI-optional heuristic).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .artifacts import ARTIFACT_SPECS, spec_for
from .classification import classify
from .fs import find_markdown_files
from .models import Product
from .parser import parse, parse_file
from .relationships import extract_relationships


@dataclass
class InspectionResult:
    """Typed single-file inspection result (ADR-003).

    Section names are stored normalized (e.g. ``"success metrics"``); renderers
    format them. ``to_dict`` is the JSON contract and is additive-friendly:
    decision metadata fields and ``relationships`` appear only when present.
    """

    type: str  # artifact name, or "unknown"
    confidence: float  # 0.0 – 1.0 (rounded to 2dp)
    present_sections: list[str]
    missing_sections: list[str]
    # Decision metadata — populated only for decisions that declare it.
    status: str | None = None
    category: str | None = None
    # ``supersedes`` is a relationship section but, for backwards compatibility
    # (v0.4.2 / ADR-007), it stays a top-level scalar here rather than going into
    # ``relationships`` — the documented exception to the v0.7.0 model.
    supersedes: str | None = None
    # Cross-artifact relationship metadata (v0.7.0): {snake_section -> [refs]}.
    # Holds only the ``related_*`` sections; never resolved or validated.
    relationships: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "type": self.type,
            "confidence": self.confidence,
            "present_sections": [_snake(s) for s in self.present_sections],
            "missing_sections": [_snake(s) for s in self.missing_sections],
        }
        for key in ("status", "category", "supersedes"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        # Additive: only present when the artifact declares relationship sections.
        if self.relationships:
            payload["relationships"] = self.relationships
        return payload


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


def _first_line(body: str) -> str:
    """The first non-empty line of a section body (single-value metadata)."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def canonical_value(raw: str, allowed: tuple[str, ...]) -> str:
    """Match ``raw`` against ``allowed`` case-insensitively, returning the
    canonical spelling; if it matches nothing, return it stripped (an invalid
    value that validation will flag)."""
    candidate = _first_line(raw)
    for value in allowed:
        if value.casefold() == candidate.casefold():
            return value
    return candidate


def _attach_decision_metadata(result: InspectionResult, product: Product) -> None:
    spec = spec_for("decision")
    if spec is None:  # pragma: no cover - decision spec always exists
        return
    for field_name, allowed in spec.metadata.items():
        body = product.sections.get(field_name)
        if body:
            setattr(result, field_name, canonical_value(body, allowed))
    supersedes = product.sections.get("supersedes")
    if supersedes:
        # Metadata only (REQ-003): no validation, just normalize the value.
        result.supersedes = _first_line(supersedes)


def build_inspection(product: Product) -> InspectionResult:
    """Classify ``product``, attach decision metadata and relationships."""
    c = classify(product)
    result = InspectionResult(
        type=c.type,
        confidence=c.confidence,
        present_sections=c.present_sections,
        missing_sections=c.missing_sections,
    )
    if c.type == "decision":
        _attach_decision_metadata(result, product)
    # Relationship metadata is spec-driven, so it applies to any recognized type
    # (Unknown has no spec and therefore no relationships).
    spec = spec_for(c.type)
    if spec is not None:
        result.relationships = extract_relationships(product, spec)
    return result


def inspect_text(text: str) -> InspectionResult:
    return build_inspection(parse(text))


def inspect_file(path: str) -> InspectionResult:
    return build_inspection(parse_file(path))


def inspect_directory(directory: str, recursive: bool = True) -> DirectoryInspection:
    """Inspect every Markdown file under ``directory`` and aggregate the types."""
    files = []
    for path in find_markdown_files(directory, recursive=recursive):
        result = inspect_file(str(path))
        files.append(
            FileInspection(path=str(path), type=result.type, confidence=result.confidence)
        )
    return DirectoryInspection(directory=directory, recursive=recursive, files=files)
