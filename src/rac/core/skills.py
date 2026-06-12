"""Bundled agent skill registry — `rac skill` (v0.10.5).

The bundled skill set is a static registry of named skills with one-line
descriptions, surfaced by `rac skill list` and installable by name. Skill
content ships as package resources under :mod:`rac.skills` and is loaded with
``importlib.resources``, mirroring how canonical templates ship under
:mod:`rac.templates` (ADR-021), so installation works from an installed wheel
without the dogfood repository and without AI or network access.

Two failure modes are deliberately distinct, mirroring
:mod:`rac.core.templates`: an *unregistered skill name* is a caller error
(:class:`SkillNotFound` → CLI usage exit), while a *registered skill whose
packaged resource is absent* is a broken installation
(:class:`SkillResourceMissing` → operational error).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class SkillSpec:
    """One bundled skill: its name and a one-line description."""

    name: str
    description: str


# Bundled skills, in registry order. `rac skill install` with no name installs
# all of them; `rac skill list` enumerates them.
BUNDLED_SKILLS = (
    SkillSpec(
        name="rac-artifacts",
        description="Author and maintain RAC Markdown artifacts with the rac CLI.",
    ),
    SkillSpec(
        name="rac-review",
        description="Review a RAC corpus and work findings worst-first.",
    ),
    SkillSpec(
        name="rac-ingest",
        description="Convert legacy documents into valid, linked RAC artifacts.",
    ),
)


class SkillNotFound(Exception):
    """The requested skill is not in the bundled registry (usage error)."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        super().__init__(
            f"unknown skill: {skill_name} (available: {', '.join(available_skills())})"
        )


class SkillResourceMissing(Exception):
    """A registered skill's packaged resource is absent (operational error)."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        super().__init__(
            f"packaged skill missing: {skill_name}; the RAC installation appears to be broken"
        )


def available_skills() -> list[str]:
    """Bundled skill names, in registry order."""
    return [spec.name for spec in BUNDLED_SKILLS]


def skill_specs() -> list[SkillSpec]:
    """Bundled skill specs (name + description), in registry order."""
    return list(BUNDLED_SKILLS)


def load_skill(skill_name: str) -> bytes:
    """Return the packaged ``SKILL.md`` content for ``skill_name``.

    Bytes, not text: the installed file must be byte-identical to the
    packaged resource (REQ-007). Raises :class:`SkillNotFound` for
    unregistered names and :class:`SkillResourceMissing` when the packaged
    resource is absent.
    """
    if skill_name not in available_skills():
        raise SkillNotFound(skill_name)
    resource = resources.files("rac.skills").joinpath(skill_name, "SKILL.md")
    try:
        return resource.read_bytes()
    except FileNotFoundError as exc:
        raise SkillResourceMissing(skill_name) from exc
