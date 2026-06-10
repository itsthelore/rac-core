"""Tests for schema reference (`rac schema`, v0.5.2)."""

from __future__ import annotations

import io
import json

import pytest

from rac.core.artifacts import spec_for
from rac.cli import main
from rac.core.schema import available_schemas, schema_reference

from conftest import fixture_path


def test_available_schemas_are_registered_artifacts():
    assert available_schemas() == [
        "requirement",
        "decision",
        "roadmap",
        "prompt",
        "design",
    ]


def test_schema_reference_consumes_artifact_spec():
    spec = spec_for("requirement")
    assert spec is not None
    ref = schema_reference("requirement")
    assert ref is not None
    assert ref.required == list(spec.required)
    assert ref.recommended == list(spec.recommended)
    assert ref.descriptions["problem"] == spec.descriptions["problem"]
    assert ref.guidance["risks"] == list(spec.guidance["risks"])


def test_schema_list_human(capsys):
    rc = main(["schema", "--list"])
    assert rc == 0
    assert capsys.readouterr().out == (
        "Available Schemas:\n"
        "- requirement\n"
        "- decision\n"
        "- roadmap\n"
        "- prompt\n"
        "- design\n"
    )


def test_schema_list_json(capsys):
    rc = main(["schema", "--list", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schemas": ["requirement", "decision", "roadmap", "prompt", "design"]
    }


def test_schema_human_requirement(capsys):
    rc = main(["schema", "requirement"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Requirement" in out
    assert "Required Sections:" in out
    assert "Problem" in out
    assert "Recommended Sections:" in out
    assert "Success Metrics" in out
    assert "Guidance:" in out
    assert "What user or business problem does this solve?" in out
    assert "Optional Sections:" in out
    # v0.7.0: requirements now declare relationship sections as optional.
    assert "Related Decisions" in out
    assert "Decision artifacts this artifact references" in out


def test_schema_human_decision_includes_metadata(capsys):
    rc = main(["schema", "decision"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Decision" in out
    assert "Optional Sections:" in out
    assert "Supersedes" in out
    assert "Metadata Fields:" in out
    assert "Status: Proposed | Accepted | Superseded | Deprecated" in out
    assert "Category: Architecture | Product | Process | Technical | Other" in out


def test_schema_json_requirement_shape(capsys):
    rc = main(["schema", "requirement", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "type",
        "required",
        "recommended",
        "optional",
        "descriptions",
        "guidance",
        "metadata",
    }
    assert payload["type"] == "requirement"
    assert payload["required"] == ["problem", "requirements"]
    assert payload["recommended"] == ["success_metrics", "risks", "assumptions"]
    assert payload["optional"] == [
        "related_decisions",
        "related_roadmaps",
        "related_prompts",
        "related_designs",
        "related_requirements",
    ]
    assert "success_metrics" in payload["descriptions"]
    assert "success_metrics" in payload["guidance"]
    assert payload["metadata"] == {}


def test_schema_json_decision_metadata_values(capsys):
    rc = main(["schema", "decision", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "decision"
    assert payload["optional"] == [
        "supersedes",
        "related_requirements",
        "related_roadmaps",
        "related_designs",
    ]
    assert payload["metadata"]["status"] == [
        "Proposed",
        "Accepted",
        "Superseded",
        "Deprecated",
    ]
    assert payload["metadata"]["category"] == [
        "Architecture",
        "Product",
        "Process",
        "Technical",
        "Other",
    ]


def test_requirement_template_is_validation_safe(capsys, monkeypatch):
    rc = main(["schema", "requirement", "--template"])
    assert rc == 0
    template = capsys.readouterr().out
    assert "# Title" in template
    assert "## Problem" in template
    assert "- [REQ-001] TODO: describe a required system behaviour." in template
    assert "<!-- What must the system do? -->" in template
    assert "## Assumptions" in template

    monkeypatch.setattr("sys.stdin", io.StringIO(template))
    assert main(["validate", "-"]) == 0


def test_decision_template_is_validation_safe(capsys, monkeypatch):
    rc = main(["schema", "decision", "--template"])
    assert rc == 0
    template = capsys.readouterr().out
    assert "## Status" in template
    assert "\nProposed\n" in template
    assert "<!-- Choose one: Proposed | Accepted | Superseded | Deprecated -->" in template
    assert "## Category" in template
    assert "\nOther\n" in template
    assert "<!-- Choose one: Architecture | Product | Process | Technical | Other -->" in template
    assert "## Supersedes" not in template

    monkeypatch.setattr("sys.stdin", io.StringIO(template))
    assert main(["validate", "-"]) == 0


def test_unknown_schema_exits_two_and_lists_available(capsys):
    # "meeting" is a deferred type with no concrete schema yet (see rac/artifacts.py).
    with pytest.raises(SystemExit) as exc:
        main(["schema", "meeting"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "Unknown schema: meeting" in err
    assert "Available schemas:" in err
    assert "- requirement" in err
    assert "- decision" in err
    assert "- roadmap" in err
    assert "- prompt" in err
    assert "- design" in err


def test_schema_requires_name_or_list(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["schema"])
    assert exc.value.code == 2
    assert "schema name required" in capsys.readouterr().err


def test_schema_rejects_template_with_list(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["schema", "--list", "--template"])
    assert exc.value.code == 2
    assert "--template cannot be used with --list" in capsys.readouterr().err


def test_schema_json_and_template_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        main(["schema", "requirement", "--json", "--template"])


def test_validate_stdin_matches_file(monkeypatch, capsys):
    with open(fixture_path("valid", "feature.md"), encoding="utf-8") as fh:
        text = fh.read()

    file_rc = main(["validate", fixture_path("valid", "feature.md"), "--json"])
    file_payload = json.loads(capsys.readouterr().out)

    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    stdin_rc = main(["validate", "-", "--json"])
    stdin_payload = json.loads(capsys.readouterr().out)

    assert stdin_rc == file_rc == 0
    file_payload["file"] = "-"
    assert stdin_payload == file_payload


def test_validate_stdin_invalid_returns_one(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("# Bad\n\n## Problem\n\nx\n"))
    rc = main(["validate", "-"])
    assert rc == 1
    assert "missing-requirements" in capsys.readouterr().out
