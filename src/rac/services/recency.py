"""Git-derived artifact recency and provenance (v0.13.2 / v0.23.0, ADR-045).

RAC artifacts carry no authored-on timestamp: adding one would mean a schema
change, hand-kept dates that drift, and the work-status modelling ADR-017
rejects. Git already records when every file last changed and by whom, so both
*recency* (when knowledge was last written) and *provenance* (who wrote it, and
the lifecycle it moved through) are derived from ``git log`` here — never stored.

This is one of the package's two narrow git touchpoints, alongside
``revisions.py`` (ADR-043): read-only, offline, and never mutating ``.git``.
Every read degrades to "unknown" (``None`` / ``[]``) rather than raising when
git is absent, the directory is not a repository, or a file is untracked —
recency and provenance are advisory, never required.

Recency is deliberately a *capture-cadence* signal, not a work-status or
due-date one, so its consumers (the cadence nudge, v0.13.3) stay inside ADR-017.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rac.core.markdown import parse
from rac.services.agent_rules import artifact_status
from rac.services.index import build_repository_index

# Joins several ``git log --format`` fields into one line. The unit-separator
# control byte never appears in a commit date, author name, or email, so the
# record splits back apart unambiguously.
_FIELD_SEP = "\x1f"

# ``git log`` boundary selectors: the first commit that touched a file
# (``--reverse``, oldest first) versus the most recent (``-1``).
_EARLIEST = ["--reverse"]
_LATEST = ["-1"]


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str] | None:
    """Run git, capturing text output; ``None`` when git is not on PATH."""
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False, text=True)
    except FileNotFoundError:  # no git binary
        return None


def _repository_root(directory: str) -> str | None:
    """The work-tree root containing ``directory``, or ``None`` if not a repo."""
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=directory)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip()


def _pathspec(repo_root: str, path: str) -> str:
    """``path`` relative to ``repo_root`` for git, or absolute if outside it."""
    abspath = Path(path).resolve()
    try:
        return str(abspath.relative_to(Path(repo_root).resolve()))
    except ValueError:  # path lies outside the work tree; pass it through
        return str(abspath)


def _parse_stamp(stamp: str) -> datetime | None:
    stamp = stamp.strip()
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:  # unexpected git output; treat as unknown
        return None


def _boundary_log(repo_root: str, path: str, fmt: str, *, earliest: bool) -> list[str]:
    """Non-empty ``git log`` lines for one file's boundary commit.

    ``earliest`` selects the creation commit (``--reverse``, first line);
    otherwise the most recent change (``-1``). ``fmt`` is a ``--format`` spec so a
    single call can carry several ``_FIELD_SEP``-joined fields. An empty list
    means the file is untracked, or git could not answer.
    """
    selector = _EARLIEST if earliest else _LATEST
    result = _run_git(["log", *selector, fmt, "--", _pathspec(repo_root, path)], cwd=repo_root)
    if result is None or result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _boundary_committed(repo_root: str, path: str, *, earliest: bool) -> datetime | None:
    """Commit time of ``path``'s first or last change (``%cI``), or ``None``."""
    lines = _boundary_log(repo_root, path, "--format=%cI", earliest=earliest)
    return _parse_stamp(lines[0]) if lines else None


@dataclass
class ArtifactRecency:
    """One artifact's authored times, or ``None`` when git does not know.

    ``first_committed`` (creation) is populated only when recency is requested
    ``with_creation`` — the OKF export needs it; the cadence path does not.
    """

    path: str
    artifact_type: str
    last_committed: datetime | None
    first_committed: datetime | None = None


@dataclass
class RecencyReport:
    """Corpus recency: per-artifact last-authored times and aggregates."""

    directory: str
    recursive: bool
    artifacts: list[ArtifactRecency]

    @property
    def most_recent(self) -> datetime | None:
        """The newest last-authored time across all artifacts, or ``None``."""
        known = [a.last_committed for a in self.artifacts if a.last_committed is not None]
        return max(known) if known else None

    def most_recent_by_type(self) -> dict[str, datetime]:
        """Newest last-authored time per artifact type (unknowns omitted)."""
        result: dict[str, datetime] = {}
        for a in self.artifacts:
            if a.last_committed is None:
                continue
            current = result.get(a.artifact_type)
            if current is None or a.last_committed > current:
                result[a.artifact_type] = a.last_committed
        return result

    def to_dict(self) -> dict:
        most_recent = self.most_recent
        return {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            "most_recent": most_recent.isoformat() if most_recent else None,
            "by_type": {t: ts.isoformat() for t, ts in sorted(self.most_recent_by_type().items())},
            "artifacts": [
                {
                    "path": a.path,
                    "type": a.artifact_type,
                    "last_committed": (a.last_committed.isoformat() if a.last_committed else None),
                }
                for a in self.artifacts
            ],
        }


