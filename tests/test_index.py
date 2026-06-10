"""Tests for rac.services.index and the `rac index` CLI command (v0.7.5).

`rac index` is a deterministic, read-only repository manifest: which artifacts
exist, plus their stable identity, type, title, and path — nothing more (no
status, no dates, no analysis). See the v0.7.5 roadmap and ADR-023.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rac.cli import main
from rac.services.index import build_repository_index

# Reuse the portfolio fixture that already holds all five types + an unknown.
ALL_TYPES = Path(__file__).parent / "fixtures" / "portfolio_summary" / "all_types"


# --- discovery + coverage (Initiative 2, REQ-003) ---------------------------


def test_indexes_all_types_and_unknown():
    index = build_repository_index(str(ALL_TYPES))
    types = {e.type for e in index.artifacts}
    assert types == {
        "requirement",
        "decision",
        "roadmap",
        "prompt",
        "design",
        "unknown",
    }
    assert index.artifact_count == 6


def test_every_entry_has_nonempty_id_including_unknown():
    # REQ-002: a stable identity for every indexed artifact, Unknown included
    # (filename-stem fallback).
    index = build_repository_index(str(ALL_TYPES))
    assert all(e.id for e in index.artifacts)
    unknown = [e for e in index.artifacts if e.type == "unknown"]
    assert len(unknown) == 1
    assert unknown[0].id  # stem-derived, non-empty


def test_entries_sorted_by_path_and_deterministic():
    i1 = build_repository_index(str(ALL_TYPES))
    i2 = build_repository_index(str(ALL_TYPES))
    paths = [e.path for e in i1.artifacts]
    assert paths == sorted(paths)
    assert i1.to_dict() == i2.to_dict()


# --- identity precedence through the index (REQ-002) ------------------------


def test_explicit_id_section_beats_filename_stem(tmp_path):
    (tmp_path / "explicit-id.md").write_text(
        "# Some Decision\n\n## ID\n\nDEC-99\n\n"
        "## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nx\n"
    )
    entry = build_repository_index(str(tmp_path)).artifacts[0]
    assert entry.id == "DEC-99"  # not "explicit-id"
    assert entry.type == "decision"
    assert entry.title == "Some Decision"


# --- title + incomplete-but-recognizable ------------------------------------


def test_titleless_but_recognizable_requirement(tmp_path):
    # No H1, but Problem + Requirements → still classifies as a requirement, with
    # a null title (indexed, not dropped to Unknown).
    (tmp_path / "untitled.md").write_text(
        "## Problem\n\nUsers need X.\n\n## Requirements\n\n- [REQ-001] Do X.\n"
    )
    entry = build_repository_index(str(tmp_path)).artifacts[0]
    assert entry.type == "requirement"
    assert entry.title is None
    assert entry.id == "untitled"  # stem fallback


# --- entry shape: exactly id/type/title/path, no status/dates ---------------


def test_entry_dict_keys_are_exact():
    # "aliases" added in v0.7.12 (additive, ADR-007): canonical-first list of
    # every identifier the artifact answers to, for resolver consumers.
    index = build_repository_index(str(ALL_TYPES))
    for e in index.artifacts:
        assert set(e.to_dict()) == {"id", "type", "title", "path", "aliases"}
        assert e.to_dict()["aliases"][0] == e.id


def test_no_status_or_date_fields():
    # Locked v0.7.5 decisions: the index never emits status, created, or updated —
    # even for decisions that declare a ## Status section.
    index = build_repository_index(str(ALL_TYPES))
    for e in index.artifacts:
        d = e.to_dict()
        assert "status" not in d
        assert "created" not in d
        assert "updated" not in d


# --- read only (REQ-004) -----------------------------------------------------


def test_indexing_is_read_only(tmp_path):
    src = tmp_path / "adr-100-foo.md"
    content = "# Foo\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nx\n"
    src.write_text(content)
    before = src.stat().st_mtime_ns
    build_repository_index(str(tmp_path))
    assert src.read_text() == content
    assert src.stat().st_mtime_ns == before


# --- empty repo --------------------------------------------------------------


def test_empty_directory(tmp_path):
    index = build_repository_index(str(tmp_path))
    assert index.artifact_count == 0
    assert index.artifacts == []


# --- recursion control -------------------------------------------------------


def test_top_level_fewer_than_recursive(tmp_path):
    decision = "# {t}\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nx\n"
    (tmp_path / "top.md").write_text(decision.format(t="T"))
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.md").write_text(decision.format(t="N"))
    assert build_repository_index(str(tmp_path), recursive=True).artifact_count == 2
    assert build_repository_index(str(tmp_path), recursive=False).artifact_count == 1


# --- JSON contract (ADR-007) -------------------------------------------------


def test_json_schema_version_and_top_level_keys():
    d = build_repository_index(str(ALL_TYPES)).to_dict()
    assert d["schema_version"] == "1"
    assert set(d) == {
        "schema_version",
        "directory",
        "recursive",
        "artifact_count",
        "artifacts",
    }
    assert d["artifact_count"] == len(d["artifacts"])


# --- performance foundation (Initiative 5) ----------------------------------


def test_scales_to_a_thousand_artifacts(tmp_path):
    for i in range(1000):
        (tmp_path / f"req-{i:04d}.md").write_text(
            f"# R{i}\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] x\n"
        )
    index = build_repository_index(str(tmp_path))
    assert index.artifact_count == 1000
    assert all(e.type == "requirement" for e in index.artifacts)


# --- CLI ---------------------------------------------------------------------


def test_cli_index_exit_0(tmp_path):
    assert main(["index", str(tmp_path)]) == 0


def test_cli_index_no_arg_defaults_to_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert main(["index"]) == 0


def test_cli_index_human_output(capsys):
    rc = main(["index", str(ALL_TYPES)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Repository Index" in out
    assert "Artifacts:  6" in out


def test_cli_index_json_output(capsys):
    rc = main(["index", str(ALL_TYPES), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["artifact_count"] == 6
    assert all(set(e) == {"id", "type", "title", "path", "aliases"} for e in payload["artifacts"])


def test_cli_index_not_a_directory(tmp_path):
    f = tmp_path / "file.md"
    f.write_text("# x")
    with pytest.raises(SystemExit) as exc:
        main(["index", str(f)])
    assert exc.value.code == 2
