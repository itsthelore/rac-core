"""Portal HTML assembly — inject the export payload into the vendored shell.

The Portal shell is a self-contained HTML viewer built from
``lore-web/src/viewer/`` and committed as package data at
``rac.templates.portal`` together with its provenance manifest
(roadmap v0.11.0, Initiative 2). It carries one empty data seam,

    <script type="application/json" id="lore-export"></script>

and ``render_export_html`` substitutes the export JSON into that element —
nothing else in the file changes, so the result opens from ``file://`` with
zero network requests (ADR-002 offline; data injection per
``lore-web/VIEWER_CONTRACT.md``).

The serialized JSON is made ``<script>``-safe with two valid JSON escapes:
``</`` becomes ``<\\/`` (no premature ``</script>``) and ``<!--`` becomes
``<\\u0021--`` (no HTML comment open), so the embedded payload parses
unchanged.

Two failure modes are deliberately distinct exceptions, both operational
(the shell ships with the distribution; neither is a caller error): a
*missing packaged shell* is a broken installation, while a shell *without
exactly one empty seam* is corrupt vendoring.
"""

from __future__ import annotations

from importlib import resources

from rac.services.export import CorpusExport

from .json import render_export_json

# The exact empty data seam the shell-only viewer build emits (no whitespace
# inside the element); the populated form replaces it verbatim.
_SEAM = '<script type="application/json" id="lore-export"></script>'


class PortalShellMissing(Exception):
    """The packaged Portal shell is absent (broken installation)."""

    def __init__(self) -> None:
        super().__init__(
            "packaged portal shell missing (rac/templates/portal/"
            "lore-portal-shell.html); the RAC installation appears to be broken"
        )


class PortalSeamMissing(Exception):
    """The packaged shell lacks its single empty data seam (corrupt vendoring)."""

    def __init__(self) -> None:
        super().__init__(
            "packaged portal shell has no usable data seam "
            f"({_SEAM}); re-vendor it: cd lore-web && npm run vendor:shell"
        )


def _load_shell() -> str:
    resource = resources.files("rac.templates").joinpath("portal/lore-portal-shell.html")
    try:
        return resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PortalShellMissing() from exc


def _escape_for_script(payload: str) -> str:
    """Make a serialized JSON document safe inside a ``<script>`` element."""
    return payload.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def render_export_html(export: CorpusExport) -> str:
    """The vendored Portal shell with ``export`` injected into its data seam."""
    shell = _load_shell()
    if shell.count(_SEAM) != 1:
        raise PortalSeamMissing()
    payload = _escape_for_script(render_export_json(export))
    populated = f'<script type="application/json" id="lore-export">{payload}</script>'
    return shell.replace(_SEAM, populated)
