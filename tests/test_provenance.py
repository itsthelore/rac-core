"""Provenance battery (v0.23.0, WS5).

`get_artifact` surfaces who decided and when, derived from git rather than from
stored front-matter dates (ADR-045). These tests pin the git-derived fields
against a throwaway repository with known commits, prove they degrade to
``null``/``[]`` when git cannot answer (REQ-004), and prove the addition is
purely additive over the WS11 `provenance` object (REQ-001, ADR-007).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from rac.mcp.server import build_server
from rac.services.recency import artifact_provenance

DECISION = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n# {title}\n\n"
    "## Status\n\n{status}\n\n## Context\n\nWhy.\n\n## Decision\n\nDo it.\n\n"
    "## Consequences\n\nFine.\n"
)

# Two distinct authors and fixed commit times, so every git-derived field is
# deterministic and assertable.
AUTHOR_A = ("Ada Lovelace", "ada@example.com")
AUTHOR_B = ("Grace Hopper", "grace@example.com")
DATE_A = "2026-01-02T03:04:05+00:00"
DATE_B = "2026-03-04T05:06:07+00:00"


def _write_decision(path: Path, aid: str, *, status: str) -> None:
    path.write_text(DECISION.format(id=aid, title=path.stem, status=status), encoding="utf-8")


def _git(
    args: list[str], cwd: Path, *, author: tuple[str, str] | None = None, date: str | None = None
) -> None:
    env = dict(os.environ)
    if author is not None:
        env["GIT_AUTHOR_NAME"], env["GIT_AUTHOR_EMAIL"] = author
        env["GIT_COMMITTER_NAME"], env["GIT_COMMITTER_EMAIL"] = author
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env)


def _commit(repo: Path, message: str, *, author: tuple[str, str], date: str) -> None:
    _git(["add", "-A"], repo)
    _git(["commit", "-m", message], repo, author=author, date=date)


def _get_artifact(root: Path, artifact_id: str) -> dict:
    server = build_server(str(root))
    contents, _ = asyncio.run(server.call_tool("get_artifact", {"id": artifact_id}))
    return json.loads(contents[0].text)


def _expected_author(author: tuple[str, str]) -> str:
    return f"{author[0]} <{author[1]}>"


# --- git-derived fields against known commits (REQ-001, REQ-003) -------------


def test_provenance_fields_match_known_commits(tmp_path):
    _git(["init"], tmp_path)
    decision = tmp_path / "event-bus.md"

    _write_decision(decision, "RAC-PR0VENANCE01", status="Proposed")
    _commit(tmp_path, "add decision (proposed)", author=AUTHOR_A, date=DATE_A)

    _write_decision(decision, "RAC-PR0VENANCE01", status="Accepted")
    _commit(tmp_path, "accept decision", author=AUTHOR_B, date=DATE_B)

    prov = artifact_provenance(str(tmp_path), str(decision))

    # Creation commit is author A at DATE_A; the last change is author B at DATE_B.
    assert prov.first_author == _expected_author(AUTHOR_A)
    assert prov.first_committed == datetime.fromisoformat(DATE_A)
    assert prov.last_author == _expected_author(AUTHOR_B)
    assert prov.last_committed == datetime.fromisoformat(DATE_B)

    # status_history records one entry per change, oldest first.
    assert [c.status for c in prov.status_history] == ["Proposed", "Accepted"]
    assert [c.author for c in prov.status_history] == [
        _expected_author(AUTHOR_A),
        _expected_author(AUTHOR_B),
    ]
    assert [c.committed for c in prov.status_history] == [
        datetime.fromisoformat(DATE_A),
        datetime.fromisoformat(DATE_B),
    ]


def test_status_history_emits_only_on_change(tmp_path):
    # A commit that does not change the status value adds no history entry.
    _git(["init"], tmp_path)
    decision = tmp_path / "stable.md"

    _write_decision(decision, "RAC-PR0VENANCE02", status="Accepted")
    _commit(tmp_path, "add decision", author=AUTHOR_A, date=DATE_A)

    # Body edit, status unchanged.
    decision.write_text(
        DECISION.format(id="RAC-PR0VENANCE02", title="stable", status="Accepted").replace(
            "Do it.", "Do it carefully."
        ),
        encoding="utf-8",
    )
    _commit(tmp_path, "expand decision body", author=AUTHOR_B, date=DATE_B)

    prov = artifact_provenance(str(tmp_path), str(decision))
    assert [c.status for c in prov.status_history] == ["Accepted"]
    # The body edit still moves last-change authorship.
    assert prov.first_author == _expected_author(AUTHOR_A)
    assert prov.last_author == _expected_author(AUTHOR_B)


# --- graceful degradation when git cannot answer (REQ-004) -------------------


def test_provenance_degrades_outside_repository(tmp_path):
    # tmp_path is not a git work tree: every git-derived field is null/empty.
    decision = tmp_path / "orphan.md"
    _write_decision(decision, "RAC-PR0VENANCE03", status="Accepted")

    prov = artifact_provenance(str(tmp_path), str(decision))
    assert prov.last_committed is None
    assert prov.last_author is None
    assert prov.first_committed is None
    assert prov.first_author is None
    assert prov.status_history == []


def test_provenance_degrades_for_untracked_file(tmp_path):
    # git is available and the directory is a repo, but the file was never
    # committed (the shallow-clone / uncommitted case): fields still degrade.
    _git(["init"], tmp_path)
    decision = tmp_path / "uncommitted.md"
    _write_decision(decision, "RAC-PR0VENANCE04", status="Accepted")

    prov = artifact_provenance(str(tmp_path), str(decision))
    assert prov.last_committed is None
    assert prov.first_committed is None
    assert prov.status_history == []


# --- get_artifact surface: additive, status always populates (REQ-001/004) ---


def test_get_artifact_status_populates_without_git(tmp_path):
    # Outside a repo the current status still comes from parsed metadata, while
    # the git-derived fields are null/empty (REQ-004).
    decision = tmp_path / "accepted.md"
    _write_decision(decision, "RAC-PR0VENANCE05", status="Accepted")

    prov = _get_artifact(tmp_path, "RAC-PR0VENANCE05")["provenance"]
    assert prov["status"] == "Accepted"
    assert prov["last_committed"] is None
    assert prov["last_author"] is None
    assert prov["first_committed"] is None
    assert prov["first_author"] is None
    assert prov["status_history"] == []


def test_get_artifact_provenance_is_purely_additive(tmp_path):
    # The top-level keys are unchanged from before WS5; provenance keeps the
    # WS11 `status` key and gains exactly the five git-derived fields (ADR-007).
    decision = tmp_path / "accepted.md"
    _write_decision(decision, "RAC-PR0VENANCE06", status="Accepted")

    payload = _get_artifact(tmp_path, "RAC-PR0VENANCE06")
    assert list(payload) == [
        "schema_version",
        "id",
        "type",
        "title",
        "path",
        "content",
        "provenance",
    ]
    assert set(payload["provenance"]) == {
        "status",
        "last_committed",
        "last_author",
        "first_committed",
        "first_author",
        "status_history",
    }


def test_get_artifact_with_git_history_is_byte_identical_across_calls(tmp_path):
    # Determinism (ADR-032): a committed artifact's get_artifact output, git
    # provenance included, is byte-identical on repeated reads of an unchanged
    # repository.
    _git(["init"], tmp_path)
    decision = tmp_path / "event-bus.md"
    _write_decision(decision, "RAC-PR0VENANCE07", status="Proposed")
    _commit(tmp_path, "add decision", author=AUTHOR_A, date=DATE_A)
    _write_decision(decision, "RAC-PR0VENANCE07", status="Accepted")
    _commit(tmp_path, "accept decision", author=AUTHOR_B, date=DATE_B)

    server = build_server(str(tmp_path))
    first = asyncio.run(server.call_tool("get_artifact", {"id": "RAC-PR0VENANCE07"}))[0][0].text
    second = asyncio.run(server.call_tool("get_artifact", {"id": "RAC-PR0VENANCE07"}))[0][0].text
    assert first == second
    prov = json.loads(first)["provenance"]
    assert prov["status"] == "Accepted"
    assert prov["last_author"] == _expected_author(AUTHOR_B)
    assert [c["status"] for c in prov["status_history"]] == ["Proposed", "Accepted"]
