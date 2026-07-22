"""Tests for git-derived artifact recency (v0.13.2, ADR-045).

Each test builds a throwaway git repository under ``tmp_path`` with controlled
commit times; the suite never touches this repository's own git state. Recency
is read-only and degrades to "unknown" (``None``) outside git or for
uncommitted files, never raising.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from asdecided import cli
from asdecided.mcp.server import build_server
from asdecided.output import human as human_output
from asdecided.output import json as json_output
from asdecided.services.recency import (
    DEFAULT_STALE_AFTER_DAYS,
    Staleness,
    annotate_search_recency,
    artifact_recency,
    load_freshness_threshold,
    recency_for_paths,
    staleness,
)
from asdecided.services.resolve import find_artifacts

_REQUIREMENT = "# {title}\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
_DECISION = "# {title}\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n"


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


# --- service -----------------------------------------------------------------


def test_recency_returns_known_commit_time(tmp_path):
    _init(tmp_path)
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T12:00:00+00:00")

    report = artifact_recency(str(tmp_path))
    assert len(report.artifacts) == 1
    art = report.artifacts[0]
    assert art.last_committed == datetime.fromisoformat("2026-01-01T12:00:00+00:00")
    assert report.most_recent == datetime.fromisoformat("2026-01-01T12:00:00+00:00")


def test_recency_unknown_for_uncommitted_file(tmp_path):
    _init(tmp_path)
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "committed.md").write_text(_REQUIREMENT.format(title="C"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T12:00:00+00:00")
    # A new, never-committed artifact.
    (corpus / "new.md").write_text(_REQUIREMENT.format(title="N"), encoding="utf-8")

    report = artifact_recency(str(tmp_path))
    by_path = {Path(a.path).name: a.last_committed for a in report.artifacts}
    assert by_path["committed.md"] is not None
    assert by_path["new.md"] is None
    # Aggregate ignores the unknown.
    assert report.most_recent == datetime.fromisoformat("2026-01-01T12:00:00+00:00")


def test_recency_most_recent_by_type(tmp_path):
    _init(tmp_path)
    reqs = tmp_path / "rac" / "requirements"
    decs = tmp_path / "rac" / "decisions"
    reqs.mkdir(parents=True)
    decs.mkdir(parents=True)
    (reqs / "r.md").write_text(_REQUIREMENT.format(title="R"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "req", when="2026-01-01T00:00:00+00:00")
    (decs / "d.md").write_text(_DECISION.format(title="D"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "dec", when="2026-03-01T00:00:00+00:00")

    report = artifact_recency(str(tmp_path))
    by_type = report.most_recent_by_type()
    assert by_type["requirement"] == datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    assert by_type["decision"] == datetime.fromisoformat("2026-03-01T00:00:00+00:00")
    # The overall aggregate is the newest of the two.
    assert report.most_recent == datetime.fromisoformat("2026-03-01T00:00:00+00:00")


def test_recency_outside_git_is_all_unknown(tmp_path):
    # No `git init`: a plain directory of artifacts.
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")

    report = artifact_recency(str(tmp_path))
    assert len(report.artifacts) == 1
    assert report.artifacts[0].last_committed is None
    assert report.most_recent is None
    assert report.most_recent_by_type() == {}


def test_recency_excludes_unknown_documents(tmp_path):
    _init(tmp_path)
    corpus = tmp_path / "rac"
    corpus.mkdir(parents=True)
    (corpus / "prose.md").write_text("# Notes\n\nJust prose.\n", encoding="utf-8")
    (corpus / "r.md").write_text(_REQUIREMENT.format(title="R"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T00:00:00+00:00")

    report = artifact_recency(str(tmp_path))
    # Only the recognised requirement is tracked, not the prose document.
    assert [Path(a.path).name for a in report.artifacts] == ["r.md"]


def test_recency_to_dict_shape(tmp_path):
    _init(tmp_path)
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T12:00:00+00:00")

    payload = artifact_recency(str(tmp_path)).to_dict()
    assert payload["schema_version"] == "1"
    assert payload["most_recent"] == "2026-01-01T12:00:00+00:00"
    assert payload["by_type"]["requirement"] == "2026-01-01T12:00:00+00:00"
    assert payload["artifacts"][0]["type"] == "requirement"
    assert payload["artifacts"][0]["last_committed"] == "2026-01-01T12:00:00+00:00"


# --- staleness indicator (freshness-and-drift phase 1, REQ-004) --------------
#
# ``staleness`` is a deterministic function of a last-committed date against a
# threshold. The ``reference`` parameter pins "now" so the derived age and flag
# are exact — no wall-clock dependence in these assertions.

_REF = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def test_staleness_unknown_date_is_all_none():
    # Outside git / untracked: no date, so no derived age or flag — never a
    # fabricated date (REQ-003, ADR-045 posture).
    result = staleness(None, reference=_REF)
    assert result == Staleness(None, None, None)
    assert result.to_dict() == {"last_committed": None, "age_days": None, "stale": None}


def test_staleness_fresh_below_threshold():
    committed = _REF - timedelta(days=100)
    result = staleness(committed, threshold_days=180, reference=_REF)
    assert result.age_days == 100
    assert result.stale is False
    assert result.last_committed == committed


def test_staleness_stale_above_threshold():
    result = staleness(_REF - timedelta(days=181), threshold_days=180, reference=_REF)
    assert result.age_days == 181
    assert result.stale is True


def test_staleness_boundary_is_not_stale_at_exactly_threshold():
    # ``stale`` is age > threshold, so an artifact exactly at the threshold is
    # still fresh — the boundary is documented and deterministic (REQ-004).
    result = staleness(_REF - timedelta(days=180), threshold_days=180, reference=_REF)
    assert result.age_days == 180
    assert result.stale is False


def test_staleness_respects_custom_threshold():
    committed = _REF - timedelta(days=45)
    assert staleness(committed, threshold_days=30, reference=_REF).stale is True
    assert staleness(committed, threshold_days=90, reference=_REF).stale is False


def test_staleness_default_threshold_is_180():
    assert DEFAULT_STALE_AFTER_DAYS == 180
    assert staleness(_REF - timedelta(days=179), reference=_REF).stale is False
    assert staleness(_REF - timedelta(days=181), reference=_REF).stale is True


def test_staleness_to_dict_serialises_date():
    committed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    payload = staleness(committed, threshold_days=180, reference=_REF).to_dict()
    assert payload == {
        "last_committed": "2026-01-01T12:00:00+00:00",
        "age_days": 181,
        "stale": True,
    }


# --- freshness threshold config (REQ-004) ------------------------------------


def _write_config(tmp_path: Path, body: str) -> None:
    config_dir = tmp_path / ".decided"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(body, encoding="utf-8")


def test_threshold_defaults_when_no_config(tmp_path):
    assert load_freshness_threshold(str(tmp_path)) == DEFAULT_STALE_AFTER_DAYS


def test_threshold_reads_freshness_stanza(tmp_path):
    _write_config(tmp_path, "repository_key: acme\nfreshness:\n  stale_after_days: 30\n")
    assert load_freshness_threshold(str(tmp_path)) == 30


def test_threshold_found_from_subdirectory(tmp_path):
    _write_config(tmp_path, "freshness:\n  stale_after_days: 45\n")
    sub = tmp_path / "rac" / "requirements"
    sub.mkdir(parents=True)
    assert load_freshness_threshold(str(sub)) == 45


def test_threshold_defaults_without_freshness_stanza(tmp_path):
    _write_config(tmp_path, "repository_key: acme\n")
    assert load_freshness_threshold(str(tmp_path)) == DEFAULT_STALE_AFTER_DAYS


def test_threshold_defaults_on_non_positive_or_wrong_type(tmp_path):
    for body in (
        "freshness:\n  stale_after_days: 0\n",
        "freshness:\n  stale_after_days: -5\n",
        "freshness:\n  stale_after_days: soon\n",
        "freshness:\n  stale_after_days: true\n",  # bool is not a day count
        "freshness: not-a-mapping\n",
    ):
        _write_config(tmp_path, body)
        assert load_freshness_threshold(str(tmp_path)) == DEFAULT_STALE_AFTER_DAYS


def test_threshold_defaults_on_malformed_yaml(tmp_path):
    _write_config(tmp_path, "freshness: [unterminated\n")
    assert load_freshness_threshold(str(tmp_path)) == DEFAULT_STALE_AFTER_DAYS


# --- recency_for_paths / annotate (REQ-001, REQ-003, REQ-005) ----------------


def _ancient_and_fresh(tmp_path: Path) -> tuple[str, str]:
    """A git repo with one ancient artifact and one committed just now.

    Returns the two artifact paths. The ancient one is decades old, so it is
    ``stale`` against any sane threshold regardless of wall-clock; the fresh one
    is committed at real "now" (age 0), so it is never stale.
    """
    _init(tmp_path)
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    ancient = corpus / "ancient.md"
    fresh = corpus / "fresh.md"
    ancient.write_text(_REQUIREMENT.format(title="Ancient Widget"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "ancient", when="2000-01-01T00:00:00+00:00")
    fresh.write_text(_REQUIREMENT.format(title="Fresh Widget"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "fresh")
    return str(ancient), str(fresh)


def test_recency_for_paths_exact_age_with_reference(tmp_path):
    _init(tmp_path)
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init", when="2026-01-01T00:00:00+00:00")

    path = str(corpus / "a.md")
    reference = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    result = recency_for_paths(str(tmp_path), [path], threshold_days=180, reference=reference)
    assert result[path].age_days == 181
    assert result[path].stale is True


def test_recency_for_paths_outside_git_is_unknown(tmp_path):
    corpus = tmp_path / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(_REQUIREMENT.format(title="A"), encoding="utf-8")
    path = str(corpus / "a.md")
    result = recency_for_paths(str(tmp_path), [path])
    assert result[path] == Staleness(None, None, None)


def test_annotate_search_recency_is_noop_on_empty():
    # Guard the degenerate case: no matches, no git calls, no error.
    assert annotate_search_recency([], "/nonexistent") is None


def test_annotate_search_recency_joins_stale_flag(tmp_path):
    _ancient_and_fresh(tmp_path)
    result = find_artifacts(str(tmp_path), "widget")
    annotate_search_recency(result.matches, str(tmp_path))
    by_title = {m.title: m.recency for m in result.matches}
    assert by_title["Ancient Widget"]["stale"] is True
    assert by_title["Fresh Widget"]["stale"] is False
    # last_committed is the git fact; both are present strings.
    assert by_title["Ancient Widget"]["last_committed"].startswith("2000-01-01")


def test_annotate_search_recency_threshold_override(tmp_path):
    # A tiny threshold with a far-future reference flips even the fresh file to
    # stale — the join honours the passed threshold, not just the config default.
    _ancient_and_fresh(tmp_path)
    result = find_artifacts(str(tmp_path), "widget")
    reference = datetime(2030, 1, 1, tzinfo=UTC)
    annotate_search_recency(result.matches, str(tmp_path), threshold_days=1, reference=reference)
    assert all(m.recency["stale"] is True for m in result.matches)


# --- read surfaces: find JSON / human / MCP search (REQ-001, REQ-006) --------


def test_find_json_carries_recency_stale_flags(tmp_path):
    ancient, fresh = _ancient_and_fresh(tmp_path)
    result = find_artifacts(str(tmp_path), "widget")
    annotate_search_recency(result.matches, str(tmp_path))
    payload = json.loads(json_output.render_find_json(result))
    by_path = {m["path"]: m["recency"] for m in payload["matches"]}
    assert by_path[ancient]["stale"] is True
    assert by_path[fresh]["stale"] is False
    # Additive: schema_version is unchanged and recency sits beside the metadata.
    assert payload["schema_version"] == "1"


def test_find_human_marks_only_stale_matches(tmp_path):
    _ancient_and_fresh(tmp_path)
    result = find_artifacts(str(tmp_path), "widget")
    annotate_search_recency(result.matches, str(tmp_path))
    rendered = human_output.render_find_human(result)
    # The ancient match carries the inline marker; the fresh one does not.
    ancient_line = next(line for line in rendered.splitlines() if "Ancient Widget" in line)
    fresh_line = next(line for line in rendered.splitlines() if "Fresh Widget" in line)
    assert "stale" in ancient_line
    assert "stale" not in fresh_line


def test_mcp_search_carries_recency_within_budget(tmp_path):
    _ancient_and_fresh(tmp_path)
    server = build_server(str(tmp_path))
    contents, _ = asyncio.run(server.call_tool("search_artifacts", {"query": "widget"}))
    payload = json.loads(contents[0].text)
    assert payload["match_count"] == 2
    assert "truncated" not in payload  # REQ-007: budget unaffected on a small corpus
    for match in payload["matches"]:
        assert set(match["recency"]) == {"last_committed", "age_days", "stale"}


def test_cli_find_wires_recency_end_to_end(tmp_path, capsys):
    # Through the real `decided find` command (not a manual annotate): the JSON face
    # carries recency, and the human face flags the ancient match inline.
    ancient, _fresh = _ancient_and_fresh(tmp_path)
    cli.main(["find", "widget", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    by_path = {m["path"]: m["recency"] for m in payload["matches"]}
    assert by_path[ancient]["stale"] is True

    cli.main(["find", "widget", str(tmp_path)])
    human = capsys.readouterr().out
    assert "stale" in next(line for line in human.splitlines() if "Ancient Widget" in line)
