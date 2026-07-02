"""Bundled git-hook registry -- `rac hook` (v0.13.4).

A static registry of named git hooks, each with a one-line description,
surfaced by ``rac hook list`` and installable by style. Hook scripts ship as
package resources under :mod:`rac.hooks` and load through
``importlib.resources``, mirroring how skills ship under :mod:`rac.skills`
(ADR-021), so installation works from an installed wheel with no repository,
network, or AI.

The two failure modes mirror :mod:`rac.core.skills`: an *unregistered hook
style* is a caller mistake (:class:`HookNotFound`, a usage exit), while a
*registered hook whose packaged resource is absent* is a broken install
(:class:`HookResourceMissing`, an operational error).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from rac.errors import RACError


@dataclass(frozen=True)
class HookSpec:
    """One bundled git hook: its style (the git hook filename) and a description."""

    style: str  # the git hook filename, e.g. "post-commit"
    description: str


# The bundled hooks, in registry order. ``rac hook install`` defaults to the
# first (the advisory post-commit nudge); ``rac hook list`` enumerates them.
BUNDLED_HOOKS = (
    HookSpec(
        style="post-commit",
        description="Advisory write-cadence nudge after each commit (never blocks).",
    ),
    HookSpec(
        style="pre-commit",
        description="Validate staged Markdown artifacts before each commit (blocks on errors).",
    ),
)

# The style ``rac hook install`` uses when the caller names none.
DEFAULT_STYLE = BUNDLED_HOOKS[0].style


class HookNotFound(RACError):
    """The requested hook style is not in the bundled registry (usage error)."""

    def __init__(self, style: str) -> None:
        self.style = style
        super().__init__(f"unknown hook style: {style} (available: {', '.join(available_hooks())})")


class HookResourceMissing(RACError):
    """A registered hook's packaged resource is absent (operational error)."""

    def __init__(self, style: str) -> None:
        self.style = style
        super().__init__(
            f"packaged hook missing: {style}; the RAC installation appears to be broken"
        )


def available_hooks() -> list[str]:
    """Bundled hook styles, in registry order."""
    return [spec.style for spec in BUNDLED_HOOKS]


def hook_specs() -> list[HookSpec]:
    """Bundled hook specs (style + description), in registry order."""
    return list(BUNDLED_HOOKS)


def load_hook(style: str) -> bytes:
    """Return the packaged hook script for ``style`` as raw bytes.

    Bytes, not text: the installed file must be byte-identical to the packaged
    resource. Raises :class:`HookNotFound` for an unregistered style and
    :class:`HookResourceMissing` when the packaged resource is absent.
    """
    if style not in available_hooks():
        raise HookNotFound(style)
    resource = resources.files("rac.hooks").joinpath(f"{style}.sh")
    try:
        return resource.read_bytes()
    except FileNotFoundError as exc:
        raise HookResourceMissing(style) from exc
