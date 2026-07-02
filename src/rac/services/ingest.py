"""Turn a source document into Markdown so it can enter the RAC workflow.

`rac ingest <file>` converts an existing document — Markdown already, or a rich
format such as DOCX/PDF/HTML — into Markdown text. Conversion is the whole job
(ADR-006, ingestion over rewrite): the result is *not* judged against any RAC
schema here; classification and validation are separate, later commands.

Each format is handled by a :class:`DocumentConverter` (ADR-008), so a new
source is added by registering another converter and the CLI never changes.
The rich-format converter (ADR-072) is `markitdown`, imported lazily so the
core install — and ``rac ingest file.md`` — works without the optional extras.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from rac.errors import RACError


class ConversionError(RACError):
    """A recognized document could not be converted to Markdown."""


class UnsupportedDocument(ConversionError):
    """No converter handles this file type, or its optional extra is missing."""


@dataclass
class IngestResult:
    """Structured outcome of one ingestion (ADR-003)."""

    source_path: str
    converter: str  # name of the converter that produced ``markdown``
    markdown: str


@runtime_checkable
class DocumentConverter(Protocol):
    """A source document turned into a Markdown string.

    A converter declares the extensions it recognizes and converts a path,
    raising :class:`ConversionError` (or its subclass) when it cannot.
    """

    name: str
    extensions: tuple[str, ...]

    def convert(self, path: Path) -> str: ...


class MarkdownConverter:
    """Pass through files that are already Markdown — no extra dependency."""

    name = "markdown"
    extensions: tuple[str, ...] = (".md", ".markdown")

    def convert(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")


class MarkItDownConverter:
    """Convert rich documents via `markitdown`, an optional dependency (ADR-072).

    The import is deferred to :meth:`convert` (and to :func:`_is_missing_dependency`)
    so nothing here is required by a core install. A missing package, or a
    missing per-format reader extra, is reported as an :class:`UnsupportedDocument`
    that names the extra to install; any other failure is a :class:`ConversionError`.
    """

    name = "markitdown"
    # HTML/HTM are built into markitdown; the remaining formats need reader
    # extras, mapped to our granular ingest extras in ``_EXTRA_FOR_SUFFIX``.
    extensions: tuple[str, ...] = (".docx", ".pdf", ".html", ".htm", ".pptx", ".xls", ".xlsx")

    def convert(self, path: Path) -> str:
        try:
            from markitdown import MarkItDown
        except ModuleNotFoundError as exc:
            raise UnsupportedDocument(_missing_extra_message(path.suffix)) from exc

        try:
            result = MarkItDown().convert(str(path))
        except Exception as exc:  # markitdown surfaces many unrelated error types
            if _is_missing_dependency(exc):
                # The package is present but this format's reader extra is not.
                raise UnsupportedDocument(_missing_extra_message(path.suffix)) from exc
            raise ConversionError(f"could not convert {path.name}: {exc}") from exc
        return result.text_content


# The optional extra that supplies each format's reader. Suffixes absent here —
# ``.html``/``.htm`` — need no extra, so they fall back to the base ``ingest``.
_EXTRA_FOR_SUFFIX = {
    ".docx": "ingest",
    ".pdf": "ingest-pdf",
    ".pptx": "ingest-office",
    ".xls": "ingest-office",
    ".xlsx": "ingest-office",
}


def _missing_extra_message(suffix: str) -> str:
    extra = _EXTRA_FOR_SUFFIX.get(suffix.lower(), "ingest")
    return f"converting '{suffix}' needs the {extra} extra: pip install 'rac-core[{extra}]'"


def _is_missing_dependency(exc: Exception) -> bool:
    """True when ``exc`` is, or wraps, a markitdown missing-dependency error.

    markitdown raises ``MissingDependencyException`` directly for a bare missing
    reader, but also bundles per-attempt failures inside
    ``FileConversionException(attempts=...)``, each attempt keeping the original
    error in ``.exc_info = (type, value, traceback)``. Both shapes count.
    """
    try:
        from markitdown._exceptions import MissingDependencyException
    except Exception:  # pragma: no cover - markitdown not installed
        return False
    if isinstance(exc, MissingDependencyException):
        return True
    for attempt in getattr(exc, "attempts", None) or []:
        info = getattr(attempt, "exc_info", None)
        if info and isinstance(info[1], MissingDependencyException):
            return True
    return False


# Registry ordered by lookup preference; extension sets are disjoint today, so
# the first match is also the only match.
_CONVERTERS: list[DocumentConverter] = [MarkdownConverter(), MarkItDownConverter()]


def converter_for(path: Path) -> DocumentConverter | None:
    """Return the converter that handles ``path``'s extension, or None."""
    suffix = path.suffix.lower()
    for converter in _CONVERTERS:
        if suffix in converter.extensions:
            return converter
    return None


def supported_extensions() -> list[str]:
    """Every extension any registered converter can handle, sorted."""
    return sorted({ext for converter in _CONVERTERS for ext in converter.extensions})


def ingest(path: str) -> IngestResult:
    """Convert ``path`` to Markdown, preserving its structure.

    Raises :class:`UnsupportedDocument` when no converter recognizes the file
    type and :class:`ConversionError` when a recognized document fails to convert.
    """
    source = Path(path)
    converter = converter_for(source)
    if converter is None:
        raise UnsupportedDocument(
            f"unsupported file type '{source.suffix or source.name}'. "
            f"Supported: {', '.join(supported_extensions())}"
        )
    markdown = converter.convert(source)
    return IngestResult(source_path=str(source), converter=converter.name, markdown=markdown)
