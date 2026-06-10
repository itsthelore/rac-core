"""Tests for operation primitives and the corpus snapshot (v0.8.0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.core.corpus import collect_corpus, walk_corpus
from rac.core.operations import (
    CancellationToken,
    OperationCancelled,
    Progress,
    checkpoint,
)

FIXTURES = str(Path(__file__).parent / "fixtures")


def test_checkpoint_passes_without_token():
    checkpoint(None)


def test_checkpoint_passes_with_live_token():
    checkpoint(CancellationToken())


def test_checkpoint_raises_once_cancelled():
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        checkpoint(token)


def test_cancellation_is_one_way():
    token = CancellationToken()
    assert not token.cancelled
    token.cancel()
    token.cancel()
    assert token.cancelled


def test_collect_matches_walk_order():
    entries = collect_corpus(FIXTURES)
    assert [e.path for e in entries] == [e.path for e in walk_corpus(FIXTURES)]


def test_collect_reports_monotonic_progress_with_known_total():
    reports: list[Progress] = []
    entries = collect_corpus(FIXTURES, on_progress=reports.append)

    assert [r.completed for r in reports] == list(range(1, len(entries) + 1))
    assert {r.total for r in reports} == {len(entries)}
    assert {r.phase for r in reports} == {"scan"}


def test_collect_cancels_before_completing(tmp_path):
    for i in range(5):
        (tmp_path / f"doc-{i}.md").write_text(f"# Doc {i}\n", encoding="utf-8")

    token = CancellationToken()
    parsed: list[Progress] = []

    def cancel_after_two(progress: Progress) -> None:
        parsed.append(progress)
        if progress.completed == 2:
            token.cancel()

    with pytest.raises(OperationCancelled):
        collect_corpus(str(tmp_path), on_progress=cancel_after_two, cancel=token)
    assert len(parsed) == 2


def test_collect_respects_recursive_flag(tmp_path):
    (tmp_path / "top.md").write_text("# Top\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "deep.md").write_text("# Deep\n", encoding="utf-8")

    top_only = collect_corpus(str(tmp_path), recursive=False)
    assert [e.path.name for e in top_only] == ["top.md"]
