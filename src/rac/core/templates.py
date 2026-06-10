"""Canonical artifact template registry — `rac new` / `rac templates` (v0.7.10).

The supported template set is derived from :data:`rac.core.artifacts.ARTIFACT_SPECS`
— the same registry that drives classification and validation — so the CLI never
maintains its own list (REQ: one canonical registry). Template content ships as
package resources under :mod:`rac.templates` and is loaded with
``importlib.resources``, so generation works from an installed wheel without the
dogfood repository (ADR-021) and without AI or network access (ADR-002).

Two failure modes are deliberately distinct: an *unsupported artifact type* is a
caller error (:class:`TemplateNotFound` → CLI usage exit), while a *registered
type whose packaged resource is missing* is a broken installation
(:class:`TemplateResourceMissing` → operational error).
"""

from __future__ import annotations

from importlib import resources

from rac.core.artifacts import ARTIFACT_SPECS


class TemplateNotFound(Exception):
    """The requested artifact type has no canonical template (usage error)."""

    def __init__(self, artifact_type: str):
        self.artifact_type = artifact_type
        super().__init__(
            f"unsupported artifact type: {artifact_type} "
            f"(supported: {', '.join(available_templates())})"
        )


class TemplateResourceMissing(Exception):
    """A registered type's packaged template is absent (operational error)."""

    def __init__(self, artifact_type: str):
        self.artifact_type = artifact_type
        super().__init__(
            f"packaged template missing for artifact type: {artifact_type}; "
            "the RAC installation appears to be broken"
        )


def available_templates() -> list[str]:
    """Canonical template names, in spec registry order."""
    return [spec.name for spec in ARTIFACT_SPECS]


def load_template(artifact_type: str) -> str:
    """Return the canonical template body for ``artifact_type``.

    Raises :class:`TemplateNotFound` for unregistered types and
    :class:`TemplateResourceMissing` when the packaged resource is absent.
    """
    if artifact_type not in available_templates():
        raise TemplateNotFound(artifact_type)
    resource = resources.files("rac.templates").joinpath(f"{artifact_type}.md")
    try:
        return resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TemplateResourceMissing(artifact_type) from exc
