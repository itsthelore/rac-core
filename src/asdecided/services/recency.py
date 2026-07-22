"""Git-derived artifact recency (v0.13.2, ADR-045).

When was each artifact last written? RAC artifacts carry no timestamp, and
adding one would mean a schema change, hand-kept dates that drift, and the
work-status modelling ADR-017 rejects. Git already records exactly when every
file last changed, so recency is *derived* from `git log`, never stored.

This is the second narrow git touchpoint in the package, alongside
`revisions.py` (ADR-043): read-only, offline, no `.git` mutation. It answers
"unknown" (``None``) rather than raising when git is unavailable, the
directory is not a repository, or a file is untracked or uncommitted —
recency is advisory, never required.

Recency is a *capture-cadence* signal — when product knowledge was last
written — explicitly not a work-status or due-date signal, so consumers (the
cadence nudge, v0.13.3) stay inside ADR-017.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from asdecided.core.corpus import CorpusEntry, walk_corpus
from asdecided.core.markdown import parse
from asdecided.services.agent_rules import artifact_status
from asdecided.services.init import find_config_file

# Field separator for combined ``git log --format`` records. The unit-separator
# control byte never appears in a commit date, author name, or email, so a
# single ``--format`` call can carry several fields and be split unambiguously.
_FIELD_SEP = "\x1f"


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


def _last_committed(repo_root: str, path: str) -> datetime | None:
    """Commit time of the most recent change to ``path``, or ``None``.

    Uses ``git log -1 --format=%cI`` (ISO-8601, timezone-aware). An empty
    result means the file is untracked or uncommitted.
    """
    result = _run_git(
        ["log", "-1", "--format=%cI", "--", _pathspec(repo_root, path)], cwd=repo_root
    )
    if result is None or result.returncode != 0:
        return None
    return _parse_stamp(result.stdout)


def _first_committed(repo_root: str, path: str) -> datetime | None:
    """Commit time of the earliest change to ``path``, or ``None``.

    ``git log --reverse --format=%cI`` lists oldest first; the first line is the
    creation commit. Used only for the OKF export's ``created`` field, never on
    the cadence path.
    """
    result = _run_git(
        ["log", "--reverse", "--format=%cI", "--", _pathspec(repo_root, path)], cwd=repo_root
    )
    if result is None or result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.strip():
            return _parse_stamp(line)
    return None


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


def recency_from_corpus(
    directory: str,
    entries: list[CorpusEntry],
    recursive: bool = True,
    *,
    with_creation: bool = False,
) -> RecencyReport:
    """Recency for an already-walked corpus snapshot (the snapshot seam).

    Same result as :func:`artifact_recency`; the snapshot lets one walk feed
    several analyses (e.g. the ``decided review`` cadence nudge) instead of
    re-walking the tree. Callers pass the raw walk — unknown-type documents are
    excluded *here*, so the ``type != "unknown"`` filter lives in one place;
    recency is about product-knowledge artifacts. Derives each artifact's
    last-committed time from git (and its first-committed time when
    ``with_creation`` — one extra git call per file, used only by the OKF
    export). Outside a git repository, or for untracked files, the time is
    ``None`` ("unknown") — no exception crosses the boundary.
    """
    recognised = [e for e in entries if e.artifact_type != "unknown"]
    repo_root = _repository_root(directory)

    artifacts: list[ArtifactRecency] = []
    for entry in recognised:
        path = str(entry.path)
        last = _last_committed(repo_root, path) if repo_root is not None else None
        first = (
            _first_committed(repo_root, path) if with_creation and repo_root is not None else None
        )
        artifacts.append(
            ArtifactRecency(
                path=path,
                artifact_type=entry.artifact_type,
                last_committed=last,
                first_committed=first,
            )
        )
    return RecencyReport(directory=directory, recursive=recursive, artifacts=artifacts)


def artifact_recency(
    directory: str, recursive: bool = True, with_creation: bool = False
) -> RecencyReport:
    """Recency for every recognised artifact under ``directory``.

    A thin wrapper: walk the corpus once, then defer to
    :func:`recency_from_corpus`, which owns the ``type != "unknown"`` filter and
    the per-artifact git derivation. Outside a git repository, or for untracked
    files, the time is ``None`` ("unknown") — no exception crosses the boundary.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    return recency_from_corpus(directory, entries, recursive=recursive, with_creation=with_creation)


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

    ``earliest`` selects the creation commit (``git log --reverse``, first line);
    otherwise the most recent change (``git log -1``). One ``--format`` call
    carries both fields. Returns ``(None, None)`` when git does not know.
    """
    fmt = f"--format=%cI{_FIELD_SEP}%an <%ae>"
    args = ["log", "--reverse", fmt] if earliest else ["log", "-1", fmt]
    args += ["--", _pathspec(repo_root, path)]
    result = _run_git(args, cwd=repo_root)
    if result is None or result.returncode != 0:
        return None, None
    for line in result.stdout.splitlines():
        if line.strip():
            stamp, _, author = line.partition(_FIELD_SEP)
            return _parse_stamp(stamp), (author.strip() or None)
    return None, None


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


# --- Staleness indicator (freshness-and-drift phase 1, ADR-045) ---------------
#
# A documented, deterministic function of an artifact's last-committed age
# against a configurable threshold, reported as data beside its date — never a
# score or verdict (ADR-034). The last-committed date is the git fact (stable for
# a fixed git state); the derived ``age_days`` / ``stale`` are relative to a
# reference time (``now`` by default, injectable so tests stay deterministic).

# The documented default: an artifact untouched for this many days reads "stale".
DEFAULT_STALE_AFTER_DAYS = 180


@dataclass(frozen=True)
class Staleness:
    """One artifact's freshness: its last-committed date and derived indicator."""

    last_committed: datetime | None
    age_days: int | None
    stale: bool | None

    def to_dict(self) -> dict:
        return {
            "last_committed": self.last_committed.isoformat() if self.last_committed else None,
            "age_days": self.age_days,
            "stale": self.stale,
        }


