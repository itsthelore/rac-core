"""Ops-cluster characterization tests (eval, usage, hook, release, agent-rules).

These are characterization tests added before the rebuild-scale examiner
freeze: they pin the *current* observable behavior of the ops cluster exactly,
so a from-scratch rebuild that changes any of these surfaces is caught. They do
not assert what the behavior *should* be — only what it is today.

Surfaces pinned here (unpinned before this file):

- the installed ``pre-commit`` git hook blocking path, end to end
  (staged invalid ``*.md`` -> commit refused with exit 1 and a reason on
  stderr; a valid corpus commits cleanly);
- ``rac.release.main`` exit codes 0/1/2 and its ``✓`` / ``✗`` / ``usage:``
  message shapes;
- ``evaluate_gate`` / ``GateFailure.render`` for the regression rule (a metric
  below ``baseline − tolerance`` renders ``FAIL [regression] …``, distinct from
  ``[floor]``) and the integer-formatted negative-violations rule;
- ``eval`` usage-error branches (duplicate case id, unresolved ``get_related``);
- ``usage.render_human`` empty-state / guide-section / trend / pluralization,
  ``usage.share_url`` template + report payload, and the recent-days window;
- the ``rac export --agent-rules --client`` rejection and the generate
  append-to-existing-prose branch;
- the ``post-commit`` hook not-on-PATH skip branch and ``consent.opt_in``
  preserving an ``enterprise_locked`` record.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

from rac import consent, usage
from rac.cli import main
from rac.release import main as release_main
from rac.services import eval as ev
from rac.services.agent_rules import (
    STATE_UPDATED,
    embedded_digest,
    generate_agent_rules,
)
from rac.services.hook import install_hook

# The console-script bin dir of the running interpreter; in a venv `rac` lives
# beside `python`. The git hooks shell out to `rac`, which is not otherwise on
# PATH inside the test's subprocess environment, so tests that must exercise the
# on-PATH branch prepend this. Tests that pin the not-on-PATH branch leave it out.
_BIN_DIR = str(Path(sys.executable).parent)

CORPUS = Path(__file__).parent / "eval" / "corpus"


def _git(repo: Path, *args: str, rac_on_path: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if rac_on_path:
        env["PATH"] = _BIN_DIR + os.pathsep + env.get("PATH", "")
    else:
        # Pin PATH to the system dirs so `rac` is unresolvable regardless of
        # whether the ambient environment has a venv bin dir on PATH.
        env["PATH"] = "/usr/bin:/bin"
    return subprocess.run(
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
        text=True,
        env=env,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    return tmp_path


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


# --- HIGH #1: pre-commit hook blocks invalid, passes valid (end to end) -------


def test_pre_commit_hook_blocks_invalid_and_passes_valid(repo):
    # The installed pre-commit hook refuses a commit when a staged Markdown
    # artifact fails `rac validate`, and lets a valid corpus through.
    install_hook(str(repo), "pre-commit")

    (repo / "bad.md").write_text(
        "# X\n\n## Requirements\n\n[REQ-001] a\n[REQ-001] b\n", encoding="utf-8"
    )
    _git(repo, "add", ".", rac_on_path=True)
    with pytest.raises(subprocess.CalledProcessError) as exc:
        _git(repo, "commit", "--quiet", "-m", "bad", rac_on_path=True)
    assert exc.value.returncode == 1
    assert "rac: validation failed for bad.md" in exc.value.stderr

    # Repairing the artifact lets the commit through cleanly.
    (repo / "bad.md").write_text(
        "# A\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n", encoding="utf-8"
    )
    _git(repo, "add", ".", rac_on_path=True)
    committed = _git(repo, "commit", "--quiet", "-m", "good", rac_on_path=True)
    assert committed.returncode == 0


def test_pre_commit_hook_allows_commit_when_no_markdown_staged(repo):
    install_hook(str(repo), "pre-commit")
    (repo / "note.txt").write_text("not markdown\n", encoding="utf-8")
    _git(repo, "add", ".", rac_on_path=True)
    # No staged *.md -> the hook exits 0 without running rac at all.
    committed = _git(repo, "commit", "--quiet", "-m", "text only", rac_on_path=True)
    assert committed.returncode == 0


# --- HIGH #2: rac.release.main exit codes and message shapes ------------------


def test_release_main_ok_prints_wellformed_and_returns_0(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## v0.22.0 — first cut\n", encoding="utf-8")
    assert release_main(["v0.22.0", str(changelog)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "✓ release v0.22.0 is well-formed and has a changelog entry\n"
    assert captured.err == ""


def test_release_main_rejects_bad_version_returns_1(tmp_path, capsys):
    # The reverted CalVer form is now rejected (ADR-111).
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## v0.22.0 — first cut\n", encoding="utf-8")
    assert release_main(["2026.06.1", str(changelog)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("✗ release 2026.06.1 rejected:\n")
    assert "is not a canonical SemVer release identifier" in err


def test_release_main_rejects_missing_changelog_entry_returns_1(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("nothing relevant here\n", encoding="utf-8")
    assert release_main(["v0.22.0", str(changelog)]) == 1
    err = capsys.readouterr().err
    assert "✗ release v0.22.0 rejected:" in err
    assert "no '## v0.22.0' entry found in CHANGELOG.md (REQ-005)" in err


def test_release_main_no_args_is_usage_error_returns_2(capsys):
    assert release_main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "usage: python -m rac.release <version> [changelog-path]\n"


# --- HIGH #3: eval gate regression rule + render text -------------------------


def test_gate_fires_regression_below_baseline_minus_tolerance():
    current = {
        "overall": {"p_at_1": 0.80, "r_at_5": 1.0, "negative_violations": 0},
        "by_category": {},
    }
    baseline = {"overall": {"p_at_1": 0.95, "r_at_5": 1.0, "negative_violations": 0}}
    config = {
        "tolerance": 0.02,
        "floors": {"overall": {"p_at_1": 0.0}, "negative_violations": 0},
    }
    failures = ev.evaluate_gate(current, baseline, config)
    regressions = [f for f in failures if f.rule == ev.RULE_REGRESSION]
    # The floor is satisfied (0.80 >= 0.0), so the *only* fired rule is the
    # baseline regression — not [floor].
    assert [f.rule for f in failures] == [ev.RULE_REGRESSION]
    assert regressions[0].metric == "overall.p_at_1"
    assert (
        regressions[0].render()
        == "FAIL [regression] overall.p_at_1: baseline 0.950000, current 0.800000"
    )


def test_gate_negative_render_uses_integer_limit_and_current():
    current = {"overall": {"p_at_1": 1.0, "r_at_5": 1.0, "negative_violations": 3}}
    config = {"tolerance": 0.0, "floors": {"negative_violations": 0}}
    (failure,) = ev.evaluate_gate(current, {}, config)
    assert failure.rule == ev.RULE_NEGATIVE
    assert (
        failure.render()
        == "FAIL [negative_violations] overall.negative_violations: limit 0, current 3"
    )


def test_gate_floor_render_is_distinct_from_regression():
    # A metric below its floor renders [floor] with the six-decimal floor value.
    current = {
        "overall": {"p_at_1": 0.40, "r_at_5": 1.0, "negative_violations": 0},
        "by_category": {},
    }
    config = {
        "tolerance": 0.02,
        "floors": {"overall": {"p_at_1": 0.90}, "negative_violations": 0},
    }
    failures = ev.evaluate_gate(current, {}, config)
    floor_failures = [f for f in failures if f.rule == ev.RULE_FLOOR]
    assert floor_failures
    assert (
        floor_failures[0].render()
        == "FAIL [floor] overall.p_at_1: floor 0.900000, current 0.400000"
    )


# --- MEDIUM #6: eval usage-error branches ------------------------------------


def test_duplicate_case_id_is_usage_error(tmp_path):
    query_set = tmp_path / "q.json"
    query_set.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "A",
                        "tool": "search_artifacts",
                        "query": "x",
                        "category": "c",
                        "relevant": ["I"],
                    },
                    {
                        "id": "A",
                        "tool": "search_artifacts",
                        "query": "y",
                        "category": "c",
                        "relevant": ["I"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ev.EvalUsageError, match="duplicate case id 'A'"):
        ev.load_query_set(str(query_set))


def test_get_related_unresolved_query_is_usage_error():
    case = ev.QueryCase(
        id="t",
        tool=ev.TOOL_GET_RELATED,
        query="RAC-NOPENOPENOPE",
        category="c",
        relevant=("X",),
    )
    with pytest.raises(ev.EvalUsageError, match="did not resolve to an artifact"):
        ev.returned_ids(str(CORPUS), [], case)


# --- MEDIUM #4/#5/#8: usage read-back rendering, share url, recent window -----


def _enable() -> None:
    consent.opt_in()


def test_render_human_empty_state_message():
    empty = usage.render_human(usage.summarize_usage(Path("/no/such/log.jsonl")), None)
    assert empty.startswith("RAC usage\n")
    assert "No CLI usage recorded — telemetry is off (enable with `rac telemetry on`)." in empty


def test_render_human_counts_pluralization_trend_and_guide_section(isolated):
    _enable()
    usage.record_command("validate", usage.OUTCOME_ERROR, 1)
    summary = usage.summarize_usage()
    out = usage.render_human(
        summary,
        {"tools": [{"tool": "get_summary", "calls": 2, "errors": 0}]},
    )
    assert "CLI commands: 1 calls across 1 session(s)" in out
    assert "(1 error)" in out  # singular, not "(1 errors)"
    assert "recent:" in out
    assert "Guide MCP tools:" in out
    assert "get_summary" in out


def test_share_url_carries_template_and_report_payload(isolated):
    _enable()
    usage.record_command("validate", usage.OUTCOME_OK, 1)
    url = usage.share_url(usage.summarize_usage(), {"tools": []})
    assert url.startswith("https://github.com/itsthelore/rac-core/issues/new?")
    query = urllib.parse.parse_qs(url.partition("?")[2])
    assert query["template"] == ["guide-usage-report.yml"]
    report = json.loads(query["report"][0])
    assert set(report) == {"schema_version", "cli", "guide"}


def test_recent_keeps_only_last_seven_days_ascending(isolated):
    path = usage.usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [usage._event("validate", "ok", 1) for _ in range(9)]
    for i, row in enumerate(rows):  # nine distinct UTC days
        row["ts"] = f"2026-01-0{i + 1}T00:00:00+00:00"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    summary = usage.summarize_usage(days=7)
    assert summary.total == 9  # older events still counted in the total
    assert list(summary.recent) == [
        "2026-01-03",
        "2026-01-04",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
        "2026-01-09",
    ]
    assert list(summary.recent) == sorted(summary.recent)  # ascending


# --- MEDIUM #7: agent-rules client rejection + append-to-prose generate -------

_DECISION = """---
schema_version: 1
type: decision
---
# ADR-001: Alpha

