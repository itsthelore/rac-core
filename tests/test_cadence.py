"""Tests for the write-cadence nudge in `rac review` (v0.13.3).

The nudge is off by default, informational, and never changes the review's
exit status (ADR-017: capture cadence, not work tracking). It fires only when
git-derived recency is known and the newest artifact is older than the window.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rac.cli import main
from rac.services.review import (
    PRIORITY_STALE_CORPUS,
    REVIEW_STALE_CORPUS,
    build_review,
)

_REQUIREMENT = "# {title}\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"


def _git(repo: Path, *args: str, when: str | None = None) -> None:
    env = dict(os.environ)
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _repo_with_commit(tmp_path: Path, when: str) -> Path:
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when=when)
    return tmp_path


# --- service -----------------------------------------------------------------


def test_stale_corpus_emits_advisory_finding(tmp_path):
    repo = _repo_with_commit(tmp_path, "2026-01-01T00:00:00+00:00")
    now = datetime(2026, 1, 21, tzinfo=UTC)  # 20 days later
    report = build_review(str(repo), stale_after_days=14, now=now)
    stale = [i for i in report.issues if i.code == REVIEW_STALE_CORPUS]
    assert len(stale) == 1
    assert stale[0].severity == "info"
    assert stale[0].priority == PRIORITY_STALE_CORPUS
    # Advisory: it never fails the review.
    assert report.ok is True


def test_fresh_corpus_has_no_finding(tmp_path):
    repo = _repo_with_commit(tmp_path, "2026-01-20T00:00:00+00:00")
    now = datetime(2026, 1, 21, tzinfo=UTC)  # 1 day later
    report = build_review(str(repo), stale_after_days=14, now=now)
    assert not any(i.code == REVIEW_STALE_CORPUS for i in report.issues)


def test_boundary_exactly_at_window_is_not_stale(tmp_path):
    repo = _repo_with_commit(tmp_path, "2026-01-01T00:00:00+00:00")
    now = datetime(2026, 1, 15, tzinfo=UTC)  # exactly 14 days
    report = build_review(str(repo), stale_after_days=14, now=now)
    assert not any(i.code == REVIEW_STALE_CORPUS for i in report.issues)


def test_disabled_by_default(tmp_path):
    repo = _repo_with_commit(tmp_path, "2020-01-01T00:00:00+00:00")  # ancient
    report = build_review(str(repo))  # no stale_after_days
    assert not any(i.code == REVIEW_STALE_CORPUS for i in report.issues)


def test_non_git_directory_suppresses_finding(tmp_path):
    # A plain directory of artifacts: recency unknown, so no nudge, no error.
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    report = build_review(str(tmp_path), stale_after_days=1)
    assert not any(i.code == REVIEW_STALE_CORPUS for i in report.issues)


# --- CLI ----------------------------------------------------------------------


def test_cli_stale_after_exit_0_with_finding(tmp_path, capsys):
    repo = _repo_with_commit(tmp_path, "2020-01-01T00:00:00+00:00")  # long ago
    rc = main(["review", str(repo), "--stale-after", "14"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No product knowledge recorded" in out


def test_cli_stale_after_default_window(tmp_path, capsys):
    repo = _repo_with_commit(tmp_path, "2020-01-01T00:00:00+00:00")
    rc = main(["review", str(repo), "--stale-after"])  # no value -> default 14
    assert rc == 0
    assert "14 days" in capsys.readouterr().out


def test_cli_stale_after_json_includes_finding(tmp_path, capsys):
    repo = _repo_with_commit(tmp_path, "2020-01-01T00:00:00+00:00")
    main(["review", str(repo), "--stale-after", "14", "--json"])
    payload = json.loads(capsys.readouterr().out)
    codes = [i["code"] for i in payload["issues"]]
    assert REVIEW_STALE_CORPUS in codes
    assert payload["ok"] is True


def test_cli_without_flag_no_finding(tmp_path, capsys):
    repo = _repo_with_commit(tmp_path, "2020-01-01T00:00:00+00:00")
    main(["review", str(repo), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert all(i["code"] != REVIEW_STALE_CORPUS for i in payload["issues"])


def test_cli_negative_window_is_usage_error(tmp_path):
    repo = _repo_with_commit(tmp_path, "2020-01-01T00:00:00+00:00")
    with pytest.raises(SystemExit) as exc:
        main(["review", str(repo), "--stale-after", "-3"])
    assert exc.value.code == 2
