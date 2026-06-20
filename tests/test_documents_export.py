"""Tests for `rac export --documents` (v0.25.0 WS1, requirement
rac-corpus-documents-export).

The JSONL projection is a stable, additive contract (ADR-007) feeding external
memory/RAG backends: one record per classified artifact, a Markdown body (not the
viewer's HTML), and metadata carrying the canonical id/type/status for the
verify-in-Lore loop. These tests pin the shape, the determinism (ADR-002), and
that the default viewer JSON is left untouched.
"""

from __future__ import annotations

import json

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.services.export import build_corpus_export, build_documents_export

EXIT_USAGE = 2


# --- service layer -----------------------------------------------------------


def test_build_documents_skips_unknown_and_orders_by_path():
    export = build_documents_export(fixture_path("export"))
    # Four Markdown files, one unclassifiable: only classified artifacts project,
    # matching the viewer export's gate.
    assert export.document_count == build_corpus_export(fixture_path("export")).artifact_count
    assert export.document_count == 3
    paths = [d.path for d in export.documents]
    assert paths == sorted(paths)
    assert "random-notes" not in {d.id for d in export.documents}


def test_text_is_markdown_not_html():
    export = build_documents_export(fixture_path("export"))
    by_id = {d.id: d for d in export.documents}
    body = by_id["RAC-00000000EXP1"].text
    # The Markdown source is carried verbatim: headings stay '#'/'##', never
    # rendered to <h1>/<p> the way the viewer's body_html would.
    assert body.startswith("# ADR-001")
    assert "## Status" in body
    assert "<h1>" not in body and "<p>" not in body


def test_record_carries_verify_metadata_and_canonical_id():
    export = build_documents_export(fixture_path("export"))
    record = export.documents[0].to_dict(export.corpus_name)
    assert record["schema_version"] == "1"
    assert record["id"] == "RAC-00000000EXP1"  # the verify-in-Lore re-fetch hook
    assert record["type"] == "decision"
    assert record["status"] == "Accepted"
    meta = record["metadata"]
    assert set(meta) == {"path", "aliases", "tags", "source"}
    assert meta["source"] == "export"
    assert record["id"] in meta["aliases"]


def test_status_canonicalized_and_retired_not_dropped():
    export = build_documents_export(fixture_path("export"))
    by_id = {d.id: d for d in export.documents}
    # Lowercase 'proposed' in the source canonicalizes; the artifact is present,
    # not filtered out — all classified artifacts ship with status stamped.
    assert by_id["notes-raw-html"].status == "Proposed"


def test_build_documents_deterministic():
    first = build_documents_export(fixture_path("export")).to_records()
    second = build_documents_export(fixture_path("export")).to_records()
    assert first == second


# --- CLI ---------------------------------------------------------------------


def test_cli_documents_emits_jsonl(capsys):
    assert main(["export", fixture_path("export"), "--documents"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)  # each line is a standalone JSON object
        assert record["schema_version"] == "1"
        assert record["id"] and record["type"] and record["title"]
        assert isinstance(record["text"], str)
        assert record["metadata"]["source"] == "export"


def test_cli_documents_deterministic(capsys):
    assert main(["export", fixture_path("export"), "--documents"]) == 0
    first = capsys.readouterr().out
    assert main(["export", fixture_path("export"), "--documents"]) == 0
    assert capsys.readouterr().out == first


def test_cli_documents_leaves_default_export_untouched(capsys):
    assert main(["export", fixture_path("export"), "--documents"]) == 0
    documents = capsys.readouterr().out
    assert main(["export", fixture_path("export")]) == 0
    viewer = capsys.readouterr().out
    # Additive: the default mode is still the viewer JSON payload, distinct from
    # the JSONL projection.
    assert documents != viewer
    assert '"corpus"' in viewer and '"body_html"' in viewer
    assert '"body_html"' not in documents


def test_cli_documents_out_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["export", fixture_path("export"), "--documents", "--out", "x.jsonl"])
    assert exc.value.code == EXIT_USAGE
    assert "--out requires" in capsys.readouterr().err
