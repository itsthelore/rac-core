"""RAC Guide — the MCP server consumer surface (v0.10.0).

Guide serves RAC repository knowledge to coding agents over MCP, so recorded
decisions are respected instead of silently violated. It is a consumer of RAC
Core in the same sense Explorer is (ADR-015, ADR-031): the server layer calls
read-only services and shapes their results for the wire, owning no repository
intelligence of its own.

This package is the only place in RAC permitted to import the ``mcp`` SDK
(the mirror of the rule that only Explorer's Textual modules import Textual).
Nothing under ``rac.core`` or ``rac.services`` imports ``rac.mcp`` or ``mcp``,
and the server layer imports no write-capable service — both enforced by
``tests/test_mcp_isolation.py``.
"""

from __future__ import annotations

from rac.mcp.server import build_server, run_server

__all__ = ["build_server", "run_server"]
