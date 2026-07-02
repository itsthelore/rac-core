"""Bundled agent-skill registry -- `rac skill` (v0.10.5).

A static registry of named Claude Code skills, each with a one-line description,
surfaced by ``rac skill list`` and installable by name. Skill content ships as
package resources under :mod:`rac.skills` and loads through
``importlib.resources``, mirroring how canonical templates ship under
:mod:`rac.templates` (ADR-021), so installation works from an installed wheel
with no dogfood repository and no AI or network.

The two failure modes mirror :mod:`rac.core.templates`: an *unregistered skill
name* is a caller mistake (:class:`SkillNotFound`, a usage exit), while a
*registered skill whose packaged resource is absent* is a broken install
(:class:`SkillResourceMissing`, an operational error).

``load_skill`` and ``available_skills`` read the module-level
:data:`BUNDLED_SKILLS` at call time, so tests that monkeypatch it (to inject a
resource-less skill) see their change.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from rac.errors import RACError


@dataclass(frozen=True)
class SkillSpec:
    """One bundled skill: its name and a one-line description."""

    name: str
    description: str


# The bundled skills, in registry order. ``rac skill install`` with no name
# installs every one; ``rac skill list`` enumerates them. Descriptions are
# user-visible (golden-pinned), so treat them as fixed text.
BUNDLED_SKILLS = (
    SkillSpec(
        name="rac-artifacts",
        description="Author and maintain Lore (RAC) Markdown artifacts with the rac CLI.",
    ),
    SkillSpec(
        name="rac-review",
        description="Review a Lore (RAC) corpus and work findings worst-first.",
    ),
    SkillSpec(
        name="rac-ingest",
        description="Convert legacy documents into valid, linked Lore (RAC) artifacts.",
    ),
    SkillSpec(
        name="rac-import",
        description="Reformat one document into one valid Lore (RAC) artifact, with human review.",
    ),
    SkillSpec(
        name="rac-capture",
        description="Capture a new decision or requirement into a valid Lore (RAC) artifact.",
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
    """Return the packaged ``SKILL.md`` content for ``skill_name`` as raw bytes.

    Bytes, not text: the installed file must be byte-identical to the packaged
    resource (REQ-007). Raises :class:`SkillNotFound` for an unregistered name
    and :class:`SkillResourceMissing` when the packaged resource is absent.
    """
    if skill_name not in available_skills():
        raise SkillNotFound(skill_name)
    resource = resources.files("rac.skills").joinpath(skill_name, "SKILL.md")
    try:
        return resource.read_bytes()
    except FileNotFoundError as exc:
        raise SkillResourceMissing(skill_name) from exc
