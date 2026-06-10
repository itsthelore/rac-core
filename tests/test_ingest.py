"""Tests for document ingestion (`rac ingest`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.services.ingest import (
    MarkdownConverter,
    MarkItDownConverter,
    UnsupportedDocument,
    converter_for,
    ingest,
    supported_extensions,
)

# --- service layer ----------------------------------------------------------


def test_converter_selection_by_extension():
    assert isinstance(converter_for(Path("a.md")), MarkdownConverter)
    assert isinstance(converter_for(Path("a.markdown")), MarkdownConverter)
    for ext in (".docx", ".pdf", ".html", ".htm", ".pptx", ".xls", ".xlsx"):
        assert isinstance(converter_for(Path(f"a{ext}")), MarkItDownConverter), ext
    assert converter_for(Path("a.txt")) is None


def test_supported_extensions():
    exts = set(supported_extensions())
    assert {".md", ".docx", ".pdf", ".html", ".htm", ".pptx", ".xls", ".xlsx"} <= exts


def test_markdown_passthrough():
    result = ingest(fixture_path("ingest", "sample.md"))
    assert result.converter == "markdown"
    assert "[REQ-001] Ingest preserves existing Markdown content" in result.markdown


def test_unsupported_type_raises(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(UnsupportedDocument):
        ingest(str(bad))


def test_missing_extra_message_points_at_right_extra():
    from rac.services.ingest import _missing_extra_message

    assert "[ingest-pdf]" in _missing_extra_message(".pdf")
    assert "[ingest-office]" in _missing_extra_message(".pptx")
    assert "[ingest-office]" in _missing_extra_message(".xlsx")
    assert "[ingest]" in _missing_extra_message(".docx")
    assert "[ingest]" in _missing_extra_message(".html")  # html -> base markitdown


# --- CLI: markdown / error paths (no optional deps needed) ------------------


def test_cli_preview_to_stdout(capsys):
    rc = main(["ingest", fixture_path("ingest", "sample.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# Already Markdown" in out


def test_cli_write_and_overwrite_guard(tmp_path, capsys):
    out = tmp_path / "out.md"
    # First write succeeds.
    assert main(["ingest", fixture_path("ingest", "sample.md"), "-o", str(out)]) == 0
    assert out.read_text().startswith("# Already Markdown")
    # Second write refuses without --force.
    with pytest.raises(SystemExit) as exc:
        main(["ingest", fixture_path("ingest", "sample.md"), "-o", str(out)])
    assert exc.value.code == 2
    # --force overwrites.
    assert main(["ingest", fixture_path("ingest", "sample.md"), "-o", str(out), "--force"]) == 0


def test_cli_unsupported_exits_two(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(SystemExit) as exc:
        main(["ingest", str(bad)])
    assert exc.value.code == 2


def test_cli_missing_file_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["ingest", fixture_path("ingest", "does_not_exist.docx")])
    assert exc.value.code == 2


def test_cli_json_shape(capsys):
    rc = main(["ingest", fixture_path("ingest", "sample.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"source", "converter", "output", "markdown"} <= payload.keys()
    assert payload["converter"] == "markdown"
    assert payload["output"] is None


# --- DOCX via MarkItDown (only when optional deps are installed) ------------

markitdown = pytest.importorskip("markitdown")
docx = pytest.importorskip("docx")


def _make_docx(path: Path) -> None:
    doc = docx.Document()
    doc.add_heading("Bond Dashboard", level=1)
    doc.add_paragraph("Retail investors struggle to understand rate exposure.")
    doc.add_heading("Requirements", level=2)
    doc.add_paragraph("User can view holdings")
    doc.save(str(path))


def test_docx_conversion_preserves_structure(tmp_path):
    src = tmp_path / "spec.docx"
    _make_docx(src)
    result = ingest(str(src))
    assert result.converter == "markitdown"
    assert "# Bond Dashboard" in result.markdown
    assert "## Requirements" in result.markdown
    assert "User can view holdings" in result.markdown


def test_cli_ingest_docx_to_file(tmp_path):
    src = tmp_path / "spec.docx"
    _make_docx(src)
    out = tmp_path / "spec.md"
    assert main(["ingest", str(src), "-o", str(out)]) == 0
    assert "# Bond Dashboard" in out.read_text()


# --- Other formats added in v0.3.1 ------------------------------------------


def test_html_conversion(tmp_path):
    # HTML needs no extra dependency (built into MarkItDown).
    src = tmp_path / "page.html"
    src.write_text("<h1>Bond Dashboard</h1><p>Rate exposure.</p>")
    result = ingest(str(src))
    assert result.converter == "markitdown"
    assert "# Bond Dashboard" in result.markdown


def test_pptx_conversion(tmp_path):
    pptx = pytest.importorskip("pptx")
    src = tmp_path / "deck.pptx"
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Deck Title"
    prs.save(str(src))
    result = ingest(str(src))
    assert result.converter == "markitdown"
    assert "Deck Title" in result.markdown


def test_xlsx_conversion(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    src = tmp_path / "data.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Metric"
    ws["A2"] = "MAU"
    wb.save(str(src))
    result = ingest(str(src))
    assert result.converter == "markitdown"
    assert "Metric" in result.markdown


def test_pdf_conversion(tmp_path):
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    src = tmp_path / "doc.pdf"
    c = canvas.Canvas(str(src))
    c.drawString(72, 720, "PDF heading and body text.")
    c.save()
    result = ingest(str(src))
    assert result.converter == "markitdown"
    assert "PDF heading and body text." in result.markdown


def test_missing_dependency_detection():
    # A per-format missing reader should be recognized so the CLI can map it to
    # a clear "install the ingest extra" message (exit 2), direct or wrapped in
    # MarkItDown's FileConversionException(attempts=...).
    from types import SimpleNamespace

    from markitdown._exceptions import (
        FileConversionException,
        MissingDependencyException,
    )

    from rac.services.ingest import _is_missing_dependency

    assert _is_missing_dependency(MissingDependencyException("x")) is True
    attempt = SimpleNamespace(
        converter=object(),
        exc_info=(MissingDependencyException, MissingDependencyException("y"), None),
    )
    assert _is_missing_dependency(FileConversionException(attempts=[attempt])) is True
    assert _is_missing_dependency(ValueError("unrelated")) is False
