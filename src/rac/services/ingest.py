"""Convert source documents into Markdown.

`rac ingest <file>` turns an existing document (DOCX today; HTML/PDF later) into
Markdown so it can enter the RAC workflow. Ingestion's only job is **conversion
that preserves structure** — it does not judge whether the result is a valid RAC
artifact. That is the responsibility of future `inspect` / `normalize` commands.

Per ADR-008 (agent-ready architecture), the logic lives here as a reusable
service behind a :class:`DocumentConverter` abstraction; the CLI is a thin
wrapper. New sources (Notion, Confluence, PDF, ...) are added by registering
another converter — the CLI does not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


class ConversionError(Exception):
    """A document was recognized but could not be converted."""


class UnsupportedDocument(ConversionError):
    """The file type has no registered converter (or a needed extra is missing)."""


@dataclass
class IngestResult:
    """Typed result of an ingestion (ADR-003: structured outputs)."""

    source_path: str
    converter: str  # name of the converter that produced the Markdown
    markdown: str


@runtime_checkable
class DocumentConverter(Protocol):
    """Turns a source document into Markdown.

    Implementations declare the file extensions they handle and convert a path
    to a Markdown string. They should raise :class:`ConversionError` on failure.
    """

    name: str
    extensions: tuple[str, ...]

    def convert(self, path: Path) -> str: ...


class MarkdownConverter:
    """Pass-through for files already in Markdown — needs no extra dependency."""

    name = "markdown"
    extensions: tuple[str, ...] = (".md", ".markdown")

    def convert(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")


class MarkItDownConverter:
    """Convert rich documents to Markdown via MarkItDown (optional dependency).

    Imported lazily so the core install (and `rac ingest file.md`) works without
    the `ingest` extra installed.
    """

    name = "markitdown"
    # HTML needs no extra (built into MarkItDown); the others come from the
    # corresponding markitdown extras, exposed as our granular ingest extras.
    extensions: tuple[str, ...] = (".docx", ".pdf", ".html", ".htm", ".pptx", ".xls", ".xlsx")

    def convert(self, path: Path) -> str:
        try:
            from markitdown import MarkItDown
        except ModuleNotFoundError as exc:
            raise UnsupportedDocument(_missing_extra_message(path.suffix)) from exc

        try:
            result = MarkItDown().convert(str(path))
        except Exception as exc:  # MarkItDown raises a variety of errors
            if _is_missing_dependency(exc):
                # MarkItDown is installed but this format's reader extra isn't.
                raise UnsupportedDocument(_missing_extra_message(path.suffix)) from exc
            raise ConversionError(f"could not convert {path.name}: {exc}") from exc
        return result.text_content


# Which optional extra provides the reader for a given file type. HTML/HTM need
# no extra (built into MarkItDown), so they fall back to the base `ingest`.
_EXTRA_FOR_SUFFIX = {
    ".docx": "ingest",
    ".pdf": "ingest-pdf",
    ".pptx": "ingest-office",
    ".xls": "ingest-office",
    ".xlsx": "ingest-office",
}


def _missing_extra_message(suffix: str) -> str:
    extra = _EXTRA_FOR_SUFFIX.get(suffix.lower(), "ingest")
    return (
        f"converting '{suffix}' needs the {extra} extra: "
        f"pip install 'requirements-as-code[{extra}]'"
    )


def _is_missing_dependency(exc: Exception) -> bool:
    """True if ``exc`` is (or wraps) a MarkItDown missing-dependency error."""
    try:
        from markitdown._exceptions import MissingDependencyException
    except Exception:  # pragma: no cover - defensive
        return False
    if isinstance(exc, MissingDependencyException):
        return True
    # MarkItDown wraps converter failures in FileConversionException(attempts=...),
    # each attempt carrying the original error in .exc_info = (type, value, tb).
    for attempt in getattr(exc, "attempts", None) or []:
        info = getattr(attempt, "exc_info", None)
        if info and isinstance(info[1], MissingDependencyException):
            return True
    return False


# Registry — first converter whose extensions match wins. Order is not currently
# significant since extension sets are disjoint, but kept explicit for clarity.
_CONVERTERS: list[DocumentConverter] = [MarkdownConverter(), MarkItDownConverter()]


def converter_for(path: Path) -> DocumentConverter | None:
    """Return the converter that handles ``path``'s extension, or None."""
    suffix = path.suffix.lower()
    for converter in _CONVERTERS:
        if suffix in converter.extensions:
            return converter
    return None


def supported_extensions() -> list[str]:
    """All file extensions any registered converter can handle."""
    return sorted({ext for c in _CONVERTERS for ext in c.extensions})


def ingest(path: str) -> IngestResult:
    """Convert ``path`` to Markdown, preserving its structure.

    Raises :class:`UnsupportedDocument` for unhandled file types and
    :class:`ConversionError` when a recognized document fails to convert.
    """
    p = Path(path)
    converter = converter_for(p)
    if converter is None:
        raise UnsupportedDocument(
            f"unsupported file type '{p.suffix or p.name}'. "
            f"Supported: {', '.join(supported_extensions())}"
        )
    markdown = converter.convert(p)
    return IngestResult(source_path=str(p), converter=converter.name, markdown=markdown)
