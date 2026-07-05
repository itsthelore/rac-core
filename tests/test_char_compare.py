"""Characterization tests for the compare cluster (diff / migrate / drift / recency).

These characterization tests were added before the rebuild-scale examiner freeze.
They pin the *current* behavior of thin, previously-unpinned seams around the
diff/compare/migrate/drift/recency services, so a from-scratch reimplementation
that quietly changes an error string, an exit code, a degrade path, or a key
derivation is caught. Nothing here asserts a *desired* behavior — every
expectation was read off the code as it stands on ``claude/rebuild-scale-10m``.

Coverage map (see charmap/compare.md):
- F1 (HIGH):   git binary absent degrades recency and drift to "unknown"/empty.
- F2 (MEDIUM): ``rac diff`` on a missing file is a usage error (exit 2).
- F3 (MEDIUM): ``rac diff`` on identical inputs prints ``No changes.``.
- F4 (MEDIUM): ``drift_problem`` exact human wording.
- F5 (MEDIUM): ``artifact_recency(with_creation=True)`` reports the first commit.
- F6 (MEDIUM): compare ``_issue_ref`` path-key derivation (all three branches).
- F7 (MEDIUM): compare change for an unclassified prose file.
- F8 (LOW):    diff human ANSI color path.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.core.corpus import CorpusCache
from rac.output import human as human_output
from rac.services.compare import CHANGE_ADDED, _issue_ref, compare_states, load_state
from rac.services.diff import diff as diff_products
from rac.services.drift import DriftRecord, drift_problem, suspect_drift
from rac.services.recency import artifact_recency
from rac.services.relationships import ISSUE_DUPLICATE_IDENTIFIER, RelationshipIssue

# --- fixtures / helpers ------------------------------------------------------

# Untyped requirement (classified structurally), mirroring tests/test_recency.py.
_REQUIREMENT = "# {title}\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"

# Typed decision + requirement with a resolvable in-corpus edge, mirroring
# tests/test_drift.py, so drift has a real edge to (fail to) find.
_RID = "RAC-AAAAAAAAAAA1"
_DID = "RAC-BBBBBBBBBBB2"
_REQ = (
    "---\nschema_version: 1\nid: {id}\ntype: requirement\n---\n# {t}\n\n"
    "## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
)
_DEC = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n# {t}\n\n## Status\n\n"
    "Accepted\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n\n"
    "## Related Requirements\n\n- {ref}\n"
)


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


# --- F1 — git binary absent degrades to "unknown"/empty (HIGH) ---------------


def test_recency_degrades_when_git_binary_absent(tmp_path, monkeypatch):
    # An empty PATH means the ``git`` executable cannot be found, so every
    # subprocess launch raises FileNotFoundError. ``_run_git`` swallows it and
    # returns None, so recency degrades to "unknown" rather than crashing — the
    # distinct git-missing branch, not the not-a-repository branch (ADR-045).
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    monkeypatch.setenv("PATH", "")
    report = artifact_recency(str(tmp_path))
    assert len(report.artifacts) == 1
    assert report.artifacts[0].last_committed is None
    assert report.most_recent is None


def test_drift_degrades_when_git_binary_absent(tmp_path, monkeypatch):
    # The same repo that yields a suspect edge with git present must yield no
    # findings — not an error — once the git binary cannot be found.
    _init(tmp_path)
    corpus = tmp_path / "rac"
    corpus.mkdir(parents=True)
    (corpus / "dec.md").write_text(_DEC.format(id=_DID, t="Dec", ref=_RID), encoding="utf-8")
    (corpus / "req.md").write_text(_REQ.format(id=_RID, t="Req"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T00:00:00+00:00")
    (corpus / "req.md").write_text(_REQ.format(id=_RID, t="Req v2"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "touch", when="2026-06-01T00:00:00+00:00")
    entries = CorpusCache().collect(str(tmp_path))
    monkeypatch.setenv("PATH", "")
    assert suspect_drift(str(tmp_path), entries) == []


# --- F2 — `rac diff` on a missing file is a usage error (MEDIUM) -------------


def test_diff_missing_file_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["diff", "does-not-exist.md", fixture_path("diff", "new.md")])
    assert exc.value.code == 2
    assert "rac: file not found: does-not-exist.md" in capsys.readouterr().err


# --- F3 — `rac diff` on identical inputs prints "No changes." (MEDIUM) -------


def test_diff_identical_files_reports_no_changes(capsys):
    old = fixture_path("diff", "old.md")
    rc = main(["diff", old, old])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "No changes."


# --- F4 — drift_problem exact human wording (MEDIUM) -------------------------


def test_drift_problem_exact_wording():
    rec = DriftRecord(
        source_path="rac/dec.md",
        target_path="rac/req.md",
        target_ref="RAC-X",
        source_committed=datetime(2026, 1, 1, tzinfo=UTC),
        target_committed=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert drift_problem(rec) == (
        "references RAC-X which changed more recently "
        "(target last committed 2026-06-01T00:00:00+00:00, "
        "this artifact 2026-01-01T00:00:00+00:00) — review recommended"
    )


# --- F5 — recency(with_creation=True) reports the first commit (MEDIUM) ------


def test_recency_with_creation_reports_first_commit(tmp_path):
    _init(tmp_path)
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "c1", when="2026-01-01T00:00:00+00:00")
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A2"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "c2", when="2026-06-01T00:00:00+00:00")

    art = artifact_recency(str(tmp_path), with_creation=True).artifacts[0]
    # first_committed is the earliest (creation) commit via `git log --reverse`;
    # last_committed is the most recent — the two must not collapse together.
    assert art.first_committed == datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    assert art.last_committed == datetime.fromisoformat("2026-06-01T00:00:00+00:00")


# --- F6 — compare `_issue_ref` path-key derivation (MEDIUM) ------------------
#
# The set-diffing of new/resolved relationship issues keys on `_issue_ref.path`,
# so its three derivations are an observable contract. The multi-path (b) and
# repository-level (c) branches are not reachable through `load_state` today
# (`validation_from_corpus` surfaces no duplicate-identifier / repo-level finding
# in that path), so they are pinned by constructing the ref directly.


def test_issue_ref_single_source_path_is_corpus_relative():
    ref = _issue_ref(
        RelationshipIssue(
            code="relationship-target-not-found",
            source_path="/repo/base/decisions/adr-001.md",
            relationship="related_requirements",
            target="legacy",
        ),
        "/repo/base",
    )
    assert ref.path == "decisions/adr-001.md"
    assert ref.code == "relationship-target-not-found"
    assert ref.relationship == "related_requirements"
    assert ref.target == "legacy"


def test_issue_ref_multi_path_is_sorted_comma_joined():
    # Duplicate-identifier findings span files and carry no single source; the key
    # is the corpus-relative paths, sorted and ", "-joined (order-independent).
    ref = _issue_ref(
        RelationshipIssue(
            code=ISSUE_DUPLICATE_IDENTIFIER,
            source_path=None,
            paths=["/repo/base/requirements/z.md", "/repo/base/requirements/a.md"],
            identifier="RAC-DUPDUPDUP01",
        ),
        "/repo/base",
    )
    assert ref.path == "requirements/a.md, requirements/z.md"
    assert ref.identifier == "RAC-DUPDUPDUP01"


def test_issue_ref_repository_level_has_empty_path():
    ref = _issue_ref(
        RelationshipIssue(code="some-repo-level-finding", source_path=None, paths=None),
        "/repo/base",
    )
    assert ref.path == ""


# --- F7 — compare change for an unclassified prose file (MEDIUM) -------------


def test_compare_added_unclassified_file(tmp_path):
    # A prose file with no frontmatter classifies as an "unknown" artifact rather
    # than being dropped: every walked Markdown file becomes an Artifact, so the
    # change carries type == "unknown" with a *filename-derived* id (the stem),
    # not None. Title stays None. The `_change` artifact-None fallback is not
    # reachable through `load_state` today; this pins the observed contract.
    base = tmp_path / "base"
    base.mkdir()
    head = tmp_path / "head"
    head.mkdir()
    (head / "notes.md").write_text("Just some prose with no frontmatter.\n", encoding="utf-8")

    comparison = compare_states(load_state(str(base)), load_state(str(head)))
    assert len(comparison.changes) == 1
    change = comparison.changes[0]
    assert change.change == CHANGE_ADDED
    assert change.type == "unknown"
    assert change.id == "notes"
    assert change.title is None
    assert change.path == "notes.md"


# --- F8 — diff human ANSI color path (LOW) -----------------------------------


def test_diff_human_emits_ansi_color_when_enabled(monkeypatch):
    # The golden test forces color off; with a TTY (`_USE_COLOR=True`) added items
    # are green (32), removed red (31), and titles bold (1).
    from rac.core.markdown import parse_file

    old = parse_file(fixture_path("diff", "old.md"))
    new = parse_file(fixture_path("diff", "new.md"))
    monkeypatch.setattr(human_output, "_USE_COLOR", True)
    rendered = human_output.render_diff_human(diff_products(old, new), "old.md", "new.md")
    assert "\033[32m" in rendered
    assert "\033[31m" in rendered
    assert "\033[1m" in rendered
