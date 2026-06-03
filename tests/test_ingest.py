"""Tests for document ingestion (`rac ingest`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rac.cli import main
from rac.ingest import (
    MarkdownConverter,
    MarkItDownConverter,
    UnsupportedDocument,
    converter_for,
    ingest,
    supported_extensions,
)

from conftest import fixture_path


# --- service layer ----------------------------------------------------------


def test_converter_selection_by_extension():
    assert isinstance(converter_for(Path("a.md")), MarkdownConverter)
    assert isinstance(converter_for(Path("a.markdown")), MarkdownConverter)
    assert isinstance(converter_for(Path("a.docx")), MarkItDownConverter)
    assert converter_for(Path("a.txt")) is None


def test_supported_extensions():
    assert ".docx" in supported_extensions()
    assert ".md" in supported_extensions()


def test_markdown_passthrough():
    result = ingest(fixture_path("ingest", "sample.md"))
    assert result.converter == "markdown"
    assert "[REQ-001] Ingest preserves existing Markdown content" in result.markdown


def test_unsupported_type_raises(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(UnsupportedDocument):
        ingest(str(bad))


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
    assert main(
        ["ingest", fixture_path("ingest", "sample.md"), "-o", str(out), "--force"]
    ) == 0


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