## Status

Accepted

## Category

Architecture

## Context

Context.

## Decision

Decision.

## Consequences

Consequences.
"""


def _agent_corpus(tmp_path: Path) -> Path:
    decisions = tmp_path / "rac" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "adr-001.md").write_text(_DECISION, encoding="utf-8")
    return tmp_path / "rac"


def test_cli_unknown_client_is_usage_error(tmp_path, capsys):
    # argparse's `choices` constraint on --client intercepts an unknown value
    # before the handler runs: exit 2 with an "invalid choice" message. (The
    # handler's own "rac: unknown --client" string is therefore unreachable from
    # the CLI; this pins what a user actually observes.)
    rac_dir = _agent_corpus(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["export", str(rac_dir), "--agent-rules", "--client", "bogus"])
    assert exc.value.code == 2
    assert "invalid choice: 'bogus'" in capsys.readouterr().err


def test_generate_appends_block_to_prose_without_a_block(tmp_path):
    rac_dir = _agent_corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "CLAUDE.md").write_text("# Hand written\n\nProse.\n", encoding="utf-8")

    result = generate_agent_rules(str(rac_dir), str(root), clients=["claude"])
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# Hand written\n\nProse.\n")
    assert embedded_digest(text) == result.digest
    claude_file = next(f for f in result.files if f.path == "CLAUDE.md")
    assert claude_file.state == STATE_UPDATED


# --- LOW #9 / #11: post-commit skip branch, opt_in preserves lock -------------


def test_post_commit_hook_skips_when_rac_not_on_path(repo):
    # With `rac` absent from PATH the advisory post-commit hook prints a skip
    # note to stderr and still exits 0 (the commit succeeds).
    install_hook(str(repo), "post-commit")
    (repo / "note.txt").write_text("trigger\n", encoding="utf-8")
    _git(repo, "add", ".")  # rac_on_path=False -> rac is not resolvable
    committed = _git(repo, "commit", "--quiet", "-m", "advisory")
    assert committed.returncode == 0
    assert "rac: not on PATH; skipping write-cadence nudge" in committed.stderr


def test_opt_in_preserves_existing_enterprise_lock(isolated):
    consent.save_consent(consent.Consent(enterprise_locked=True))
    minted = consent.opt_in()
    assert minted.enterprise_locked is True
    assert minted.share_usage is True
