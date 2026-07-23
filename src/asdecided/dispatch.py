"""Native-only launcher for the AsDecided command-line tools."""

from __future__ import annotations

import os
import sys
from importlib import resources


def _binary_path(name: str) -> str | None:
    """Return a bundled native binary path when this wheel contains it."""
    executable = name + (".exe" if os.name == "nt" else "")
    try:
        resource = resources.files("asdecided.bin").joinpath(executable)
        return str(resource) if resource.is_file() else None
    except (ModuleNotFoundError, FileNotFoundError, TypeError):
        return None


def _exec(binary: str, argv: list[str]) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(binary, [binary, *argv])


def _missing(name: str) -> None:
    sys.stderr.write(
        f"decided: no bundled '{name}' binary is available for this platform "
        "(install a supported platform wheel).\n"
    )
    raise SystemExit(2)


def main() -> None:
    """Run Rust; Python is an SDK/packaging bridge, not a second CLI engine."""
    argv = sys.argv[1:]
    if argv and argv[0] == "mcp":
        name, forwarded = "decided-mcp", argv[1:]
    else:
        name, forwarded = "decided", argv
    binary = _binary_path(name)
    if binary is None:
        _missing(name)
    _exec(binary, forwarded)
