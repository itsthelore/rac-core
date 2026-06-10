"""Tests for the canonical corpus traversal seam (v0.7.14)."""

from __future__ import annotations

from pathlib import Path

from rac.core.classification import classify
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.fs import find_markdown_files

FIXTURES = str(Path(__file__).parent / "fixtures")


def test_walk_yields_every_markdown_file_in_sorted_order():
    entries = list(walk_corpus(FIXTURES))
    assert [e.path for e in entries] == find_markdown_files(FIXTURES)


def test_entries_carry_product_and_classification():
    entries = list(walk_corpus(FIXTURES))
    assert entries, "fixture corpus must not be empty"
    for entry in entries:
        assert entry.classification == classify(entry.product)
        assert entry.artifact_type == entry.classification.type


def test_unknown_is_a_valid_outcome(tmp_path):
    (tmp_path / "note.md").write_text("just some prose\n", encoding="utf-8")
    [entry] = list(walk_corpus(str(tmp_path)))
    assert entry.artifact_type == "unknown"


def test_recursive_flag_limits_walk_to_top_level(tmp_path):
    (tmp_path / "top.md").write_text("# Top\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "deep.md").write_text("# Deep\n", encoding="utf-8")

    all_paths = [e.path.name for e in walk_corpus(str(tmp_path))]
    top_only = [e.path.name for e in walk_corpus(str(tmp_path), recursive=False)]
    assert all_paths == ["deep.md", "top.md"]
    assert top_only == ["top.md"]


def test_walk_is_lazy():
    iterator = walk_corpus(FIXTURES)
    first = next(iterator)
    assert isinstance(first, CorpusEntry)