def artifact_recency(
    directory: str, recursive: bool = True, with_creation: bool = False
) -> RecencyReport:
    """Recency for every recognised artifact under ``directory``.

    Derives each artifact's last-committed time from git (and its first-committed
    time when ``with_creation`` — one extra git call per file, used only by the
    OKF export). Outside a git repository, or for untracked files, the time is
    ``None`` ("unknown") — no exception crosses the boundary. Unknown-type
    documents are excluded; recency is about product-knowledge artifacts.
    """
    index = build_repository_index(directory, recursive=recursive)
    entries = [e for e in index.artifacts if e.type != "unknown"]
    repo_root = _repository_root(directory)

    artifacts: list[ArtifactRecency] = []
    for entry in entries:
        if repo_root is None:
            last = first = None
        else:
            last = _boundary_committed(repo_root, entry.path, earliest=False)
            first = (
                _boundary_committed(repo_root, entry.path, earliest=True) if with_creation else None
            )
        artifacts.append(
            ArtifactRecency(
                path=entry.path,
                artifact_type=entry.type,
                last_committed=last,
                first_committed=first,
            )
        )
    return RecencyReport(directory=directory, recursive=recursive, artifacts=artifacts)


# --- Provenance (v0.23.0, WS5, ADR-045) --------------------------------------
#
# get_artifact surfaces who decided and when. Authorship and dates are *derived*
# from git, never stored in front matter (ADR-045), through this same narrow git
# touchpoint — WS5 adds no third git module and imports no git library (REQ-003).
# Every git read degrades to ``None`` / ``[]`` rather than raising when git is
# unavailable, the directory is not a repository, or the file is untracked
# (REQ-004); the current status still comes from parsed metadata regardless.


def _commit_record(
    repo_root: str, path: str, *, earliest: bool
) -> tuple[datetime | None, str | None]:
    """``(commit time, "Name <email>")`` for one boundary commit touching ``path``.

    ``earliest`` selects the creation commit; otherwise the most recent change.
    One ``--format`` call carries both fields. ``(None, None)`` when git does not
    know.
    """
    lines = _boundary_log(repo_root, path, f"--format=%cI{_FIELD_SEP}%an <%ae>", earliest=earliest)
    if not lines:
        return None, None
    stamp, _, author = lines[0].partition(_FIELD_SEP)
    return _parse_stamp(stamp), (author.strip() or None)


def _status_history(repo_root: str, path: str) -> list[StatusChange]:
    """The artifact's ``## Status`` value at each commit that changed it, oldest first.

    Walks the file's history once (``git log --reverse``), then reads the parsed
    status at each revision (``git show <rev>:<path>``), emitting one entry every
    time the value changes from the previous one (REQ-003). Absent / empty status
    is the baseline and yields no entry, so the history is the meaningful
    lifecycle (e.g. ``Proposed`` → ``Accepted``). O(commits touching the file);
    a missing or unreadable revision is skipped, never raised.
    """
    pathspec = _pathspec(repo_root, path)
    walk = _run_git(
        ["log", "--reverse", f"--format=%H{_FIELD_SEP}%cI{_FIELD_SEP}%an <%ae>", "--", pathspec],
        cwd=repo_root,
    )
    if walk is None or walk.returncode != 0:
        return []
    history: list[StatusChange] = []
    last_status = ""
    for line in walk.stdout.splitlines():
        if not line.strip():
            continue
        sha, stamp, author = line.split(_FIELD_SEP, 2)
        shown = _run_git(["show", f"{sha}:{pathspec}"], cwd=repo_root)
        if shown is None or shown.returncode != 0:
            continue
        status = artifact_status(parse(shown.stdout))
        if status and status != last_status:
            history.append(
                StatusChange(
                    status=status, committed=_parse_stamp(stamp), author=author.strip() or None
                )
            )
            last_status = status
    return history


@dataclass
class StatusChange:
    """One lifecycle transition reconstructed from git: when the parsed
    ``## Status`` value changed, and the author of the commit that changed it."""

    status: str
    committed: datetime | None
    author: str | None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "committed": self.committed.isoformat() if self.committed else None,
            "author": self.author,
        }


@dataclass
class ArtifactProvenance:
    """One artifact's git-derived provenance: creation and last-change
    author/time plus the reconstructed status history. Every field is ``None``
    / ``[]`` when git cannot answer (ADR-045); the *current* status is sourced
    from parsed metadata by the caller, not from git, so it is not carried here."""

    last_committed: datetime | None = None
    last_author: str | None = None
    first_committed: datetime | None = None
    first_author: str | None = None
    status_history: list[StatusChange] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "last_committed": self.last_committed.isoformat() if self.last_committed else None,
            "last_author": self.last_author,
            "first_committed": self.first_committed.isoformat() if self.first_committed else None,
            "first_author": self.first_author,
            "status_history": [change.to_dict() for change in self.status_history],
        }


def artifact_provenance(directory: str, path: str) -> ArtifactProvenance:
    """Git-derived provenance for one artifact at ``path`` within ``directory``.

    Reuses the recency git boundary (no new touchpoint, no git library; REQ-003)
    and never raises: outside a repository, in a shallow clone missing the
    commits, or for an untracked file, every field degrades to ``None`` / ``[]``
    (REQ-004). The current lifecycle status is read from parsed metadata by the
    caller and is deliberately not part of this git-only object.
    """
    repo_root = _repository_root(directory)
    if repo_root is None:
        return ArtifactProvenance()
    last_committed, last_author = _commit_record(repo_root, path, earliest=False)
    first_committed, first_author = _commit_record(repo_root, path, earliest=True)
    return ArtifactProvenance(
        last_committed=last_committed,
        last_author=last_author,
        first_committed=first_committed,
        first_author=first_author,
        status_history=_status_history(repo_root, path),
    )
