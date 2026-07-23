"""Characterization tests for the relationships / coverage / rename cluster.

These tests were added before the rebuild-scale examiner freeze (Phase 0.5).
They pin the *current* observable behaviour of the graph cluster exactly as it
stands today — including the parts that are odd or asymmetric (the rename
refusal routed to stderr while previews go to stdout, the exact human block
order and wording, the SARIF message text, the singular/plural coverage
boundary). They are a safety net for the reimplementation, not an endorsement:
nothing here is "corrected". If a behaviour below looks wrong, that is the point
— the rebuild must reproduce it or consciously change it.

Expected strings were captured by running the current code against small,
purpose-built corpora; they are embedded inline (no new golden files). Color is
disabled because pytest's stdout is not a TTY, so the human renderers emit plain
text (see ``asdecided.output.human._USE_COLOR``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from asdecided.cli import main
from asdecided.output.human import (
    render_relationship_validation_human,
    render_relationships_human,
)
from asdecided.output.json import render_relationships_json
from asdecided.output.sarif import render_relationships_sarif
from asdecided.services.coverage import analyze_coverage, render_coverage_human
from asdecided.services.relationships import (
    ISSUE_RELATIONSHIP_CYCLE,
    Relationship,
    build_relationship_report,
    neighborhood,
    validate_relationships,
)
from asdecided.services.rename import (
    apply_rename,
    compute_rename,
)

# --- fixtures / builders -----------------------------------------------------


def _dec(title: str, *, status: str = "Accepted", extra: str = "") -> str:
    return (
        f"# {title}\n\n## Context\n\nc\n\n## Decision\n\nd\n\n"
        f"## Consequences\n\nx\n\n## Status\n\n{status}\n{extra}\n"
    )


def _req(title: str, extra: str = "") -> str:
    return f"# {title}\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] do the thing\n{extra}\n"


def _dec_id_section(id_value: str, *, related: list[str] | None = None) -> str:
    """A decision whose identity is an editable ``## ID`` section (not the filename)."""
    related_block = ""
    if related:
        related_block = "\n## Related Decisions\n\n" + "".join(f"- {r}\n" for r in related)
    return (
        f"# {id_value} A Decision\n\n## ID\n\n{id_value}\n\n"
        "## Context\n\nWhy.\n\n## Decision\n\nWhat.\n\n## Consequences\n\nResults.\n"
        f"{related_block}"
    )


def _write_coverage_artifact(
    base: Path, name: str, ident: str, atype: str, body: str, related: str = ""
) -> None:
    (base / name).write_text(
        f"---\nschema_version: 1\nid: {ident}\ntype: {atype}\n---\n# {ident}\n\n{body}{related}",
        encoding="utf-8",
    )


_REQ_BODY = "## Problem\n\nNeeded.\n\n## Requirements\n\n- [REQ-001] The system MUST do X.\n"


@pytest.fixture
def rename_corpus(tmp_path: Path) -> Path:
    """Three ``## ID`` decisions: two reference the target, which declares ADR-001."""
    (tmp_path / "adr-001-target.md").write_text(_dec_id_section("ADR-001"))
    (tmp_path / "adr-002-source.md").write_text(_dec_id_section("ADR-002", related=["ADR-001"]))
    (tmp_path / "adr-003-source.md").write_text(_dec_id_section("ADR-003", related=["ADR-001"]))
    return tmp_path


@pytest.fixture
def validation_corpus(tmp_path: Path) -> Path:
    """A corpus carrying one of every validation-block finding at once.

    Duplicate identifier (two ``adr-777`` files), an unsupported edge
    (``## Verified By`` on a decision), a supersedes 2-cycle, a range mismatch
    (a requirement's ``## Related Decisions`` pointing at another requirement),
    and a plain not-found reference — so block ordering and wording are pinned
    together.
    """
    (tmp_path / "adr-777.md").write_text(_dec("ADR-777 First"))
    (tmp_path / "adr-777-alt.md").write_text(_dec("ADR-777 Second"))
    (tmp_path / "unsup.md").write_text(
        _dec("Unsup", extra="\n## Verified By\n\n- `tests/x.spec.ts`\n")
    )
    (tmp_path / "a.md").write_text(_dec("A", extra="\n## Supersedes\n\n- b\n"))
    (tmp_path / "b.md").write_text(_dec("B", extra="\n## Supersedes\n\n- a\n"))
    (tmp_path / "target-req.md").write_text(_req("Target Requirement"))
    (tmp_path / "src.md").write_text(_req("Src", "\n## Related Decisions\n\n- target-req\n"))
    (tmp_path / "missing-src.md").write_text(_req("MSrc", "\n## Related Decisions\n\n- nope\n"))
    return tmp_path


