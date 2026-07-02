"""RAC Guide — the MCP server consumer surface.

Guide serves RAC repository knowledge to coding agents over MCP so recorded
decisions are respected rather than silently violated. Like Explorer, it is a
*consumer* of RAC Core (ADR-015, ADR-031): the server layer calls read-only
services and shapes their results for the wire, owning no repository
intelligence of its own.

This package is the only place in RAC permitted to import the ``mcp`` SDK — the
mirror of the rule that only Explorer's Textual modules import Textual. Nothing
under ``rac.core`` or ``rac.services`` imports ``rac.mcp`` or ``mcp``, and the
server layer imports no write-capable service. Both invariants are enforced by
AST rules in ``tests/test_mcp_isolation.py``, not by convention.
"""

from __future__ import annotations

from rac.mcp.server import build_server, run_server

__all__ = ["build_server", "run_server"]
