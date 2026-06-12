"""Tests for rac.core.skills, rac.services.skill, and the `rac skill` CLI.

Pins the v0.10.4 bundled-skill contract (REQ-005..007 of
rac/requirements/rac-growth-agent-skill.md): the skill ships as a package
resource byte-identical to the repository's dogfood copy under
`.claude/skills/`, `rac skill install` writes it to the documented Claude
Code discovery path without ever overwriting, and exit codes follow the
standard convention (0 installed, 1 refused or operational error, 2 bad
path).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rac.cli import main
from rac.core.skills import SkillResourceMissing, available_skills, load_skill
from rac.services.skill import SKILL_NAME, SkillFileExists, install_skill

REPO_ROOT = Path(__file__).parent.parent
GOLDEN_DIR = Path(__file__).parent / "golden"

DOGFOOD_SKILL = REPO_ROOT / ".claude" / "skills" / "rac-artifacts" / "SKILL.md"
INSTALL_REL_PATH = Path(".claude") / "skills" / "rac-artifacts" / "SKILL.md"


# --- registry ----------------------------------------------------------------


def test_registry_lists_the_one_bundled_skill():
    # One bundled skill (v0.10.4): the skill-name CLI argument is introduced
    # only when a second skill exists.
    assert available_skills() == ["rac-artifacts"]
    assert SKILL_NAME == "rac-artifacts"


def test_missing_resource_raises_skill_resource_missing():
    with pytest.raises(SkillResourceMissing, match="packaged skill missing: nonexistent"):
        load_skill("nonexistent")


# --- content contract (REQ-007) ------------------------------------------------


def test_packaged_skill_matches_dogfood_copy():
    # The dogfood copy and the packaged resource cannot drift: one canonical
    # content, two distribution surfaces, byte-identical (REQ-007).
    assert load_skill("rac-artifacts") == DOGFOOD_SKILL.read_bytes()


def test_skill_load_is_deterministic():
    assert load_skill("rac-artifacts") == load_skill("rac-artifacts")


# --- service -----------------------------------------------------------------


def test_install_writes_skill_to_discovery_path(tmp_path):
    installed = install_skill(str(tmp_path))
    dest = tmp_path / INSTALL_REL_PATH
    assert dest.read_bytes() == load_skill("rac-artifacts")
    assert installed.skill == "rac-artifacts"
    assert installed.path == str(dest)
    assert installed.bytes_written == len(dest.read_bytes())


def test_install_creates_parent_directories(tmp_path):
    # A fresh project has no .claude/ tree; install creates it.
    assert not (tmp_path / ".claude").exists()
    install_skill(str(tmp_path))
    assert (tmp_path / INSTALL_REL_PATH).is_file()


def test_install_never_overwrites(tmp_path):
    dest = tmp_path / INSTALL_REL_PATH
    dest.parent.mkdir(parents=True)
    dest.write_text("precious user content", encoding="utf-8")
    with pytest.raises(SkillFileExists):
        install_skill(str(tmp_path))
    assert dest.read_text(encoding="utf-8") == "precious user content"


def test_second_install_refused_and_file_untouched(tmp_path):
    install_skill(str(tmp_path))
    dest = tmp_path / INSTALL_REL_PATH
    before = dest.read_bytes()
    with pytest.raises(SkillFileExists, match="never overwrites"):
        install_skill(str(tmp_path))
    assert dest.read_bytes() == before


def test_installed_skill_json_contract(tmp_path):
    installed = install_skill(str(tmp_path))
    assert installed.to_dict() == {
        "schema_version": "1",
        "installed": True,
        "skill": "rac-artifacts",
        "path": str(tmp_path / INSTALL_REL_PATH),
    }


# --- CLI: rac skill install ----------------------------------------------------


def test_cli_skill_install_creates_file(tmp_path, capsys):
    rc = main(["skill", "install", "--dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / INSTALL_REL_PATH).read_bytes() == load_skill("rac-artifacts")
    stdout = capsys.readouterr().out
    assert "Installed rac-artifacts skill" in stdout


def test_cli_skill_install_defaults_to_current_directory(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["skill", "install"])
    assert rc == 0
    assert (tmp_path / INSTALL_REL_PATH).is_file()


def test_cli_skill_install_json(tmp_path, capsys):
    rc = main(["skill", "install", "--dir", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "1",
        "installed": True,
        "skill": "rac-artifacts",
        "path": str(tmp_path / INSTALL_REL_PATH),
    }


def test_cli_second_install_exits_1_and_leaves_file_untouched(tmp_path, capsys):
    assert main(["skill", "install", "--dir", str(tmp_path)]) == 0
    dest = tmp_path / INSTALL_REL_PATH
    before = dest.read_bytes()
    rc = main(["skill", "install", "--dir", str(tmp_path)])
    assert rc == 1
    assert "never overwrites" in capsys.readouterr().err
    assert dest.read_bytes() == before


def test_cli_skill_install_bad_dir_exits_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["skill", "install", "--dir", str(tmp_path / "nope")])
    assert exc.value.code == 2
    assert "not a directory" in capsys.readouterr().err


def test_cli_skill_install_missing_resource_is_operational_error(tmp_path, capsys, monkeypatch):
    def boom(target_dir):
        raise SkillResourceMissing("rac-artifacts")

    monkeypatch.setattr("rac.cli.install_skill", boom)
    rc = main(["skill", "install", "--dir", str(tmp_path)])
    assert rc == 1
    assert "packaged skill missing" in capsys.readouterr().err


# --- golden output -------------------------------------------------------------

# Same golden mechanism as tests/test_golden.py (byte-for-byte stdout pins,
# refreshed with RAC_UPDATE_GOLDEN=1), but run from a tmp directory: `skill
# install` writes a file, so it cannot run against the repository root like
# the read-only golden cases. With the default --dir the reported path is
# relative, so the output stays machine-independent.
GOLDEN_CASES = [
    ("skill_install_human", ["skill", "install"], 0),
    ("skill_install_json", ["skill", "install", "--json"], 0),
]


@pytest.mark.parametrize("name,argv,expected_rc", GOLDEN_CASES, ids=[c[0] for c in GOLDEN_CASES])
def test_skill_install_golden(name, argv, expected_rc, capsys, monkeypatch, tmp_path):
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
