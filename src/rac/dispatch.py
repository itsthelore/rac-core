"""Native-engine dispatch — route covered commands to the Rust binary.

The native-engine cutover (roadmap:native-engine-cutover, ADR-116) makes Rust
the default engine for the covered surface. This module is the thin, logic-free
router the design specifies: it peeks the subcommand, and when a bundled Rust
binary exists for it, replaces this process with the binary (``os.execv`` — a
true process replacement, so argv/stdin/stdout/stderr, exit code, and signals
pass through untouched, giving byte-parity for free). Otherwise it returns and
the Python engine runs — the universal fallback that keeps every surface working
and never lets a missing binary break an install.

Covered = the parity-battery command set the Rust ``rac`` binary implements
(PARITY-REPORT). Excluded: the fenced surfaces ``explorer`` and ``ingest`` (they
stay Python), and ``retrieve`` (adopted only once grounding-retrieval-surface
merges into the reference — the port follows, never leads). ``mcp`` routes to
the separate ``rac-mcp`` binary.

Escape hatch (``RAC_ENGINE``): ``python`` forces the Python engine for any
command; ``rust`` forces the native path and errors loudly if a covered
command's binary is missing (so CI can assert the native path is really used).
Unset = the default routing above.
"""

from __future__ import annotations

import os
import sys
from importlib import resources

# Subcommands the Rust `rac` binary serves (cli.rs SUBCOMMANDS minus `retrieve`,
# pending the retrieval-branch merge). `mcp` is handled separately (rac-mcp).
_COVERED_CLI = frozenset(
    {
        "validate", "diff", "inspect", "improve", "relationships", "stats",
        "schema", "templates", "resolve", "find", "review", "export", "index",
        "portfolio", "coverage", "decisions-for", "gate", "doctor",
        "watchkeeper", "mcp-stats", "usage", "telemetry", "skill", "hook",
        "eval", "new", "init", "quickstart", "rename", "migrate",
    }
)

ENGINE_ENV = "RAC_ENGINE"


def _binary_path(name: str) -> str | None:
    """The bundled binary's filesystem path, or None when not bundled."""
    exe = name + (".exe" if os.name == "nt" else "")
    try:
        resource = resources.files("rac.bin").joinpath(exe)
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    # Wheels install rac as real files, so the resource is a concrete path; guard
    # the zipimport case (no bundled binary there anyway) by requiring a real file.
    try:
        if resource.is_file():
            return os.fspath(resource)
    except (FileNotFoundError, TypeError):
        pass
    return None


def _exec(binary: str, argv: list[str]) -> None:
    """Replace this process with `binary argv...` (never returns on success)."""
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(binary, [binary, *argv])


def _missing(kind: str) -> None:
    sys.stderr.write(
        f"rac: RAC_ENGINE=rust but no bundled '{kind}' binary for this platform "
        f"(install a platform wheel, or unset RAC_ENGINE to use the Python engine).\n"
    )
    raise SystemExit(2)


def maybe_exec_native(argv: list[str]) -> None:
    """Exec the native engine for a covered command, or return to run Python.

    Called at the very top of ``rac.cli.main`` before any argument parsing, so
    the Rust binary does its own parsing over the identical argv.
    """
    engine = os.environ.get(ENGINE_ENV, "").strip().lower()
    if engine == "python":
        return  # forced Python — the arbiter path and the universal fallback
    forced_rust = engine == "rust"

    # The subcommand is the first non-flag token; `--version`/`-V` with no
    # subcommand is a covered root action the Rust binary also serves.
    sub = next((a for a in argv if not a.startswith("-")), None)
    root_version = bool(argv) and argv[0] in ("--version", "-V") and sub is None

    if sub == "mcp":
        binary = _binary_path("rac-mcp")
        if binary is not None:
            _exec(binary, argv[argv.index("mcp") + 1 :])  # drop the `mcp` token
        if forced_rust:
            _missing("rac-mcp")
        return

    if sub in _COVERED_CLI or root_version:
        binary = _binary_path("rac")
        if binary is not None:
            _exec(binary, argv)
        if forced_rust:
            _missing("rac")
        return

    # Fenced (explorer, ingest), help, no-subcommand, or unknown: Python.
    if forced_rust and sub is not None:
        sys.stderr.write(
            f"rac: RAC_ENGINE=rust, but '{sub}' is not a native-covered command "
            f"(it runs on the Python engine); unset RAC_ENGINE.\n"
        )
        raise SystemExit(2)
    return
