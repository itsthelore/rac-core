"""Suspect-artifact drift detection (freshness-and-drift phase 1).

Each test builds a throwaway git repository under ``tmp_path`` with controlled
commit times, so the suspect signal is a deterministic function of git state —
byte-identical across runs (REQ-006) and independent of the wall clock. Drift is
advisory: it names facts and recommends review, never a verdict, and degrades to
nothing outside git (REQ-004, REQ-005).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rac.core.corpus import CorpusCache
from rac.services.doctor import diagnose, render_doctor_json
from rac.services.drift import CODE_SUSPECT_ARTIFACT, suspect_drift
from rac.services.review import PRIORITY_SUSPECT_DRIFT, build_review
from rac.services.review import REVIEW_SUSPECT_ARTIFACT as REVIEW_CODE

# A decision that references a requirement (a resolvable in-corpus edge) and a
# decision whose only reference is an external ticket (never resolves, ADR-087).
_REQ = (
    "---\nschema_version: 1\nid: {id}\ntype: requirement\n---\n# {t}\n\n"
    "## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
)
_DEC = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n# {t}\n\n## Status\n\n"
    "Accepted\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n\n"
    "## Related Requirements\n\n- {ref}\n"
)
_DEC_TICKET = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n# {t}\n\n## Status\n\n"
    "Accepted\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n\n"
    "## Related Tickets\n\n- {ref}\n"
)

_RID = "RAC-AAAAAAAAAAA1"
_DID = "RAC-BBBBBBBBBBB2"


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


def _corpus(tmp_path: Path) -> Path:
    """A repo where a decision references a requirement; both committed together."""
    _init(tmp_path)
    corpus = tmp_path / "rac"
    corpus.mkdir(parents=True)
    (corpus / "dec.md").write_text(_DEC.format(id=_DID, t="Dec", ref=_RID), encoding="utf-8")
    (corpus / "req.md").write_text(_REQ.format(id=_RID, t="Req"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T00:00:00+00:00")
    return corpus


def _touch(tmp_path: Path, rel: str, body: str, when: str) -> None:
    (tmp_path / "rac" / rel).write_text(body, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", f"touch {rel}", when=when)


# --- primitive (REQ-001, REQ-003, REQ-005) -----------------------------------


def _entries(tmp_path: Path) -> list:
    return CorpusCache().collect(str(tmp_path))


def test_target_newer_than_referrer_is_suspect(tmp_path):
    _corpus(tmp_path)
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    records = suspect_drift(str(tmp_path), _entries(tmp_path))
    assert len(records) == 1
    record = records[0]
    assert Path(record.source_path).name == "dec.md"
    assert Path(record.target_path).name == "req.md"
    assert record.target_ref == _RID
    assert record.target_committed > record.source_committed


def test_referrer_newer_than_target_is_not_suspect(tmp_path):
    _corpus(tmp_path)
    _touch(
        tmp_path, "dec.md", _DEC.format(id=_DID, t="Dec v2", ref=_RID), "2026-06-01T00:00:00+00:00"
    )
    assert suspect_drift(str(tmp_path), _entries(tmp_path)) == []


def test_touching_referrer_clears_the_finding(tmp_path):
    _corpus(tmp_path)
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    assert len(suspect_drift(str(tmp_path), _entries(tmp_path))) == 1
    # Committing a newer change to the referrer clears it (Acceptance criterion).
    _touch(
        tmp_path, "dec.md", _DEC.format(id=_DID, t="Dec v2", ref=_RID), "2026-07-01T00:00:00+00:00"
    )
    assert suspect_drift(str(tmp_path), _entries(tmp_path)) == []


def test_equal_commit_time_is_not_suspect(tmp_path):
    # Committed together (identical time): the referrer is as new as its target.
    _corpus(tmp_path)
    assert suspect_drift(str(tmp_path), _entries(tmp_path)) == []


def test_external_only_reference_never_drifts(tmp_path):
    # A decision whose only reference is an external ticket (ADR-087). It resolves
    # to no in-corpus artifact, so it cannot be a suspect edge (REQ-003), even
    # after any amount of unrelated churn.
    _init(tmp_path)
    corpus = tmp_path / "rac"
    corpus.mkdir(parents=True)
    (corpus / "dec.md").write_text(
        _DEC_TICKET.format(id=_DID, t="Dec", ref="PROJ-42"), encoding="utf-8"
    )
    (corpus / "req.md").write_text(_REQ.format(id=_RID, t="Req"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T00:00:00+00:00")
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    assert suspect_drift(str(tmp_path), _entries(tmp_path)) == []


def test_duplicate_edge_yields_one_record(tmp_path):
    # A decision that references the same requirement in two sections yields a
    # single deduplicated record.
    _init(tmp_path)
    corpus = tmp_path / "rac"
    corpus.mkdir(parents=True)
    dec = (
        f"---\nschema_version: 1\nid: {_DID}\ntype: decision\n---\n# Dec\n\n## Status\n\n"
        "Accepted\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n\n"
        f"## Related Requirements\n\n- {_RID}\n\n## Supersedes\n\n- {_RID}\n"
    )
    (corpus / "dec.md").write_text(dec, encoding="utf-8")
    (corpus / "req.md").write_text(_REQ.format(id=_RID, t="Req"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T00:00:00+00:00")
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    assert len(suspect_drift(str(tmp_path), _entries(tmp_path))) == 1


def test_outside_git_yields_no_findings(tmp_path):
    # No `git init`: a plain directory. Degrade to nothing, never an error (REQ-005).
    corpus = tmp_path / "rac"
    corpus.mkdir(parents=True)
    (corpus / "dec.md").write_text(_DEC.format(id=_DID, t="Dec", ref=_RID), encoding="utf-8")
    (corpus / "req.md").write_text(_REQ.format(id=_RID, t="Req"), encoding="utf-8")
    assert suspect_drift(str(tmp_path), _entries(tmp_path)) == []


def test_records_are_byte_stable_across_runs(tmp_path):
    _corpus(tmp_path)
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    a = render_doctor_json(diagnose(str(tmp_path)))
    b = render_doctor_json(diagnose(str(tmp_path)))
    assert a == b


# --- rac doctor surface (REQ-001, REQ-002, REQ-004) --------------------------


def test_doctor_emits_advisory_warning_and_exits_zero(tmp_path):
    _corpus(tmp_path)
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    report = diagnose(str(tmp_path))
    suspects = [f for f in report.findings if f.code == CODE_SUSPECT_ARTIFACT]
    assert len(suspects) == 1
    finding = suspects[0]
    assert finding.severity == "warning"
    assert Path(finding.path).name == "dec.md"
    # Names the newer target and both dates as facts, recommends review (REQ-004).
    assert _RID in finding.problem
    assert "2026-06-01T00:00:00+00:00" in finding.problem
    assert "2026-01-01T00:00:00+00:00" in finding.problem
    assert "review recommended" in finding.problem
    assert "Advisory only" in finding.fix
    # Warning-only run exits zero (REQ-002).
    assert report.ok
    assert report.error_count == 0


def test_doctor_no_drift_when_nothing_changed(tmp_path):
    _corpus(tmp_path)
    report = diagnose(str(tmp_path))
    assert [f for f in report.findings if f.code == CODE_SUSPECT_ARTIFACT] == []


# --- rac review advisory channel (REQ-002) -----------------------------------


def test_review_surfaces_drift_as_advisory(tmp_path):
    _corpus(tmp_path)
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    report = build_review(str(tmp_path))
    drift = [i for i in report.issues if i.code == REVIEW_CODE]
    assert len(drift) == 1
    issue = drift[0]
    assert issue.priority == PRIORITY_SUSPECT_DRIFT
    assert issue.severity == "warning"
    assert _RID in issue.message
    # Advisory only: it never fails the review (no priority 1-2 finding).
    assert report.ok


def test_review_drift_and_doctor_report_the_same_code(tmp_path):
    # One source of truth: both surfaces use the drift primitive's stable code.
    assert REVIEW_CODE == CODE_SUSPECT_ARTIFACT


def test_review_human_labels_the_drift_group(tmp_path):
    from rac.output.human import render_review_human

    _corpus(tmp_path)
    _touch(tmp_path, "req.md", _REQ.format(id=_RID, t="Req v2"), "2026-06-01T00:00:00+00:00")
    rendered = render_review_human(build_review(str(tmp_path)))
    assert "Possible drift" in rendered
