"""Skill installation — `rac skill install` (v0.10.5).

``install_skills`` is the reusable installation capability: it owns resource
loading, the never-overwrite check, parent directory creation, and the result
model, so the CLI stays a thin adapter. With no name it installs every bundled
skill all-or-nothing; with a name it installs exactly that skill. The target
layout is the documented Claude Code project-level discovery path:
``<dir>/.claude/skills/<skill-name>/SKILL.md``.

Failure contract:

- unknown skill name      → :class:`~rac.core.skills.SkillNotFound` (usage
  error, exit 2 — mirrors the templates convention)
- existing skill file(s)  → :class:`SkillFileExists` (refused before anything
  is written; every existing file is left untouched — exit 1)
- missing packaged skill  → :class:`~rac.core.skills.SkillResourceMissing`
  (operational; broken installation)

A nonexistent target directory is a usage error the CLI rejects before the
service runs (exit 2), matching every other path-taking command.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rac.core.skills import SkillNotFound, available_skills, load_skill
from rac.errors import RACError


class SkillFileExists(RACError):
    """A target skill file already exists; RAC never overwrites it.

    For a no-name install every existing target is collected and reported
    before anything is written (all-or-nothing).
    """

    def __init__(self, paths: list[str]):
        self.paths = paths
        if len(paths) == 1:
            message = f"{paths[0]} already exists; rac skill install never overwrites"
        else:
            listing = "\n".join(f"  - {p}" for p in paths)
            message = (
                f"{len(paths)} skill files already exist; "
                f"rac skill install never overwrites:\n{listing}"
            )
        super().__init__(message)


@dataclass
class InstalledSkill:
    """One installed skill (stable JSON contract, ADR-007)."""

    skill: str
    path: str
    bytes_written: int

    def to_dict(self) -> dict:
        return {"skill": self.skill, "path": self.path}


@dataclass
class SkillInstallation:
    """Result of a `rac skill install` run (stable JSON contract, ADR-007)."""

    skills: list[InstalledSkill]

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "installed": True,
            "skills": [skill.to_dict() for skill in self.skills],
        }


def install_skills(target_dir: str, skill_name: str | None = None) -> SkillInstallation:
    """Write bundled skills into ``target_dir``'s Claude Code skill path.

    With ``skill_name`` ``None`` every bundled skill is installed,
    all-or-nothing: every target path is checked first, and if any exists the
    whole installation is refused with nothing written. With a name exactly
    that skill is installed. Parent directories are created as needed; an
    existing skill file is never overwritten.

    Raises :class:`~rac.core.skills.SkillNotFound` for an unregistered name,
    :class:`SkillFileExists` when any target file already exists, and
    :class:`~rac.core.skills.SkillResourceMissing` when a packaged resource
    is absent.
    """
    if skill_name is not None and skill_name not in available_skills():
        raise SkillNotFound(skill_name)
    names = available_skills() if skill_name is None else [skill_name]

    # Load every resource first (validates the installation, cheap), then
    # check every target, then write — so a refusal never leaves a partial
    # installation behind.
    contents = {name: load_skill(name) for name in names}
    destinations = {
        name: Path(target_dir) / ".claude" / "skills" / name / "SKILL.md" for name in names
    }
    existing = [str(dest) for dest in destinations.values() if dest.exists()]
    if existing:
        raise SkillFileExists(existing)

    installed: list[InstalledSkill] = []
    for name in names:
        dest = destinations[name]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(contents[name])
        installed.append(
            InstalledSkill(skill=name, path=str(dest), bytes_written=len(contents[name]))
        )
    return SkillInstallation(skills=installed)
