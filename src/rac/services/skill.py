"""Skill installation — `rac skill install` (v0.10.5).

:func:`install_skills` is the reusable capability behind the CLI adapter: it
owns resource loading, the never-overwrite refusal, parent-directory creation,
and the result model. With no name it installs every bundled skill
all-or-nothing; with a name it installs exactly that one. Skills land at the
documented Claude Code project discovery path,
``<dir>/.claude/skills/<name>/SKILL.md``.

Failure contract:

- unknown skill name      → :class:`~rac.core.skills.SkillNotFound` (usage
  error, exit 2 — mirrors the templates convention)
- existing skill file(s)  → :class:`SkillFileExists` (refused before any write;
  every existing file is left untouched — exit 1)
- missing packaged skill  → :class:`~rac.core.skills.SkillResourceMissing`
  (operational; a broken installation)

A nonexistent target directory is a usage error the CLI rejects before this
service runs (exit 2), matching every other path-taking command.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rac.core.skills import SkillNotFound, available_skills, load_skill
from rac.errors import RACError


class SkillFileExists(RACError):
    """One or more target skill files already exist; RAC never overwrites.

    A no-name install collects every existing target and reports them all
    before anything is written, so the refusal is all-or-nothing.
    """

    def __init__(self, paths: list[str]):
        # ``.paths`` is part of the contract: callers (and tests) read the full
        # refused set, and the message differs for one path vs. many.
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
        # bytes_written is tracked for callers but deliberately absent from the
        # JSON shape (pinned by test_installation_json_contract).
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

    With ``skill_name`` ``None`` every bundled skill is installed
    all-or-nothing; with a name, exactly that skill. Parent directories are
    created as needed and an existing skill file is never overwritten.

    Raises :class:`~rac.core.skills.SkillNotFound` for an unregistered name,
    :class:`SkillFileExists` when any target already exists, and
    :class:`~rac.core.skills.SkillResourceMissing` when a packaged resource is
    absent.
    """
    if skill_name is not None and skill_name not in available_skills():
        raise SkillNotFound(skill_name)
    names = available_skills() if skill_name is None else [skill_name]

    skills_root = Path(target_dir) / ".claude" / "skills"
    destinations = {name: skills_root / name / "SKILL.md" for name in names}

    # Load every resource and check every destination before writing anything:
    # a refusal (existing file) or a broken install (missing resource) must
    # never leave a partial installation behind. The mapping is in registry
    # order, which is the order the refused-path list is reported in.
    contents = {name: load_skill(name) for name in names}
    existing = [str(dest) for dest in destinations.values() if dest.exists()]
    if existing:
        raise SkillFileExists(existing)

    installed: list[InstalledSkill] = []
    for name, dest in destinations.items():
        content = contents[name]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        installed.append(InstalledSkill(skill=name, path=str(dest), bytes_written=len(content)))
    return SkillInstallation(skills=installed)
