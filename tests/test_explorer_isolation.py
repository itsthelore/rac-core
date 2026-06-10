"""Core isolation — the Explorer boundary holds in both directions (v0.8.0).

AST-based rules over the source tree (ADR-015 / ADR-028):

- ``rac.core`` and ``rac.services`` never import Textual or the Explorer.
- Textual widgets/screens/app never import Core internals — they reach RAC
  only through ``rac.explorer.adapter`` / ``state`` / ``launch``.
- The adapter, state, and launch modules never import Textual, so the base
  install (no ``explorer`` extra) and headless tests work without it.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "rac"


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


def test_core_and_services_never_import_textual_or_explorer():
    files = sorted((SRC / "core").rglob("*.py")) + sorted((SRC / "services").rglob("*.py"))
    assert files
    assert _violations(files, ("textual", "rac.explorer")) == []


def test_widgets_never_import_core_internals():
    ui_files = [SRC / "explorer" / "app.py"]
    for sub in ("screens", "widgets"):
        ui_files.extend(sorted((SRC / "explorer" / sub).rglob("*.py")))
    ui_files = [f for f in ui_files if f.exists()]
    assert ui_files, "the Textual application modules must exist"
    assert _violations(ui_files, ("rac.core", "rac.services")) == []


def test_adapter_state_and_launch_never_import_textual():
    files = [
        SRC / "explorer" / "__init__.py",
        SRC / "explorer" / "state.py",
        SRC / "explorer" / "adapter.py",
        SRC / "explorer" / "launch.py",
        SRC / "explorer" / "commands.py",
        SRC / "explorer" / "firstrun.py",
        SRC / "explorer" / "editor.py",
        SRC / "explorer" / "preferences.py",
        SRC / "explorer" / "workspace.py",
        SRC / "explorer" / "mascot.py",
    ]
    files = [f for f in files if f.exists()]
    assert (SRC / "explorer" / "adapter.py") in files
    assert _violations(files, ("textual",)) == []


def test_command_routing_owns_no_intelligence():
    # DESIGN-command-surface: routing may live in Explorer, answers may not —
    # the registry module reaches neither Core nor the services.
    commands = SRC / "explorer" / "commands.py"
    assert _violations([commands], ("rac.core", "rac.services")) == []
