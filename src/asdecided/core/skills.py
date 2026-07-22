"""Bundled agent skill registry — `decided skill` (v0.10.5).

The bundled skill set is a static registry of named skills with one-line
descriptions, surfaced by `decided skill list` and installable by name. Skill
content ships as package resources under :mod:`asdecided.skills` and is loaded with
``importlib.resources``, mirroring how canonical templates ship under
:mod:`asdecided.templates` (ADR-021), so installation works from an installed wheel
without the dogfood repository and without AI or network access.

Two failure modes are deliberately distinct, mirroring
:mod:`asdecided.core.templates`: an *unregistered skill name* is a caller error
(:class:`SkillNotFound` → CLI usage exit), while a *registered skill whose
packaged resource is absent* is a broken installation
(:class:`SkillResourceMissing` → operational error).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from asdecided.errors import RACError


@dataclass(frozen=True)
class SkillSpec:
    """One bundled skill: its name and a one-line description."""

    name: str
    description: str


# Bundled skills, in registry order. `decided skill install` with no name installs
# all of them; `decided skill list` enumerates them.
BUNDLED_SKILLS = (
    SkillSpec(
        name="decided-artifacts",
        description="Author and maintain AsDecided Markdown artifacts with the decided CLI.",
    ),
    SkillSpec(
        name="decided-review",
        description="Review an AsDecided corpus and work findings worst-first.",
    ),
    SkillSpec(
        name="decided-import",
        description="Reformat one document into one valid AsDecided artifact, with human review.",
    ),
    SkillSpec(
        name="decided-capture",
        description="Capture a new decision or requirement into a valid AsDecided artifact.",
    ),
)


class SkillNotFound(RACError):
    """The requested skill is not in the bundled registry (usage error)."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(
            f"unknown skill: {skill_name} (available: {', '.join(available_skills())})"
        )


class SkillResourceMissing(RACError):
    """A registered skill's packaged resource is absent (operational error)."""

    def __init__(self, skill_name: str) -> None:
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
    resource = resources.files("asdecided.skills").joinpath(skill_name, "SKILL.md")
    try:
        return resource.read_bytes()
    except FileNotFoundError as exc:
        raise SkillResourceMissing(skill_name) from exc
