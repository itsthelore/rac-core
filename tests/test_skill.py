"""Tests for rac.core.skills, rac.services.skill, and the `rac skill` CLI.

Pins the v0.10.5 bundled-skill contract (REQ-005..008 of
rac/requirements/rac-growth-agent-skill.md): every bundled skill ships as a
package resource byte-identical to the repository's dogfood copy under
`.claude/skills/`, `rac skill install` writes all skills (all-or-nothing) or
one by name to the documented Claude Code discovery path without ever
overwriting, `rac skill list` enumerates the bundle, and exit codes follow
the standard convention (0 installed/listed, 1 refused or operational error,
2 bad path or unknown skill name).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rac.cli import main
from rac.core.skills import (
    BUNDLED_SKILLS,
    SkillNotFound,
    SkillResourceMissing,
    available_skills,
    load_skill,
    skill_specs,
)
from rac.services.skill import SkillFileExists, install_skills

REPO_ROOT = Path(__file__).parent.parent
GOLDEN_DIR = Path(__file__).parent / "golden"

SKILL_NAMES = ["rac-artifacts", "rac-review", "rac-ingest", "rac-import", "rac-capture"]


def dogfood_path(name: str) -> Path:
    return REPO_ROOT / ".claude" / "skills" / name / "SKILL.md"


def install_rel_path(name: str) -> Path:
    return Path(".claude") / "skills" / name / "SKILL.md"


# --- registry ----------------------------------------------------------------


def test_registry_lists_the_bundled_skills_in_order():
    assert available_skills() == SKILL_NAMES


def test_every_bundled_skill_has_a_one_line_description():
    for spec in skill_specs():
        assert spec.description, f"{spec.name} has no description"
        assert "\n" not in spec.description


def test_unknown_skill_raises_skill_not_found():
    # Mirrors the templates convention: an unregistered name is a caller
    # error, listing what is available.
    with pytest.raises(SkillNotFound, match="unknown skill: nonexistent"):
        load_skill("nonexistent")
    with pytest.raises(SkillNotFound, match="rac-artifacts, rac-review, rac-ingest"):
        load_skill("nonexistent")


def test_missing_resource_raises_skill_resource_missing(monkeypatch):
    # A registered skill whose packaged resource is absent is a broken
    # installation, not a usage error.
    from rac.core import skills as core_skills

    ghost = core_skills.SkillSpec(name="rac-ghost", description="No resource ships for this.")
    monkeypatch.setattr(core_skills, "BUNDLED_SKILLS", (*BUNDLED_SKILLS, ghost))
    with pytest.raises(SkillResourceMissing, match="packaged skill missing: rac-ghost"):
        core_skills.load_skill("rac-ghost")


# --- content contract (REQ-007 / REQ-008) -------------------------------------


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_packaged_skill_matches_dogfood_copy(name):
    # The dogfood copy and the packaged resource cannot drift: one canonical
    # content, two distribution surfaces, byte-identical — per skill.
    assert load_skill(name) == dogfood_path(name).read_bytes()


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_load_is_deterministic(name):
    assert load_skill(name) == load_skill(name)


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_frontmatter_name_matches_registry(name):
    # The Claude Code frontmatter `name` and the registry name must agree, or
    # discovery and installation would disagree about what was installed.
    text = load_skill(name).decode("utf-8")
    assert text.startswith("---\n")
    assert f"name: {name}\n" in text.split("---", 2)[1]


# --- service: install all (no name) -------------------------------------------


def test_install_all_writes_every_skill(tmp_path):
    installation = install_skills(str(tmp_path))
    assert [s.skill for s in installation.skills] == SKILL_NAMES
    for installed in installation.skills:
        dest = tmp_path / install_rel_path(installed.skill)
        assert dest.read_bytes() == load_skill(installed.skill)
        assert installed.path == str(dest)
        assert installed.bytes_written == len(dest.read_bytes())


def test_install_creates_parent_directories(tmp_path):
    # A fresh project has no .claude/ tree; install creates it.
    assert not (tmp_path / ".claude").exists()
    install_skills(str(tmp_path))
    for name in SKILL_NAMES:
        assert (tmp_path / install_rel_path(name)).is_file()


def test_install_all_refuses_all_or_nothing_when_one_exists(tmp_path):
    # One pre-existing target refuses the whole installation: nothing is
    # written, and the existing file is untouched.
    dest = tmp_path / install_rel_path("rac-review")
    dest.parent.mkdir(parents=True)
    dest.write_text("precious user content", encoding="utf-8")
    with pytest.raises(SkillFileExists) as exc:
        install_skills(str(tmp_path))
    assert exc.value.paths == [str(dest)]
    assert dest.read_text(encoding="utf-8") == "precious user content"
    for name in ("rac-artifacts", "rac-ingest"):
        assert not (tmp_path / install_rel_path(name)).exists()


def test_second_install_all_refused_and_reports_every_path(tmp_path):
    install_skills(str(tmp_path))
    before = {name: (tmp_path / install_rel_path(name)).read_bytes() for name in SKILL_NAMES}
    with pytest.raises(SkillFileExists, match="never overwrites") as exc:
        install_skills(str(tmp_path))
    assert exc.value.paths == [str(tmp_path / install_rel_path(n)) for n in SKILL_NAMES]
    for name in SKILL_NAMES:
        assert (tmp_path / install_rel_path(name)).read_bytes() == before[name]


# --- service: install one (named) ----------------------------------------------


def test_named_install_writes_exactly_one_skill(tmp_path):
    installation = install_skills(str(tmp_path), "rac-review")
    assert [s.skill for s in installation.skills] == ["rac-review"]
    assert (tmp_path / install_rel_path("rac-review")).read_bytes() == load_skill("rac-review")
    for name in ("rac-artifacts", "rac-ingest"):
        assert not (tmp_path / install_rel_path(name)).exists()


def test_named_install_never_overwrites(tmp_path):
    dest = tmp_path / install_rel_path("rac-ingest")
    dest.parent.mkdir(parents=True)
    dest.write_text("precious user content", encoding="utf-8")
    with pytest.raises(SkillFileExists, match="never overwrites"):
        install_skills(str(tmp_path), "rac-ingest")
    assert dest.read_text(encoding="utf-8") == "precious user content"


def test_named_install_unknown_skill_raises(tmp_path):
    with pytest.raises(SkillNotFound, match="unknown skill: rac-nope"):
        install_skills(str(tmp_path), "rac-nope")
    assert not (tmp_path / ".claude").exists()


def test_installation_json_contract(tmp_path):
    installation = install_skills(str(tmp_path))
    assert installation.to_dict() == {
        "schema_version": "1",
        "installed": True,
        "skills": [
            {"skill": name, "path": str(tmp_path / install_rel_path(name))} for name in SKILL_NAMES
        ],
    }


# --- CLI: rac skill install ----------------------------------------------------


def test_cli_skill_install_creates_all_files(tmp_path, capsys):
    rc = main(["skill", "install", "--dir", str(tmp_path)])
    assert rc == 0
    for name in SKILL_NAMES:
        assert (tmp_path / install_rel_path(name)).read_bytes() == load_skill(name)
    stdout = capsys.readouterr().out
    for name in SKILL_NAMES:
        assert f"Installed {name} skill" in stdout


def test_cli_skill_install_defaults_to_current_directory(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["skill", "install"])
    assert rc == 0
    for name in SKILL_NAMES:
        assert (tmp_path / install_rel_path(name)).is_file()


def test_cli_skill_install_json(tmp_path, capsys):
    rc = main(["skill", "install", "--dir", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "1",
        "installed": True,
        "skills": [
            {"skill": name, "path": str(tmp_path / install_rel_path(name))} for name in SKILL_NAMES
        ],
    }


def test_cli_second_install_exits_1_and_leaves_files_untouched(tmp_path, capsys):
    assert main(["skill", "install", "--dir", str(tmp_path)]) == 0
    before = {name: (tmp_path / install_rel_path(name)).read_bytes() for name in SKILL_NAMES}
    rc = main(["skill", "install", "--dir", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "never overwrites" in err
    for name in SKILL_NAMES:
        assert str(tmp_path / install_rel_path(name)) in err
        assert (tmp_path / install_rel_path(name)).read_bytes() == before[name]


def test_cli_named_install_creates_exactly_one_file(tmp_path, capsys):
    rc = main(["skill", "install", "rac-review", "--dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / install_rel_path("rac-review")).read_bytes() == load_skill("rac-review")
    for name in ("rac-artifacts", "rac-ingest"):
        assert not (tmp_path / install_rel_path(name)).exists()
    assert "Installed rac-review skill" in capsys.readouterr().out


def test_cli_unknown_skill_name_exits_2_and_lists_available(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["skill", "install", "rac-nope", "--dir", str(tmp_path)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "unknown skill: rac-nope" in err
    assert "rac-artifacts, rac-review, rac-ingest" in err
    assert not (tmp_path / ".claude").exists()


def test_cli_skill_install_bad_dir_exits_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["skill", "install", "--dir", str(tmp_path / "nope")])
    assert exc.value.code == 2
    assert "not a directory" in capsys.readouterr().err


def test_cli_skill_install_missing_resource_is_operational_error(tmp_path, capsys, monkeypatch):
    def boom(target_dir, skill_name=None):
        raise SkillResourceMissing("rac-artifacts")

    monkeypatch.setattr("rac.cli.install_skills", boom)
    rc = main(["skill", "install", "--dir", str(tmp_path)])
    assert rc == 1
    assert "packaged skill missing" in capsys.readouterr().err


# --- CLI: rac skill list ---------------------------------------------------------


def test_cli_skill_list_human(capsys):
    rc = main(["skill", "list"])
    assert rc == 0
    stdout = capsys.readouterr().out
    for spec in skill_specs():
        assert spec.name in stdout
        assert spec.description in stdout


def test_cli_skill_list_json(capsys):
    rc = main(["skill", "list", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "1",
        "skills": [{"skill": spec.name, "description": spec.description} for spec in skill_specs()],
    }


def test_cli_skill_list_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["skill", "list"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_cli_skill_list_rejects_a_skill_name(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["skill", "list", "rac-review"])
    assert exc.value.code == 2
    assert "takes no skill name" in capsys.readouterr().err


# --- golden output -------------------------------------------------------------

# Same golden mechanism as tests/test_golden.py (byte-for-byte stdout pins,
# refreshed with RAC_UPDATE_GOLDEN=1), but run from a tmp directory: `skill
# install` writes files, so it cannot run against the repository root like
# the read-only golden cases. With the default --dir the reported paths are
# relative, so the output stays machine-independent.
GOLDEN_CASES = [
    ("skill_install_human", ["skill", "install"], 0),
    ("skill_install_json", ["skill", "install", "--json"], 0),
    ("skill_install_named_human", ["skill", "install", "rac-review"], 0),
    ("skill_install_named_json", ["skill", "install", "rac-review", "--json"], 0),
    ("skill_list_human", ["skill", "list"], 0),
    ("skill_list_json", ["skill", "list", "--json"], 0),
]


@pytest.mark.parametrize("name,argv,expected_rc", GOLDEN_CASES, ids=[c[0] for c in GOLDEN_CASES])
def test_skill_golden(name, argv, expected_rc, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Force plain output: golden files must not depend on whether the test
    # runner happens to attach a TTY.
    monkeypatch.setattr("rac.output.human._USE_COLOR", False)

    rc = main(argv)
    out = capsys.readouterr().out

    golden = GOLDEN_DIR / f"{name}.txt"
    if os.environ.get("RAC_UPDATE_GOLDEN") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(out, encoding="utf-8")

    assert rc == expected_rc
    assert out == golden.read_text(encoding="utf-8"), (
        f"Output of `rac {' '.join(argv)}` drifted from {golden}.\n"
        "If the change is intentional, refresh with: "
        "RAC_UPDATE_GOLDEN=1 python -m pytest tests/test_skill.py"
    )