# --- Finding 1: rename human output + stderr routing on refusal [HIGH] --------


def test_cli_rename_refusal_human_goes_to_stderr(rename_corpus: Path, capsys):
    # A refusal prints via render_rename_human to STDERR (not stdout) and exits 1.
    rc = main(["rename", "ADR-404", "ADR-099", str(rename_corpus)])
    assert rc == 1
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "Rename ADR-404 -> ADR-099" in cap.err
    assert "✗ Refused: no artifact resolves to that id." in cap.err


def test_cli_rename_dry_run_human_goes_to_stdout(rename_corpus: Path, capsys):
    # A dry-run preview prints via render_rename_human to STDOUT and exits 0.
    rc = main(["rename", "ADR-001", "ADR-099", str(rename_corpus)])
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.err == ""
    out = cap.out
    assert out.startswith("Rename ADR-001 -> ADR-099\n=========================\n")
    assert "(identity field: id_section)" in out
    assert "2 inbound reference(s), 1 identity edit across 3 file(s)." in out
    assert "    L5 ✗ ADR-001" in out
    assert "    L5 ✓ ADR-099" in out
    assert out.rstrip().endswith("Dry run — pass --apply to write these edits.")


def test_cli_rename_applied_human_goes_to_stdout(rename_corpus: Path, capsys):
    # An applied rename prints via render_rename_result_human to STDOUT, exit 0.
    rc = main(["rename", "ADR-001", "ADR-099", str(rename_corpus), "--apply"])
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.err == ""
    assert "Rename ADR-001 -> ADR-099" in cap.out
    assert "✓ Applied: 2 reference(s) and 1 identity edit across 3 file(s)." in cap.out


# --- Finding 2: applied-rename JSON contract [HIGH] ---------------------------


