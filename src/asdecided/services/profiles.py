"""Built-in init profiles — `decided init --profile <name>` (ADR-088).

A profile is a named bundle of *configuration only* (ADR-085): the
``.decided/config.yaml`` stanzas and the ``.mcp.json`` client wiring a careful admin
would otherwise hand-write. A profile never writes authored prose (ADR-024,
ADR-044) — firm ADR/prompt content lives in a referenced standards corpus
(ADR-089), not in generated files.

Profiles are creation-time configuration: they apply on a fresh `decided init`, layer
onto the repository key, and never overwrite a file that already exists. Built-in
and named (``default``, ``enterprise``); a profile adds no code path a solo
developer cannot reach (the ADR-085 backstop) — it emits exactly the files a
careful admin would hand-write.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from asdecided.errors import RACError

# Native AsDecided MCP wiring, identical for Claude Code and Cursor.
# Cursor (``.cursor/mcp.json``). Mirrors examples/cursor/mcp.example.json.
MCP_JSON = (
    "{\n"
    '  "mcpServers": {\n'
    '    "asdecided": {\n'
    '      "command": "decided-mcp",\n'
    '      "args": ["--root", "."]\n'
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
# Enterprise profile (ADR-088): relationship-integrity findings block `decided gate`,
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

    ``config_stanza`` is extra ``.decided/config.yaml`` YAML appended after the
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
    untouched and omitted, so `decided init` can report exactly what landed and a
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


# The shared org endpoint's server name in client configs (ADR-117). Fixed, so
# every repository in a fleet addresses the org corpus under one identity.
ORG_SERVER_KEY = "lore-org"


class MalformedClientConfig(RACError):
    """An existing MCP client config cannot be merged into (operational error)."""

    def __init__(self, config_path: str, reason: str) -> None:
        self.config_path = config_path
        super().__init__(f"malformed MCP client config {config_path}: {reason}")


def org_server_entry(url: str) -> dict[str, str]:
    """The ``lore-org`` streamable-HTTP server entry for ``url`` (ADR-117)."""
    return {"type": "http", "url": url}


def write_org_endpoint(directory: str, url: str) -> list[str]:
    """Ensure the ``lore-org`` HTTP entry in each client config (ADR-117).

    Unlike a profile — creation-time by design — org wiring is an explicit
    operator action, so it also merges into existing files: only the
    ``lore-org`` key under ``mcpServers`` is added or updated, everything the
    user wrote is preserved (JSON formatting is normalised on rewrite), and a
    run that would change nothing writes nothing. All targets are parsed
    before any is written, so a malformed file means no partial writes.

    Returns the paths actually written, in target order. Raises
    :class:`MalformedClientConfig` when an existing target is not a JSON
    object with an object-valued ``mcpServers``.
    """
    entry = org_server_entry(url)
    planned: list[tuple[Path, str]] = []
    for target in _MCP_TARGETS:
        path = Path(directory) / target
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # A stable reason, not the parser's prose: the message is part
                # of the cross-engine output contract (ADR-116), and the two
                # engines' JSON parsers word their errors differently.
                raise MalformedClientConfig(str(path), "not valid JSON") from None
            if not isinstance(data, dict):
                raise MalformedClientConfig(str(path), "top level must be a JSON object")
            servers = data.setdefault("mcpServers", {})
            if not isinstance(servers, dict):
                raise MalformedClientConfig(str(path), "'mcpServers' must be a JSON object")
            if servers.get(ORG_SERVER_KEY) == entry:
                continue  # already wired to this endpoint: idempotent no-op
            servers[ORG_SERVER_KEY] = dict(entry)
            planned.append((path, json.dumps(data, indent=2, ensure_ascii=False) + "\n"))
        else:
            payload = {"mcpServers": {ORG_SERVER_KEY: dict(entry)}}
            planned.append((path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n"))
    written: list[str] = []
    for path, text in planned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(str(path))
    return written
