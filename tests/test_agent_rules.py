"""Tests for `rac export --agent-rules [--check]` (roadmap v0.21.15, ADR-067).

The agent-rules projection is a distilled, drift-guarded view of the *live*
corpus. These tests pin the boundary ADR-067 fixes:

- the projection lists live (Accepted) decisions and excludes retired
  (Superseded/Deprecated) ones and non-decision artifacts;
- the digest is deterministic for a fixed corpus and changes when the live set
  changes (a decision added or retired);
- generate writes a managed block carrying the digest, preserves content
  outside the block on regeneration, and is idempotent;
- --check exits zero in sync, non-zero on drift or a missing block, and never
  writes;
- the four per-client files have the expected names/paths;
- the empty-corpus boundary yields an empty block and a clean check.
"""

from __future__ import annotations

import json
from pathlib import Path

from rac.cli import main
from rac.services.agent_rules import (
    STATE_IN_SYNC,
    STATE_MISSING,
    STATE_STALE,
    STATE_UPDATED,
    STATE_WRITTEN,
    build_agent_rules_block,
    check_agent_rules,
    embedded_digest,
    generate_agent_rules,
    render_managed_block,
)

# --- corpus fixtures ---------------------------------------------------------

# No frontmatter ``id`` — identity falls back to the filename prefix (e.g.
# ``adr-001``), which keeps the fixtures readable without minting valid ULIDs.
_DECISION = """---
schema_version: 1
type: decision
---
# {title}

## Status

{status}

## Category

{category}

## Context

Context.

## Decision

Decision.

## Consequences

Consequences.
"""

_REQUIREMENT = """---
schema_version: 1
type: requirement
---
# A Requirement

## Status

Active

## Description

A requirement, not a decision — must never appear in the projection.
"""


def _write_decision(
    directory: Path, slug: str, title: str, status: str, category: str = "Architecture"
) -> None:
    (directory / f"{slug}.md").write_text(
        _DECISION.format(title=title, status=status, category=category),
        encoding="utf-8",
    )


def _corpus(tmp_path: Path) -> Path:
    """A small corpus: two live decisions, one superseded, one deprecated, one
    requirement — enough to exercise inclusion, exclusion, and ordering."""
    rac_dir = tmp_path / "rac"
    decisions = rac_dir / "decisions"
    decisions.mkdir(parents=True)
    _write_decision(decisions, "adr-001-alpha", "ADR-001: Alpha", "Accepted")
    _write_decision(decisions, "adr-002-beta", "ADR-002: Beta", "Accepted", category="Product")
    _write_decision(decisions, "adr-003-old", "ADR-003: Old", "Superseded")
    _write_decision(decisions, "adr-004-dead", "ADR-004: Dead", "Deprecated")
    (decisions / "req.md").write_text(_REQUIREMENT, encoding="utf-8")
    return rac_dir


# --- projection: inclusion / exclusion / ordering ----------------------------


def test_projection_lists_live_excludes_retired_and_non_decisions(tmp_path):
    projection = build_agent_rules_block(str(_corpus(tmp_path)))
    ids = [e.identifier for e in projection.entries]
    # Only the two Accepted decisions, deterministically ordered by identifier.
    assert ids == ["adr-001", "adr-002"]
    titles = {e.title for e in projection.entries}
    assert "ADR-003: Old" not in titles  # superseded excluded
    assert "ADR-004: Dead" not in titles  # deprecated excluded
    assert all("Requirement" not in t for t in titles)  # non-decision excluded


def test_projection_carries_category(tmp_path):
    projection = build_agent_rules_block(str(_corpus(tmp_path)))
    by_id = {e.identifier: e for e in projection.entries}
    assert by_id["adr-001"].category == "Architecture"
    assert by_id["adr-002"].category == "Product"


# --- digest: determinism and sensitivity -------------------------------------


def test_digest_is_deterministic(tmp_path):
    corpus = str(_corpus(tmp_path))
    assert build_agent_rules_block(corpus).digest == build_agent_rules_block(corpus).digest


def test_digest_changes_when_a_live_decision_is_added(tmp_path):
    rac_dir = _corpus(tmp_path)
    before = build_agent_rules_block(str(rac_dir)).digest
    _write_decision(rac_dir / "decisions", "adr-005-new", "ADR-005: New", "Accepted")
    after = build_agent_rules_block(str(rac_dir)).digest
    assert before != after


def test_digest_changes_when_a_live_decision_is_retired(tmp_path):
    rac_dir = _corpus(tmp_path)
    before = build_agent_rules_block(str(rac_dir)).digest
    # Retire one of the live decisions.
    _write_decision(rac_dir / "decisions", "adr-001-alpha", "ADR-001: Alpha", "Superseded")
    after = build_agent_rules_block(str(rac_dir)).digest
    assert before != after


# --- managed block rendering -------------------------------------------------


def test_managed_block_embeds_digest_and_lists_entries(tmp_path):
    projection = build_agent_rules_block(str(_corpus(tmp_path)))
    block = render_managed_block(projection)
    assert embedded_digest(block) == projection.digest
    assert "adr-001" in block
    assert "ADR-003: Old" not in block  # retired never rendered


# --- generate ----------------------------------------------------------------


