"""Tests for rac.services.create and the `rac new` / `rac templates` CLI (v0.7.10).

Pins the v0.7.10 implementation contract: explicit literal output path, UTF-8
content, never overwrite, no directory auto-creation, and exit codes 0 / 1
(broken installation) / 2 (usage).
"""

from __future__ import annotations

import json

import pytest

from rac.core.artifacts import ARTIFACT_SPECS
from rac.core.templates import TemplateResourceMissing, load_template
from rac.services.create import (
    OutputDirectoryMissing,
    OutputPathExists,
    create_artifact,
    render_artifact,
)
from rac.cli import main

SPEC_NAMES = [spec.name for spec in ARTIFACT_SPECS]


# --- service -----------------------------------------------------------------


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_create_writes_canonical_template(tmp_path, name):
    out = tmp_path / f"{name}.md"
    created = create_artifact(name, str(out))
    assert out.read_text(encoding="utf-8") == load_template(name)
    assert created.artifact_type == name
    assert created.path == str(out)
    assert created.bytes_written == len(out.read_bytes())


def test_create_is_deterministic(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    create_artifact("requirement", str(a))
    create_artifact("requirement", str(b))
    assert a.read_bytes() == b.read_bytes()


def test_create_never_overwrites(tmp_path):
    out = tmp_path / "existing.md"
    out.write_text("precious user content", encoding="utf-8")
    with pytest.raises(OutputPathExists):
        create_artifact("decision", str(out))
    assert out.read_text(encoding="utf-8") == "precious user content"


def test_create_requires_existing_directory(tmp_path):
    with pytest.raises(OutputDirectoryMissing):
        create_artifact("decision", str(tmp_path / "missing" / "out.md"))


def test_render_artifact_prepends_frontmatter_when_given():
    # v0.7.11 seam: an envelope renders before the body without altering it.
    body = load_template("decision")
    assert render_artifact("decision") == body
    assert render_artifact("decision", frontmatter="---\nx: 1\n---\n") == (
        "---\nx: 1\n---\n" + body
    )


def test_created_artifact_json_contract(tmp_path):
    created = create_artifact("roadmap", str(tmp_path / "r.md"))
    assert created.to_dict() == {
        "schema_version": "1",
        "created": True,
        "type": "roadmap",
        "path": str(tmp_path / "r.md"),
    }


# --- CLI: rac new ------------------------------------------------------------


def test_cli_new_creates_artifact(tmp_path, capsys):
    out = tmp_path / "req.md"
    rc = main(["new", "requirement", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8") == load_template("requirement")
    assert "Created requirement artifact" in capsys.readouterr().out


def test_cli_new_json(tmp_path, capsys):
    out = tmp_path / "d.md"
    rc = main(["new", "decision", str(out), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "1",
        "created": True,
        "type": "decision",
        "path": str(out),
    }


def test_cli_new_unsupported_type_exits_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["new", "meeting", str(tmp_path / "m.md")])
    assert exc.value.code == 2
    assert "unsupported artifact type: meeting" in capsys.readouterr().err


def test_cli_new_existing_file_exits_2(tmp_path, capsys):
    out = tmp_path / "x.md"
    out.write_text("keep me", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["new", "requirement", str(out)])
    assert exc.value.code == 2
    assert "never overwrites" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "keep me"


def test_cli_new_missing_directory_exits_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["new", "requirement", str(tmp_path / "nope" / "x.md")])
    assert exc.value.code == 2
    assert "directory does not exist" in capsys.readouterr().err


def test_cli_new_missing_resource_is_operational_error(tmp_path, capsys, monkeypatch):
    def boom(artifact_type, output_path):
        raise TemplateResourceMissing(artifact_type)

    monkeypatch.setattr("rac.cli.create_artifact", boom)
    rc = main(["new", "requirement", str(tmp_path / "x.md")])
    assert rc == 1
    assert "packaged template missing" in capsys.readouterr().err


# --- CLI: rac templates -------------------------------------------------------


def test_cli_templates_lists_registry(capsys):
    rc = main(["templates"])
    assert rc == 0
    out = capsys.readouterr().out
    for name in SPEC_NAMES:
        assert f"- {name}" in out


def test_cli_templates_json_matches_registry(capsys):
    rc = main(["templates", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"schema_version": "1", "templates": SPEC_NAMES}


def test_cli_new_and_service_write_identical_content(tmp_path, capsys):
    cli_out = tmp_path / "cli.md"
    svc_out = tmp_path / "svc.md"
    main(["new", "prompt", str(cli_out)])
    create_artifact("prompt", str(svc_out))
    assert cli_out.read_bytes() == svc_out.read_bytes()
