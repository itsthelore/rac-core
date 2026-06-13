"""Tests for git revision materialization (ADR-042).

Each test builds a throwaway git repository under ``tmp_path`` — the suite
never touches this repository's own git state, and materialization must
never mutate the throwaway repository's either.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rac.services.revisions import (
    NotAGitRepository,
    RevisionNotFound,
    materialized_revision,
    repository_root,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            # Throwaway repos must not depend on the host's signing setup.
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "checkout.md").write_text(
        "# Checkout\n\n## Requirements\n\n[REQ-001] User can pay\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("not corpus\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "initial")
    return tmp_path


def test_repository_root(repo: Path):
    assert repository_root(str(repo / "rac")) == str(repo.resolve())


def test_repository_root_outside_git(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(NotAGitRepository):
        repository_root(str(plain))


def test_materializes_corpus_subpath_byte_for_byte(repo: Path):
    original = (repo / "rac" / "requirements" / "checkout.md").read_text(encoding="utf-8")
    with materialized_revision(str(repo), "main", "rac") as corpus:
        assert (corpus / "requirements" / "checkout.md").read_text(encoding="utf-8") == original
        # Only the corpus subpath is extracted.
        assert not (corpus.parent / "README.md").exists()


def test_materialization_reflects_the_revision_not_the_working_tree(repo: Path):
    target = repo / "rac" / "requirements" / "checkout.md"
    committed = target.read_text(encoding="utf-8")
    target.write_text(committed + "\n[REQ-002] Uncommitted line\n", encoding="utf-8")
    with materialized_revision(str(repo), "main", "rac") as corpus:
        assert (corpus / "requirements" / "checkout.md").read_text(encoding="utf-8") == committed


def test_temporary_directory_is_removed_on_exit(repo: Path):
    with materialized_revision(str(repo), "main", "rac") as corpus:
        kept = corpus
        assert kept.is_dir()
    assert not kept.exists()


def test_unknown_revision_raises(repo: Path):
    with pytest.raises(RevisionNotFound):
        with materialized_revision(str(repo), "no-such-branch", "rac"):
            pass  # pragma: no cover


def test_missing_subpath_yields_empty_corpus(repo: Path):
    with materialized_revision(str(repo), "main", "docs") as corpus:
        assert corpus.is_dir()
        assert list(corpus.iterdir()) == []


def test_materialization_does_not_mutate_git_state(repo: Path):
    worktrees = repo / ".git" / "worktrees"
    with materialized_revision(str(repo), "main", "rac"):
        assert not worktrees.exists()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--ignored=matching"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    # The uncommitted working tree is untouched: nothing new appears.
    assert "rac-watchkeeper" not in status.stdout
