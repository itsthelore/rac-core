"""Built-in init profiles — `rac init --profile <name>` (ADR-088).

A profile is a named bundle of *configuration only* (ADR-085): the
``.rac/config.yaml`` stanzas and the ``.mcp.json`` client wiring a careful admin
would otherwise hand-write. A profile never writes authored prose (ADR-024,
ADR-044) — firm ADR/prompt content lives in a referenced standards corpus
(ADR-089), not in generated files.

Profiles are creation-time configuration: they apply on a fresh `rac init`, layer
onto the repository key, and never overwrite a file that already exists. Built-in
and named (``default``, ``enterprise``); a profile adds no code path a solo
developer cannot reach (the ADR-085 backstop) — it emits exactly the files a
careful admin would hand-write.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The lore MCP server wiring, identical for Claude Code (root ``.mcp.json``) and
# Cursor (``.cursor/mcp.json``). Mirrors examples/cursor/mcp.example.json.
MCP_JSON = (
    "{\n"
    '  "mcpServers": {\n'
    '    "lore": {\n'
    '      "command": "rac",\n'
    '      "args": ["mcp", "--root", "."]\n'
    "    }\n"
    "  }\n"
    "}\n"
)

# Enterprise enforcement (ADR-049): relationship-integrity findings block the
# gate, committed explicitly so the policy is auditable rather than implicit
# (these are blocking by default; the profile makes the posture a committed,
# git-diffable artifact). Requirement-quality severities are left at their
# defaults — escalate per repo (ADR-053) for stricter authoring discipline.
_ENTERPRISE_CONFIG = """\
# Enterprise profile (ADR-088): relationship-integrity findings block `rac gate`,
# committed explicitly so the enforcement policy is auditable (ADR-049).
enforcement:
  blocking:
    - relationship-target-not-found
    - relationship-target-ambiguous
    - relationship-self-reference
    - relationship-target-type-mismatch
    - relationship-target-superseded
    - relationship-cycle
    - relationship-edge-unsupported
    - duplicate-artifact-identifier
"""


@dataclass(frozen=True)
class Profile:
    """A built-in init profile: config-only, never prose (ADR-088).

    ``config_stanza`` is extra ``.rac/config.yaml`` YAML appended after the
    repository key (empty for none); ``mcp_wiring`` requests the Claude Code and
    Cursor ``.mcp.json`` client configs.
    """

    name: str
    config_stanza: str
    mcp_wiring: bool


PROFILES: dict[str, Profile] = {
    # default: just the client wiring — broadly useful, no policy stanza.
    "default": Profile(name="default", config_stanza="", mcp_wiring=True),
    # enterprise: client wiring plus an explicit, auditable enforcement policy.
    "enterprise": Profile(name="enterprise", config_stanza=_ENTERPRISE_CONFIG, mcp_wiring=True),
}

# The recognised profile names, for CLI choices and config validation.
PROFILE_NAMES: tuple[str, ...] = tuple(PROFILES)

# The ``.mcp.json`` client targets a profile wires, relative to the repo root.
_MCP_TARGETS: tuple[str, ...] = (".mcp.json", ".cursor/mcp.json")


def get_profile(name: str) -> Profile | None:
    """The :class:`Profile` with the given name, or None."""
    return PROFILES.get(name)


def write_mcp_configs(directory: str) -> list[str]:
    """Write the lore MCP wiring for Claude Code and Cursor, never overwriting.

    Returns the paths actually written, in target order; an existing file is left
    untouched and omitted, so `rac init` can report exactly what landed and a
    user's own ``.mcp.json`` is never clobbered.
    """
    written: list[str] = []
    for target in _MCP_TARGETS:
        path = Path(directory) / target
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MCP_JSON, encoding="utf-8")
        written.append(str(path))
    return written
