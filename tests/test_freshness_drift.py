"""Freshness signals and drift detection — phase 1 (freshness-and-drift-detection).

Each test builds a throwaway git repository under ``tmp_path`` with controlled
commit times (mirroring tests/test_recency.py); the suite never touches this
repository's own git state. Both signals are git-derived and degrade to silence
outside git (ADR-045): recency is simply absent from a search match, and drift
produces no findings. The byte-pinned golden suite asserts that absence globally;
these tests assert the real values under controlled git.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rac.output.human import _recency_suffix
from rac.services.doctor import CODE_SUSPECT_ARTIFACT, SEVERITY_WARNING, diagnose
from rac.services.drift import detect_drift
from rac.services.index import build_repository_index
from rac.services.recency import DEFAULT_STALE_AFTER_DAYS, recency_fields
from rac.services.resolve import attach_recency, find_artifacts, search_index
from rac.services.review import (
    PRIORITY_SUSPECT_ARTIFACT,
    REVIEW_SUSPECT_ARTIFACT,
    build_review,
)

# A valid requirement (like tests/fixtures/valid/feature.md — no frontmatter is
# required) that references a decision by its filename stem, so the edge resolves.
_SOURCE = (
    "# Source Requirement\n\n"
    "## Problem\n\nUsers need a governed behaviour.\n\n"
    "## Requirements\n\n[REQ-001] The system SHALL follow the target decision.\n\n"
    "## Related Decisions\n\n- target-decision\n"
)
# A valid decision; its filename stem ``target-decision`` is the identifier the
# reference above resolves to.
_TARGET = (
    "# Target Decision\n\n"
    "## Context\n\nThe context that governs the requirement.\n\n"
    "## Decision\n\nThe governing decision.\n\n"
    "## Consequences\n\nThe requirement must track this.\n"
)

_T0 = "2026-01-01T12:00:00+00:00"
_T1 = "2026-03-01T12:00:00+00:00"  # later than T0
_T2 = "2026-05-01T12:00:00+00:00"  # later than T1


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


def _init(repo: Path) -> None:
    _git(repo, "init", "--quiet", "--initial-branch=main")


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    """A repo with a requirement referencing a decision, both committed at T0."""
    _init(tmp_path)
    reqs = tmp_path / "rac" / "requirements"
    decs = tmp_path / "rac" / "decisions"
    reqs.mkdir(parents=True)
    decs.mkdir(parents=True)
    source = reqs / "source.md"
    target = decs / "target-decision.md"
    source.write_text(_SOURCE, encoding="utf-8")
    target.write_text(_TARGET, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "seed", when=_T0)
    return source, target


# --- recency_fields (Initiative 1 unit) --------------------------------------


def test_recency_fields_absent_when_unknown():
    now = datetime(2026, 7, 4, tzinfo=UTC)
    assert recency_fields(None, now) is None


def test_recency_fields_reports_age_and_freshness():
    now = datetime(2026, 7, 4, tzinfo=UTC)
    fresh = recency_fields(datetime(2026, 6, 1, tzinfo=UTC), now)
    assert fresh == {
        "last_committed": "2026-06-01T00:00:00+00:00",
        "age_days": 33,
        "stale": False,
    }


def test_recency_fields_stale_past_threshold():
    now = datetime(2026, 7, 4, tzinfo=UTC)
    committed = now.replace(year=2025)  # ~365 days old
    assert recency_fields(committed, now)["stale"] is True
    # The boundary is strictly greater than the threshold: exactly the threshold
    # age is not yet stale, one day past it is.
    at_threshold = now - timedelta(days=DEFAULT_STALE_AFTER_DAYS)
    assert recency_fields(at_threshold, now)["stale"] is False
    assert recency_fields(at_threshold - timedelta(days=1), now)["stale"] is True


# --- recency on read surfaces (Initiative 1) ---------------------------------


def test_attach_recency_surfaces_staleness_on_find(tmp_path):
    _seed(tmp_path)
    now = datetime(2026, 7, 20, 12, tzinfo=UTC)  # exactly 200 days after T0 → stale
    result = find_artifacts(str(tmp_path), "target")
    attach_recency(result, str(tmp_path), now=now)
    match = next(m for m in result.matches if m.path.endswith("target-decision.md"))
    assert match.recency is not None
    assert match.recency["last_committed"] == _T0
    assert match.recency["age_days"] == 200
    assert match.recency["stale"] is True
    # The additive field rides the JSON contract.
    assert any("recency" in m.to_dict() for m in result.matches)


def test_attach_recency_absent_outside_git(tmp_path):
    # A plain directory of artifacts — no `git init`.
    reqs = tmp_path / "rac" / "requirements"
    reqs.mkdir(parents=True)
    (reqs / "source.md").write_text(_SOURCE, encoding="utf-8")
    result = find_artifacts(str(tmp_path), "source")
    attach_recency(result, str(tmp_path), now=datetime(2026, 7, 4, tzinfo=UTC))
    assert result.matches  # the query still matches
    for m in result.matches:
        assert m.recency is None
        assert "recency" not in m.to_dict()  # absent, not null


def test_attach_recency_matches_mcp_search_shape(tmp_path):
    # Mirror the MCP _search_artifacts boundary: search_index then attach_recency.
    _seed(tmp_path)
    entries = build_repository_index(str(tmp_path), recursive=True).artifacts
    result = search_index(entries, "target")
    attach_recency(result, str(tmp_path), now=datetime(2026, 7, 20, tzinfo=UTC))
    payload = result.to_dict()
    surfaced = [m for m in payload["matches"] if "recency" in m]
    assert surfaced and surfaced[0]["recency"]["stale"] is True


def test_recency_suffix_rendering():
    assert _recency_suffix(None) == ""
    assert _recency_suffix({"age_days": 10, "stale": False}) == "  (updated 10d ago)"
    assert "review recommended" in _recency_suffix({"age_days": 400, "stale": True})


# --- drift detection (Initiative 2) ------------------------------------------


def test_detect_drift_fires_when_target_newer_than_referrer(tmp_path):
    source, target = _seed(tmp_path)
    # The governing decision changes; the requirement does not.
    target.write_text(_TARGET + "\nAn amendment.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "amend decision", when=_T1)

    findings = detect_drift(str(tmp_path))
    assert len(findings) == 1
    d = findings[0]
    assert d.source_path.endswith("source.md")
    assert d.target_path.endswith("target-decision.md")
    assert d.relationship == "related_decisions"
    assert d.target_committed > d.source_committed


def test_detect_drift_clears_when_referrer_updated(tmp_path):
    source, target = _seed(tmp_path)
    target.write_text(_TARGET + "\nAn amendment.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "amend decision", when=_T1)
    # Now the referrer is updated after the target → no longer suspect.
    source.write_text(_SOURCE + "\nReviewed against the amended decision.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "review requirement", when=_T2)

    assert detect_drift(str(tmp_path)) == []


def test_detect_drift_silent_outside_git(tmp_path):
    reqs = tmp_path / "rac" / "requirements"
    decs = tmp_path / "rac" / "decisions"
    reqs.mkdir(parents=True)
    decs.mkdir(parents=True)
    (reqs / "source.md").write_text(_SOURCE, encoding="utf-8")
    (decs / "target-decision.md").write_text(_TARGET, encoding="utf-8")
    assert detect_drift(str(tmp_path)) == []  # no git → no findings, no error


def test_detect_drift_excludes_external_references(tmp_path):
    # An artifact whose only reference is an external ticket (ADR-087) never drifts.
    _init(tmp_path)
    reqs = tmp_path / "rac" / "requirements"
    reqs.mkdir(parents=True)
    external = (
        "# External Only\n\n## Problem\n\np.\n\n## Requirements\n\n[REQ-001] x.\n\n"
        "## Related Tickets\n\n- itsthelore/rac-core#1\n"
    )
    (reqs / "external.md").write_text(external, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "seed", when=_T0)
    # Even after any later commit, an external ref resolves to nothing → no drift.
    (reqs / "external.md").write_text(external + "\nmore.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "touch", when=_T1)
    assert detect_drift(str(tmp_path)) == []


# --- doctor + review surfacing (Initiative 2) --------------------------------


def test_doctor_emits_advisory_suspect_finding(tmp_path):
    source, target = _seed(tmp_path)
    target.write_text(_TARGET + "\nAn amendment.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "amend decision", when=_T1)

    report = diagnose(str(tmp_path))
    suspect = [f for f in report.findings if f.code == CODE_SUSPECT_ARTIFACT]
    assert len(suspect) == 1
    assert suspect[0].severity == SEVERITY_WARNING
    assert suspect[0].path.endswith("source.md")
    assert "target-decision.md" in suspect[0].problem
    # Advisory only: a warning does not fail the run (REQ-002/007).
    assert report.error_count == 0
    assert report.ok is True


def test_review_surfaces_suspect_advisory(tmp_path):
    source, target = _seed(tmp_path)
    target.write_text(_TARGET + "\nAn amendment.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "amend decision", when=_T1)

    report = build_review(str(tmp_path))
    suspect = [i for i in report.issues if i.code == REVIEW_SUSPECT_ARTIFACT]
    assert len(suspect) == 1
    assert suspect[0].priority == PRIORITY_SUSPECT_ARTIFACT
    assert suspect[0].severity == "info"
    assert suspect[0].path.endswith("source.md")
    # Priority-5 advisory never fails the review (only 1–2 gate).
    assert report.ok is True