def staleness(
    last_committed: datetime | None,
    *,
    threshold_days: int = DEFAULT_STALE_AFTER_DAYS,
    reference: datetime | None = None,
) -> Staleness:
    """The staleness of one last-committed date against ``threshold_days``.

    ``age_days`` is whole days between ``reference`` (default: now, UTC) and
    ``last_committed``; ``stale`` is ``age_days > threshold_days``. An unknown
    date (outside git, untracked) yields all-``None`` — never a fabricated date
    (ADR-045 degrade posture). Passing ``reference`` makes the result
    deterministic for tests.
    """
    if last_committed is None:
        return Staleness(None, None, None)
    if reference is None:
        reference = datetime.now(UTC)
    age_days = (reference - last_committed).days
    return Staleness(
        last_committed=last_committed, age_days=age_days, stale=age_days > threshold_days
    )


def load_freshness_threshold(directory: str) -> int:
    """The ``freshness.stale_after_days`` from the nearest ``.decided/config.yaml``.

    Discovery reuses the shared ``.decided/config.yaml`` walk (:func:`find_config_file`).
    Defaults to :data:`DEFAULT_STALE_AFTER_DAYS` when there is no config file, no
    ``freshness`` stanza, or the value is not a positive integer — the config is
    advisory, so a malformed value degrades to the default rather than raising.
    """
    config_path = find_config_file(directory)
    if config_path is None:
        return DEFAULT_STALE_AFTER_DAYS
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return DEFAULT_STALE_AFTER_DAYS
    section = data.get("freshness") if isinstance(data, dict) else None
    value = section.get("stale_after_days") if isinstance(section, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return DEFAULT_STALE_AFTER_DAYS
    return value


def last_committed_for_paths(directory: str, paths: Iterable[str]) -> dict[str, datetime | None]:
    """Git last-committed time for each of ``paths`` (the raw recency primitive).

    One git boundary (ADR-045): the most-recent commit time per path, or ``None``
    for an untracked path or when ``directory`` is not a repository — no exception
    crosses the boundary (REQ-005). Drift detection compares these dates directly;
    the staleness join layers a threshold on top of the same values.
    """
    repo_root = _repository_root(directory)
    if repo_root is None:
        return {path: None for path in paths}
    return {path: _last_committed(repo_root, path) for path in paths}


def recency_for_paths(
    directory: str,
    paths: Iterable[str],
    *,
    threshold_days: int = DEFAULT_STALE_AFTER_DAYS,
    reference: datetime | None = None,
) -> dict[str, Staleness]:
    """Git-derived staleness for each of ``paths`` (the read-surface join).

    One git boundary, reused (ADR-045): last-committed per path, then the
    staleness indicator. Outside a repository every path maps to an unknown
    :class:`Staleness` — no exception crosses the boundary (REQ-003).
    """
    if reference is None:
        reference = datetime.now(UTC)
    last_by_path = last_committed_for_paths(directory, paths)
    return {
        path: staleness(last, threshold_days=threshold_days, reference=reference)
        for path, last in last_by_path.items()
    }


def annotate_search_recency(
    matches: list,
    directory: str,
    *,
    threshold_days: int | None = None,
    reference: datetime | None = None,
) -> None:
    """Join git-derived staleness onto search matches (the read-surface enrichment).

    Sets each match's ``recency`` dict in place, computed *after* ranking so the
    matched set and order are untouched (REQ-005). The threshold defaults to the
    corpus's ``freshness`` config (else 180 days). Duck-typed on ``.path`` /
    ``.recency`` to avoid coupling recency to the resolver.
    """
    if not matches:
        return
    threshold = (
        threshold_days if threshold_days is not None else load_freshness_threshold(directory)
    )
    by_path = recency_for_paths(
        directory, [m.path for m in matches], threshold_days=threshold, reference=reference
    )
    for match in matches:
        match.recency = by_path[match.path].to_dict()