def test_generate_writes_four_client_files_with_the_digest(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    result = generate_agent_rules(str(rac_dir), str(root))

    paths = {f.path for f in result.files}
    assert paths == {
        "CLAUDE.md",
        "AGENTS.md",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    }
    for f in result.files:
        assert f.state == STATE_WRITTEN
        text = (root / f.path).read_text(encoding="utf-8")
        assert embedded_digest(text) == result.digest


def test_generate_preserves_content_outside_the_block(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    generate_agent_rules(str(rac_dir), str(root))

    claude = root / "CLAUDE.md"
    original = claude.read_text(encoding="utf-8")
    claude.write_text(f"# My header\n\nUser prose.\n\n{original}\nUser footer.\n", encoding="utf-8")

    # Add a live decision so the block must be regenerated.
    _write_decision(rac_dir / "decisions", "adr-005-new", "ADR-005: New", "Accepted")
    result = generate_agent_rules(str(rac_dir), str(root))

    updated = claude.read_text(encoding="utf-8")
    assert updated.startswith("# My header\n\nUser prose.\n")
    assert updated.rstrip().endswith("User footer.")
    assert "adr-005" in updated  # new block content present
    claude_result = next(f for f in result.files if f.path == "CLAUDE.md")
    assert claude_result.state == STATE_UPDATED


def test_generate_is_idempotent(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    generate_agent_rules(str(rac_dir), str(root))
    first = (root / "CLAUDE.md").read_text(encoding="utf-8")
    second_result = generate_agent_rules(str(rac_dir), str(root))
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == first
    assert all(f.state == STATE_IN_SYNC for f in second_result.files)


def test_generate_respects_client_filter(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    result = generate_agent_rules(str(rac_dir), str(root), clients=["claude"])
    assert [f.path for f in result.files] == ["CLAUDE.md"]
    assert (root / "CLAUDE.md").exists()
    assert not (root / "AGENTS.md").exists()


# --- check -------------------------------------------------------------------


def test_check_passes_when_in_sync_and_does_not_write(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    generate_agent_rules(str(rac_dir), str(root))

    before = {
        f.path: (root / f.path).read_text(encoding="utf-8")
        for f in check_agent_rules(str(rac_dir), str(root)).files
    }
    result = check_agent_rules(str(rac_dir), str(root))
    assert not result.drifted
    assert all(f.state == STATE_IN_SYNC for f in result.files)
    # No file changed.
    for path, text in before.items():
        assert (root / path).read_text(encoding="utf-8") == text


def test_check_fails_on_drift_when_corpus_changed(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    generate_agent_rules(str(rac_dir), str(root))

    # Corpus changes but files are not regenerated.
    _write_decision(rac_dir / "decisions", "adr-005-new", "ADR-005: New", "Accepted")
    result = check_agent_rules(str(rac_dir), str(root))
    assert result.drifted
    assert all(f.state == STATE_STALE for f in result.files)


def test_check_fails_when_block_missing(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    # No files generated at all -> all targets missing.
    result = check_agent_rules(str(rac_dir), str(root))
    assert result.drifted
    assert all(f.state == STATE_MISSING for f in result.files)


def test_check_reports_file_without_managed_block_as_missing(tmp_path):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "CLAUDE.md").write_text("# Just prose, no managed block.\n", encoding="utf-8")
    result = check_agent_rules(str(rac_dir), str(root), clients=["claude"])
    assert result.files[0].state == STATE_MISSING
    assert result.drifted


# --- empty-corpus boundary ---------------------------------------------------


def test_empty_corpus_yields_empty_block_and_clean_check(tmp_path):
    rac_dir = tmp_path / "rac"
    rac_dir.mkdir()
    root = tmp_path / "repo"
    root.mkdir()

    projection = build_agent_rules_block(str(rac_dir))
    assert projection.entries == []
    block = render_managed_block(projection)
    assert "No live decisions recorded yet" in block

    generate_agent_rules(str(rac_dir), str(root))
    result = check_agent_rules(str(rac_dir), str(root))
    assert not result.drifted


# --- CLI integration ---------------------------------------------------------


def test_cli_generate_then_check_roundtrip(tmp_path, capsys):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()

    assert main(["export", str(rac_dir), "--agent-rules", "--out", str(root)]) == 0
    capsys.readouterr()
    assert main(["export", str(rac_dir), "--agent-rules", "--check", "--out", str(root)]) == 0
    capsys.readouterr()

    # Retire a live decision -> the committed files drift -> check exits non-zero.
    _write_decision(rac_dir / "decisions", "adr-001-alpha", "ADR-001: Alpha", "Superseded")
    assert main(["export", str(rac_dir), "--agent-rules", "--check", "--out", str(root)]) == 1


def test_cli_agent_rules_json_output(tmp_path, capsys):
    rac_dir = _corpus(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    rc = main(["export", str(rac_dir), "--agent-rules", "--json", "--out", str(root)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "generate"
    assert {f["path"] for f in payload["files"]} == {
        "CLAUDE.md",
        "AGENTS.md",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    }


def test_cli_check_without_agent_rules_is_usage_error(tmp_path, capsys):
    rac_dir = _corpus(tmp_path)
    try:
        main(["export", str(rac_dir), "--check"])
        raised = False
    except SystemExit as exc:
        raised = exc.code == 2
    assert raised
