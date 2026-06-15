"""Git revision materialization — the only git-aware module in RAC (ADR-042).

Watchkeeper compares directories; git enters exactly once, here, to turn a
revision name into a temporary directory holding the corpus subpath at that
revision. ``git archive`` is used deliberately: it never mutates ``.git``
state (no worktree registration, no locks, safe under concurrent CI runs),
extracts only the corpus subpath, and works offline.

A revision that exists but does not contain the subpath materializes an
empty directory — an empty base corpus is a valid "everything added"
comparison (the fresh-adoption case).
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from rac.errors import RACError


class NotAGitRepository(RACError):
    """The directory is not inside a git work tree (or git is unavailable)."""


class RevisionNotFound(RACError):
    """The named revision does not resolve to a commit."""


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    except FileNotFoundError as exc:  # no git binary on PATH
        raise NotAGitRepository("git executable not found") from exc


def repository_root(directory: str) -> str:
    """The work-tree root of the git repository containing ``directory``."""
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=directory)
    if result.returncode != 0:
        raise NotAGitRepository(f"not a git repository: {directory}")
    return result.stdout.decode("utf-8").strip()


@contextmanager
def materialized_revision(repo_root: str, rev: str, subpath: str) -> Iterator[Path]:
    """Yield a temporary directory holding ``subpath`` as of ``rev``.

    The directory (and everything extracted into it) is removed on exit.
    Raises :class:`RevisionNotFound` when ``rev`` is not a commit.
    """
    verify = _run_git(["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], cwd=repo_root)
    if verify.returncode != 0:
        raise RevisionNotFound(f"unknown revision: {rev}")

    pathspec = subpath if subpath not in ("", ".") else "."
    archive = _run_git(["archive", "--format=tar", rev, "--", pathspec], cwd=repo_root)

    with tempfile.TemporaryDirectory(prefix="rac-watchkeeper-") as tmp:
        target = Path(tmp)
        if archive.returncode == 0:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                tar.extractall(target, filter="data")
        # A nonzero archive exit means the subpath does not exist at ``rev``:
        # materialize an empty corpus rather than failing the comparison.
        corpus = target if pathspec == "." else target / subpath
        corpus.mkdir(parents=True, exist_ok=True)
        yield corpus
