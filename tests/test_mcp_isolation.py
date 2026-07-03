"""Guide isolation — the MCP consumer boundary holds by construction (v0.10.0).

AST-based rules over the source tree, mirroring ``test_explorer_isolation``
(ADR-015, ADR-031):

- ``rac.core`` and ``rac.services`` never import the ``mcp`` SDK or ``rac.mcp``
  — the dependency direction points one way, so Core cannot depend on its
  consumer.
- ``rac.mcp`` imports no write-capable service: Guide is read-only by
  construction, not by promise (ADR-031). The write-shaped services
  (``create``, ``init``, ``migrate``, ``ingest``, ``improve``) are forbidden in
  the server layer.

These are the same guarantees the explorer battery holds for Textual, restated
for the MCP surface so the contract is enforced by a test rather than by review.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "rac"

# Write-capable / write-shaped services the read-only server must never import
# (the roadmap names these explicitly). ``create``/``init``/``migrate`` write
# files directly; ``ingest``/``improve`` are write-shaped transforms.
WRITE_SERVICES: tuple[str, ...] = (
    "rac.services.create",
    "rac.services.init",
    "rac.services.migrate",
    "rac.services.ingest",
    "rac.services.improve",
)


def _imported_modules(path: Path) -> set[str]:
    """Every module name imported anywhere in ``path`` (absolute imports)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def _violations(files: list[Path], forbidden: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for file in files:
        for module in sorted(_imported_modules(file)):
            if any(module == f or module.startswith(f + ".") for f in forbidden):
                found.append(f"{file.relative_to(SRC.parent)} imports {module}")
    return found


def test_core_and_services_never_import_mcp_or_guide():
    files = sorted((SRC / "core").rglob("*.py")) + sorted((SRC / "services").rglob("*.py"))
    assert files
    assert _violations(files, ("mcp", "rac.mcp")) == []


def test_server_layer_imports_no_write_capable_service():
    files = sorted((SRC / "mcp").rglob("*.py"))
    assert files, "the MCP server package must exist"
    assert _violations(files, WRITE_SERVICES) == []


def test_only_the_server_package_imports_the_mcp_sdk():
    # Mirror of "only Explorer's Textual modules import Textual": every other
    # package under rac/ must stay free of the SDK so the import direction is
    # unambiguous.
    other = [f for f in SRC.rglob("*.py") if "mcp" not in f.relative_to(SRC).parts]
    assert other
    assert _violations(other, ("mcp",)) == []


# Network client modules; the ping module is RAC's fenced outbound surface
# (ADR-041). ``urllib.parse`` (string formatting for the share URL) is
# deliberately not in this list.
NETWORK_MODULES: tuple[str, ...] = ("urllib.request", "http.client")

# The transport-layer modules the serving ADR (ADR-098) permits to reach
# network/serving code: ``ping`` (the fenced outbound ping, ADR-041) and
# ``transport`` (the HTTP serving layer). Every other module — all tool logic —
# stays network-free. Widening this allowance is a recorded decision, never a
# silent drift (REQ-005).
NETWORK_ALLOWED: tuple[Path, ...] = (
    SRC / "mcp" / "ping.py",
    SRC / "mcp" / "transport.py",
)

# The Guide tool-logic modules: the server body and the read-only helpers it
# calls. None of them may import a network module — the serving allowance above
# is scoped to the transport layer, not to tool logic (ADR-098, REQ-005).
TOOL_LOGIC_MODULES: tuple[str, ...] = (
    "server",
    "budget",
    "errors",
    "telemetry",
    "audit",
)


def test_network_imports_are_confined_to_the_transport_layer():
    # The trust statement, revised for HTTP serving (ADR-098): "what does RAC
    # reach the network for" is answerable by reading two files — the outbound
    # ping and the serving transport — and nothing else.
    files = [f for f in SRC.rglob("*.py") if f not in NETWORK_ALLOWED]
    assert files
    assert _violations(files, NETWORK_MODULES) == []


def test_tool_logic_modules_are_network_free():
    # The retained guard (ADR-098, REQ-005): the network allowance is scoped to
    # the transport layer only. A tool-logic module that imports a network
    # module must still fail this battery.
    files = [SRC / "mcp" / f"{module}.py" for module in TOOL_LOGIC_MODULES]
    assert all(f.exists() for f in files), "every named tool-logic module must exist"
    assert _violations(files, NETWORK_MODULES) == []
