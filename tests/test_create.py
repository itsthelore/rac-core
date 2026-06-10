"""Tests for rac.services.create and the `rac new` / `rac templates` CLI.

Pins the v0.7.10 creation contract (explicit literal output path, UTF-8
content, never overwrite, no directory auto-creation, exit codes 0/1/2) and
the v0.7.11 identity integration: every generated artifact carries canonical
frontmatter with a system-assigned ID, and creation without `rac init` fails
with an actionable usage error.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.core.artifacts import ARTIFACT_SPECS
from rac.core.classification import classify
from rac.core.markdown import parse
from rac.core.templates import TemplateResourceMissing, load_template
from rac.core.validation import has_errors, validate
from rac.services.create import (
    IdGenerationExhausted,
    MissingRepositoryConfig,
    OutputDirectoryMissing,
    OutputPathExists,
    create_artifact,
    render_artifact,
    render_frontmatter,
)
from rac.services.init import init_repository

SPEC_NAMES = [spec.name for spec in ARTIFACT_SPECS]

# Deterministic generator for tests: a fixed, syntactically canonical suffix.
FIXED_SUFFIX = "01JY4M8X2QZ7"


def fixed_generator(repository_key: str) -> str:
    return f"{repository_key}-{FIXED_SUFFIX}"


@pytest.fixture
def repo(tmp_path):
    """An initialized repository root."""
    init_repository(str(tmp_path), key="RAC")
    return tmp_path


# --- service -----------------------------------------------------------------


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_create_writes_frontmatter_and_canonical_template(repo, name):
    out = repo / f"{name}.md"
    created = create_artifact(name, str(out), id_generator=fixed_generator)
    expected = render_frontmatter(f"RAC-{FIXED_SUFFIX}", name) + load_template(name)
    assert out.read_text(encoding="utf-8") == expected
    assert created.artifact_type == name
    assert created.path == str(out)
    assert created.id == f"RAC-{FIXED_SUFFIX}"
    assert created.bytes_written == len(out.read_bytes())


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_created_artifact_classifies_and_validates(repo, name):
    out = repo / f"{name}.md"
    create_artifact(name, str(out), id_generator=fixed_generator)
    product = parse(out.read_text(encoding="utf-8"))
    assert classify(product).type == name
    assert not has_errors(validate(product))
    assert product.metadata is not None
    assert product.metadata.id == f"RAC-{FIXED_SUFFIX}"


def test_create_is_deterministic_apart_from_id(repo):
    a = repo / "a.md"
    b = repo / "b.md"
    create_artifact("requirement", str(a), id_generator=fixed_generator)
    init_repository(str(repo))  # already initialized; just being explicit
    # Second create with the same injected generator collides with a's ID in
    # the index, so use a different fixed ID and compare bodies.
    create_artifact("requirement", str(b), id_generator=lambda key: f"{key}-01JY4M8X2QZ8")

    def strip(text: str) -> str:
        return text.split("---\n", 2)[2]

    assert strip(a.read_text(encoding="utf-8")) == strip(b.read_text(encoding="utf-8"))


def test_create_regenerates_on_id_collision(repo):
    existing = repo / "existing.md"
    create_artifact("decision", str(existing), id_generator=fixed_generator)
    ids = iter([f"RAC-{FIXED_SUFFIX}", "RAC-01JY4M8X2QZ9"])
    created = create_artifact("decision", str(repo / "next.md"), id_generator=lambda key: next(ids))
    assert created.id == "RAC-01JY4M8X2QZ9"


def test_create_exhausts_bounded_retries_on_persistent_collision(repo):
    create_artifact("decision", str(repo / "x.md"), id_generator=fixed_generator)
    with pytest.raises(IdGenerationExhausted):
        create_artifact("decision", str(repo / "y.md"), id_generator=fixed_generator)


def test_create_uses_repository_key_from_config(tmp_path):
    init_repository(str(tmp_path), key="PROJ")
    created = create_artifact("decision", str(tmp_path / "d.md"), id_generator=fixed_generator)
    assert created.id == f"PROJ-{FIXED_SUFFIX}"


def test_create_discovers_config_upward(repo):
    nested = repo / "docs" / "decisions"
    nested.mkdir(parents=True)
    created = create_artifact("decision", str(nested / "d.md"), id_generator=fixed_generator)
    assert created.id == f"RAC-{FIXED_SUFFIX}"


def test_create_without_init_fails(tmp_path):
    with pytest.raises(MissingRepositoryConfig):
        create_artifact("decision", str(tmp_path / "d.md"))


def test_create_never_overwrites(repo):
    out = repo / "existing.md"
    out.write_text("precious user content", encoding="utf-8")
    with pytest.raises(OutputPathExists):
        create_artifact("decision", str(out))
    assert out.read_text(encoding="utf-8") == "precious user content"


def test_create_requires_existing_directory(repo):
    with pytest.raises(OutputDirectoryMissing):
        create_artifact("decision", str(repo / "missing" / "out.md"))


def test_render_artifact_prepends_frontmatter_when_given():
    body = load_template("decision")
    assert render_artifact("decision") == body
    assert render_artifact("decision", frontmatter="---\nx: 1\n---\n") == (
        "---\nx: 1\n---\n" + body
    )


def test_render_frontmatter_stable_key_order():
    assert render_frontmatter("RAC-01JY4M8X2QZ7", "decision") == (
        "---\nschema_version: 1\nid: RAC-01JY4M8X2QZ7\ntype: decision\n---\n"
    )


def test_created_artifact_json_contract(repo):
    created = create_artifact("roadmap", str(repo / "r.md"), id_generator=fixed_generator)
    assert created.to_dict() == {
        "schema_version": "1",
        "created": True,
        "type": "roadmap",
        "path": str(repo / "r.md"),
        "id": f"RAC-{FIXED_SUFFIX}",
    }


# --- CLI: rac new ------------------------------------------------------------


def test_cli_new_creates_artifact(repo, capsys):
    out = repo / "req.md"
    rc = main(["new", "requirement", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("---\nschema_version: 1\nid: RAC-")
    assert text.endswith(load_template("requirement"))
    stdout = capsys.readouterr().out
    assert "Created requirement artifact" in stdout
    assert "ID: RAC-" in stdout


def test_cli_new_json(repo, capsys):
    out = repo / "d.md"
    rc = main(["new", "decision", str(out), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["created"] is True
    assert payload["type"] == "decision"
    assert payload["path"] == str(out)
    assert payload["id"].startswith("RAC-")


def test_cli_new_without_init_exits_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["new", "decision", str(tmp_path / "d.md")])
    assert exc.value.code == 2
    assert "run `rac init`" in capsys.readouterr().err


def test_cli_new_unsupported_type_exits_2(repo, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["new", "meeting", str(repo / "m.md")])
    assert exc.value.code == 2
    assert "unsupported artifact type: meeting" in capsys.readouterr().err


def test_cli_new_existing_file_exits_2(repo, capsys):
    out = repo / "x.md"
    out.write_text("keep me", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["new", "requirement", str(out)])
    assert exc.value.code == 2
    assert "never overwrites" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "keep me"


def test_cli_new_missing_directory_exits_2(repo, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["new", "requirement", str(repo / "nope" / "x.md")])
    assert exc.value.code == 2
    assert "directory does not exist" in capsys.readouterr().err


def test_cli_new_missing_resource_is_operational_error(repo, capsys, monkeypatch):
    def boom(artifact_type, output_path):
        raise TemplateResourceMissing(artifact_type)

    monkeypatch.setattr("rac.cli.create_artifact", boom)
    rc = main(["new", "requirement", str(repo / "x.md")])
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


def test_cli_new_and_service_write_identical_bodies(repo, capsys):
    cli_out = repo / "cli.md"
    svc_out = repo / "svc.md"
    main(["new", "prompt", str(cli_out)])
    create_artifact("prompt", str(svc_out), id_generator=fixed_generator)

    def strip(text: str) -> str:
        return text.split("---\n", 2)[2]

    assert strip(cli_out.read_text(encoding="utf-8")) == strip(svc_out.read_text(encoding="utf-8"))
