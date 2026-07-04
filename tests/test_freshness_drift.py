"""Drift detection — the git-native suspect link (freshness-and-drift-detection, phase 1).

Each test builds a throwaway git repository under ``tmp_path`` with controlled
commit times (mirroring tests/test_recency.py); the suite never touches this
repository's own git state. Drift is git-derived and degrades to silence outside
git (ADR-045). Read-surface recency (Initiative 1) is covered by tests/test_recency.py;
this file covers Initiative 2 — the ``suspect-artifact`` finding and its
"content change, not touch" tuning.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rac.services.doctor import CODE_SUSPECT_ARTIFACT, SEVERITY_WARNING, diagnose
from rac.services.drift import detect_drift
from rac.services.review import (
    PRIORITY_SUSPECT_ARTIFACT,
    REVIEW_SUSPECT_ARTIFACT,
    build_review,
)

# A valid requirement that references a decision by its filename stem, so the edge
# resolves (no frontmatter is required — cf. tests/fixtures/valid/feature.md).
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


def _amend_target(tmp_path: Path, target: Path, content: str) -> None:
    target.write_text(content, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "amend target", when=_T1)


# --- touch condition ---------------------------------------------------------


def test_detect_drift_fires_when_target_prose_changes_after_referrer(tmp_path):
    source, target = _seed(tmp_path)
    # The governing decision's prose changes; the requirement does not.
    _amend_target(tmp_path, target, _TARGET + "\nAn amendment to the consequences.\n")

    findings = detect_drift(str(tmp_path))
    assert len(findings) == 1
    d = findings[0]
    assert d.source_path.endswith("source.md")
    assert d.target_path.endswith("target-decision.md")
    assert d.relationship == "related_decisions"
    assert d.target_committed > d.source_committed


def test_detect_drift_clears_when_referrer_updated(tmp_path):
    source, target = _seed(tmp_path)
    _amend_target(tmp_path, target, _TARGET + "\nAn amendment.\n")
    # Now the referrer is updated after the target → no longer suspect.
    source.write_text(_SOURCE + "\nReviewed against the amended decision.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(
        tmp_path, "commit", "--quiet", "-m", "review requirement", when="2026-05-01T12:00:00+00:00"
    )

    assert detect_drift(str(tmp_path)) == []


# --- substance condition (the "content change, not touch" tuning) ------------


def test_detect_drift_suppresses_metadata_only_target_edit(tmp_path):
    # The target is touched after the referrer, but only its declared links change
    # (the real-world `## Applies To` case): prose is unchanged → not suspect.
    source, target = _seed(tmp_path)
    _amend_target(tmp_path, target, _TARGET + "\n## Related Roadmaps\n\n- some-roadmap\n")
    assert detect_drift(str(tmp_path)) == []


def test_detect_drift_flags_prose_edit_but_not_a_later_metadata_edit(tmp_path):
    # A prose amendment flags; a subsequent metadata-only edit does not un-flag or
    # re-noise it — the comparison is against the referrer's commit, not the last touch.
    source, target = _seed(tmp_path)
    _amend_target(
        tmp_path, target, _TARGET.replace("The governing decision.", "A revised decision.")
    )
    assert len(detect_drift(str(tmp_path))) == 1


# --- degrade posture ---------------------------------------------------------


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
    (reqs / "external.md").write_text(external + "\nmore prose.\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "touch", when=_T1)
    assert detect_drift(str(tmp_path)) == []


# --- doctor + review surfacing -----------------------------------------------


def test_doctor_emits_advisory_suspect_finding(tmp_path):
    source, target = _seed(tmp_path)
    _amend_target(tmp_path, target, _TARGET + "\nAn amendment.\n")

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
    _amend_target(tmp_path, target, _TARGET + "\nAn amendment.\n")

    report = build_review(str(tmp_path))
    suspect = [i for i in report.issues if i.code == REVIEW_SUSPECT_ARTIFACT]
    assert len(suspect) == 1
    assert suspect[0].priority == PRIORITY_SUSPECT_ARTIFACT
    assert suspect[0].severity == "info"
    assert suspect[0].path.endswith("source.md")
    # Priority-5 advisory never fails the review (only 1–2 gate).
    assert report.ok is True