def test_cli_rename_apply_json_contract(rename_corpus: Path, capsys):
    rc = main(["rename", "ADR-001", "ADR-099", str(rename_corpus), "--apply", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == [
        "directory",
        "old_ref",
        "new_ref",
        "applied",
        "target_path",
        "files_changed",
        "reference_edits",
        "identity_edits",
    ]
    assert payload["applied"] is True
    assert payload["reference_edits"] == 2
    assert payload["identity_edits"] == 1
    assert payload["files_changed"] == 3
    assert payload["old_ref"] == "ADR-001"
    assert payload["new_ref"] == "ADR-099"


# --- Finding 3: rename plan JSON edits[] shape and full key set [HIGH] --------


def test_cli_rename_plan_json_full_shape(rename_corpus: Path, capsys):
    rc = main(["rename", "ADR-001", "ADR-099", str(rename_corpus), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "directory",
        "recursive",
        "old_ref",
        "new_ref",
        "ok",
        "reason",
        "target_path",
        "identity_field",
        "files_changed",
        "reference_edits",
        "identity_edits",
        "edits",
    }
    assert payload["ok"] is True
    assert payload["reason"] is None
    assert payload["identity_field"] == "id_section"
    assert len(payload["edits"]) == 3
    for edit in payload["edits"]:
        assert set(edit) == {"path", "line", "old_line", "new_line", "kind"}
    assert {e["kind"] for e in payload["edits"]} == {"reference", "identity"}


# --- Finding 4: human validation blocks + ordering [HIGH] ---------------------


def test_validation_human_blocks_and_ordering(validation_corpus: Path):
    report = validate_relationships(str(validation_corpus))
    out = render_relationship_validation_human(report)

    # All four block headers are present.
    assert "Duplicate Identifiers" in out
    assert "Unsupported Relationships" in out
    assert "Relationship Cycles" in out
    assert "Broken Relationships" in out

    # Exact line renderings for the first three (unpinned before this test).
    assert "✗ adr-777 (2 files)" in out
    assert "  ✗ Verified By not supported for this artifact type" in out
    assert "✗ Supersedes cycle:" in out

    # Fixed block order: duplicates -> unsupported -> cycles -> broken.
    assert (
        out.index("Duplicate Identifiers")
        < out.index("Unsupported Relationships")
        < out.index("Relationship Cycles")
        < out.index("Broken Relationships")
    )


# --- Finding 5: human suffix "wrong target type" for range mismatch [HIGH] ----


def test_validation_human_range_mismatch_suffix(validation_corpus: Path):
    report = validate_relationships(str(validation_corpus))
    out = render_relationship_validation_human(report)
    # The range-violation reference renders with the "wrong target type" suffix.
    assert "✗ target-req wrong target type" in out
    # A plain missing reference still renders "not found" (contrast, same block).
    assert "✗ nope not found" in out


# --- Finding 6: SARIF message text + level + uri anchoring for cycle [MED-HIGH]


def test_sarif_cycle_message_level_and_uri(tmp_path: Path):
    (tmp_path / "a.md").write_text(_dec("A", extra="\n## Supersedes\n\n- b\n"))
    (tmp_path / "b.md").write_text(_dec("B", extra="\n## Supersedes\n\n- a\n"))
    report = validate_relationships(str(tmp_path))
    doc = json.loads(render_relationships_sarif(report))
    results = doc["runs"][0]["results"]
    cycle = next(r for r in results if r["ruleId"] == ISSUE_RELATIONSHIP_CYCLE)
    assert cycle["level"] == "error"
    assert cycle["message"]["text"].startswith("supersedes relationship cycle:")
    # The finding anchors on the first (sorted) component path.
    uri = cycle["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == str(tmp_path / "a.md")
    assert " -> " in cycle["message"]["text"]


# --- Finding 7: coverage human output — clean case, summary, pluralization ----


def test_coverage_human_single_gap_summary(tmp_path: Path):
    _write_coverage_artifact(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", _REQ_BODY)
    out = render_coverage_human(analyze_coverage(str(tmp_path)))
    # Exactly one gap -> singular "1 coverage gap (" (the plural boundary).
    assert "1 coverage gap (1 unscheduled, 0 unapplied, 0 unscoped)" in out
    assert out.rstrip().endswith("— advisory, not a build failure.")
    assert "Unscheduled requirements (no roadmap schedules them): 1" in out


def test_coverage_human_clean_case(tmp_path: Path):
    out = render_coverage_human(analyze_coverage(str(tmp_path)))
    assert "✓ No coverage gaps — every artifact has its expected traceability edge." in out
    assert "coverage gap" not in out.split("✓", 1)[0]  # no gap summary line


# --- Finding 8: apply_rename stale-plan ValueError [MEDIUM] -------------------


def test_apply_rename_stale_plan_raises(rename_corpus: Path):
    plan = compute_rename(str(rename_corpus), "ADR-001", "ADR-099")
    # Mutate a referenced file after computing the plan.
    (rename_corpus / "adr-002-source.md").write_text("totally different\n")
    with pytest.raises(ValueError, match="stale plan"):
        apply_rename(plan)


# --- Finding 9: neighborhood max_frontier truncation flag [MEDIUM] ------------


def test_neighborhood_max_frontier_truncates_and_flags():
    # Star graph: origin "a" links b, c, d, e (all one hop).
    rels = [
        Relationship(
            source_path="a",
            relationship="related_decisions",
            target=x,
            resolved_path=x,
            issue=None,
        )
        for x in ("b", "c", "d", "e")
    ]
    identity = {p: (f"ID-{p}", "decision", f"T {p}") for p in ("a", "b", "c", "d", "e")}
    hood = neighborhood(rels, identity, "a", depth=2, max_frontier=1)
    # More than one node admitted at a level trips the distinct max_frontier flag.
    assert hood.truncated is True


# --- Finding 10: non-validate By Type counts for external/scope sections [MED] -


def test_non_validate_counts_related_tickets(tmp_path: Path):
    (tmp_path / "adr-001.md").write_text(_dec("A1", extra="\n## Related Tickets\n\n- PROJ-1\n"))
    report = build_relationship_report(str(tmp_path))
    assert report.counts["related_tickets"] == 1
    # JSON contract carries the external-edge count.
    payload = json.loads(render_relationships_json(report))
    assert payload["counts"]["related_tickets"] == 1
    # Human By Type section labels and counts it.
    assert "- Related Tickets: 1" in render_relationships_human(report)


# --- Finding 11: coverage JSON `missing` string values [LOW-MEDIUM] -----------


def test_coverage_missing_prose(tmp_path: Path):
    _write_coverage_artifact(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", _REQ_BODY)
    report = analyze_coverage(str(tmp_path))
    assert report.gaps[0].missing == "no roadmap schedules this requirement"
