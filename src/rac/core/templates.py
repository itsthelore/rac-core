"""Canonical artifact template registry -- `rac new` / `rac templates` (v0.7.10).

The supported template set is the artifact-spec set: it is derived from
:data:`rac.core.artifacts.ARTIFACT_SPECS`, the same registry that drives
classification and validation, so the CLI never keeps a second list to drift out
of sync. Template bodies ship as package resources under :mod:`rac.templates`
and load through ``importlib.resources``, so generation works from an installed
wheel with no dogfood repository (ADR-021) and no AI or network (ADR-002).

Two failure modes stay deliberately distinct:

* an *unsupported artifact type* is a caller mistake -- :class:`TemplateNotFound`,
  which the CLI maps to a usage exit; while
* a *registered type whose packaged resource is missing* is a broken install --
  :class:`TemplateResourceMissing`, an operational error.
"""

from __future__ import annotations

from importlib import resources

from rac.core.artifacts import ARTIFACT_SPECS
from rac.errors import RACError


class TemplateNotFound(RACError):
    """The requested artifact type has no canonical template (usage error)."""

    def __init__(self, artifact_type: str) -> None:
        self.artifact_type = artifact_type
        super().__init__(
            f"unsupported artifact type: {artifact_type} "
            f"(supported: {', '.join(available_templates())})"
        )


class TemplateResourceMissing(RACError):
    """A registered type's packaged template is absent (operational error)."""

    def __init__(self, artifact_type: str) -> None:
        self.artifact_type = artifact_type
        super().__init__(
            f"packaged template missing for artifact type: {artifact_type}; "
            "the RAC installation appears to be broken"
        )


def available_templates() -> list[str]:
    """Canonical template names, in spec-registry order."""
    return [spec.name for spec in ARTIFACT_SPECS]


def load_template(artifact_type: str) -> str:
    """Return the canonical template body (text) for ``artifact_type``.

    Raises :class:`TemplateNotFound` for an unregistered type and
    :class:`TemplateResourceMissing` when the registered type's packaged
    resource cannot be found.
    """
    if artifact_type not in available_templates():
        raise TemplateNotFound(artifact_type)
    resource = resources.files("rac.templates").joinpath(f"{artifact_type}.md")
    try:
        return resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TemplateResourceMissing(artifact_type) from exc
