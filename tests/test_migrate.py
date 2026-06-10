"""Tests for rac.services.migrate and `rac migrate metadata` (v0.7.13).

Pins the migration contract: idempotent, byte-preserving, unknown documents
reported not guessed, dry runs write nothing, repaired documents picked up by
the next run, and exit codes 0/1/2.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.core.markdown import parse_file
from rac.core.validation import has_errors, validate
from rac.services.create import MissingRepositoryConfig, create_artifact
from rac.services.init import init_repository
from rac.services.migrate import (
    STATUS_ALREADY_CANONICAL,
    STATUS_MIGRATED,
    STATUS_SKIPPED_UNKNOWN,
    migrate_metadata,
)
from rac.services.resolve import OUTCOME_RESOLVED, resolve_artifact

LEGACY_DECISION = """# A Legacy Decision

## Context

c

## Decision

d

## Consequences

q
"""

UNKNOWN_DOC = "# Not An Artifact\n\nJust prose.\n"


@pytest.fixture
def repo(tmp_path):
    init_repository(str(tmp_path), key="RAC")
    (tmp_path / "adr-001-legacy.md").write_text(LEGACY_DECISION, encoding="utf-8")
    (tmp_path / "notes.md").write_text(UNKNOWN_DOC, encoding="utf-8")
    return tmp_path


# --- service -----------------------------------------------------------------


def test_migrates_recognized_legacy_artifact(repo):
    report = migrate_metadata(str(repo))
    statuses = {f.path.split("/")[-1]: f.status for f in report.files}
    assert statuses["adr-001-legacy.md"] == STATUS_MIGRATED
    assert statuses["notes.md"] == STATUS_SKIPPED_UNKNOWN
    migrated = next(f for f in report.files if f.status == STATUS_MIGRATED)
    assert migrated.id.startswith("RAC-")
    assert migrated.type == "decision"


def test_migrated_artifact_validates_and_resolves(repo):
    report = migrate_metadata(str(repo))
    migrated = next(f for f in report.files if f.status == STATUS_MIGRATED)
    product = parse_file(migrated.path)
    assert product.metadata.id == migrated.id
    assert not has_errors(validate(product))
    # Canonical ID and legacy alias both resolve to the migrated artifact.
    assert resolve_artifact(str(repo), migrated.id).outcome == OUTCOME_RESOLVED
    assert resolve_artifact(str(repo), "adr-001").outcome == OUTCOME_RESOLVED


def test_body_preserved_byte_for_byte(repo):
    before = (repo / "adr-001-legacy.md").read_bytes()
    migrate_metadata(str(repo))
    after = (repo / "adr-001-legacy.md").read_bytes()
    assert after.endswith(before)
    assert after != before  # envelope was prepended


def test_rerun_is_idempotent(repo):
    migrate_metadata(str(repo))
    first = (repo / "adr-001-legacy.md").read_bytes()
    report = migrate_metadata(str(repo))
    assert (repo / "adr-001-legacy.md").read_bytes() == first
    assert report.migrated == 0
    assert report.already_canonical == 1
    assert report.skipped_unknown == 1


def test_repaired_document_picked_up_by_next_run(repo):
    migrate_metadata(str(repo))
    # The user repairs the unknown document so it classifies.
    (repo / "notes.md").write_text(LEGACY_DECISION, encoding="utf-8")
    report = migrate_metadata(str(repo))
    statuses = {f.path.split("/")[-1]: f.status for f in report.files}
    assert statuses["notes.md"] == STATUS_MIGRATED


def test_dry_run_writes_nothing(repo):
    before = (repo / "adr-001-legacy.md").read_bytes()
    report = migrate_metadata(str(repo), dry_run=True)
    assert (repo / "adr-001-legacy.md").read_bytes() == before
    assert report.dry_run
    assert report.migrated == 1  # reported, not written


def test_malformed_frontmatter_left_alone(repo):
    broken = repo / "broken.md"
    broken.write_text("---\nschema_version: [oops\n---\n" + LEGACY_DECISION)
    before = broken.read_bytes()
    report = migrate_metadata(str(repo))
    assert broken.read_bytes() == before
    statuses = {f.path.split("/")[-1]: f.status for f in report.files}
    assert statuses["broken.md"] == STATUS_ALREADY_CANONICAL


def test_generated_ids_unique_within_run(repo):
    for i in range(10):
        (repo / f"adr-{i:03d}-x.md").write_text(LEGACY_DECISION, encoding="utf-8")
    report = migrate_metadata(str(repo))
    ids = [f.id for f in report.files if f.status == STATUS_MIGRATED]
    assert len(ids) == len(set(ids)) == 11


def test_ids_do_not_collide_with_existing_artifacts(repo):
    created = create_artifact(
        "decision",
        str(repo / "existing.md"),
        id_generator=lambda key: f"{key}-01JY4M8X2QZ7",
    )
    report = migrate_metadata(str(repo))
    migrated_ids = {f.id for f in report.files if f.status == STATUS_MIGRATED}
    assert created.id not in migrated_ids


def test_requires_init(tmp_path):
    (tmp_path / "adr-001-x.md").write_text(LEGACY_DECISION, encoding="utf-8")
    with pytest.raises(MissingRepositoryConfig):
        migrate_metadata(str(tmp_path))


def test_report_json_contract(repo):
    payload = migrate_metadata(str(repo)).to_dict()
    assert payload["schema_version"] == "1"
    assert payload["dry_run"] is False
    assert payload["summary"] == {
        "total_files": 2,
        "migrated": 1,
        "already_canonical": 0,
        "skipped_unknown": 1,
    }
    assert {f["status"] for f in payload["files"]} == {
        STATUS_MIGRATED,
        STATUS_SKIPPED_UNKNOWN,
    }
    unknown = next(f for f in payload["files"] if f["status"] == STATUS_SKIPPED_UNKNOWN)
    assert unknown["id"] is None and unknown["type"] is None


# --- CLI ----------------------------------------------------------------------


def test_cli_migrate_human(repo, capsys):
    rc = main(["migrate", "metadata", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Migrated 1 artifact(s):" in out
    assert "RAC-" in out
    assert "notes.md" in out  # unknown paths are listed
    assert "1 skipped (unknown type)" in out


def test_cli_migrate_dry_run_marked(repo, capsys):
    rc = main(["migrate", "metadata", str(repo), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Dry run — no files were written." in out
    assert "Would migrate 1 artifact(s):" in out


def test_cli_migrate_json(repo, capsys):
    rc = main(["migrate", "metadata", str(repo), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["summary"]["migrated"] == 1


def test_cli_migrate_nothing_to_do_exit_0(repo, capsys):
    main(["migrate", "metadata", str(repo)])
    capsys.readouterr()
    rc = main(["migrate", "metadata", str(repo)])
    assert rc == 0
    assert "nothing to migrate" in capsys.readouterr().out


def test_cli_migrate_without_init_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["migrate", "metadata", str(tmp_path)])
    assert exc.value.code == 2
    assert "run `rac init`" in capsys.readouterr().err


def test_cli_migrate_not_a_directory_exit_2(repo, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["migrate", "metadata", str(repo / "nope")])
    assert exc.value.code == 2


def test_cli_migrate_unknown_target_exit_2(repo):
    with pytest.raises(SystemExit) as exc:
        main(["migrate", "relationships", str(repo)])
    assert exc.value.code == 2
