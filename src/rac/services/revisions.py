"""Git revision materialization — one of RAC's two git touchpoints (ADR-042/043).

Watchkeeper compares two corpus snapshots; git enters here to turn a revision
name into a temporary directory holding the corpus subpath at that revision.
``git archive`` is chosen deliberately over a worktree or checkout: it reads the
object store without registering a worktree, taking a lock, or touching the
index, so it is safe under concurrent CI runs and leaves ``.git`` untouched.

A revision that exists but does not contain the subpath materializes an empty
directory rather than failing: an empty base corpus is the valid "everything was
added" comparison (the fresh-adoption case).
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
    """The directory is not inside a git work tree, or git is unavailable."""


class RevisionNotFound(RACError):
    """The named revision does not resolve to a commit."""


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[bytes]:
    """Run ``git`` in ``cwd`` capturing raw bytes; do not raise on a nonzero exit.

    Callers read ``returncode`` to tell normal outcomes apart (unknown revision,
    absent subpath). A missing git binary is the one failure that cannot be a
    routine outcome, so it surfaces as :class:`NotAGitRepository`.
    """
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    except FileNotFoundError as exc:
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

    The directory and everything extracted into it are removed on exit. Raises
    :class:`RevisionNotFound` when ``rev`` does not name a commit.
    """
    # Resolve to a commit up front so an unknown revision fails cleanly instead of
    # yielding a confusing empty archive.
    verify = _run_git(["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], cwd=repo_root)
    if verify.returncode != 0:
        raise RevisionNotFound(f"unknown revision: {rev}")

    # An empty or "." subpath archives the whole tree; anything else scopes the
    # archive to that subpath so only the corpus is extracted.
    pathspec = subpath if subpath not in ("", ".") else "."
    archive = _run_git(["archive", "--format=tar", rev, "--", pathspec], cwd=repo_root)

    with tempfile.TemporaryDirectory(prefix="rac-watchkeeper-") as tmp:
        target = Path(tmp)
        if archive.returncode == 0:
            # ``filter="data"`` blocks path traversal and special members; the
            # archive is git-produced but still treated as untrusted on extract.
            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                tar.extractall(target, filter="data")
        # A nonzero archive exit means the subpath does not exist at ``rev``; fall
        # through to an empty corpus directory rather than failing the comparison.
        corpus = target if pathspec == "." else target / subpath
        corpus.mkdir(parents=True, exist_ok=True)
        yield corpus
