"""Bundled native (Rust) engine binaries — the covered-surface fast path.

Empty in the repository and in the pure-Python sdist. Platform wheels place the
compiled ``rac`` and ``rac-mcp`` binaries here at build time (native-engine
cutover); ``rac.dispatch`` resolves and execs them for covered commands, and
falls through to the Python engine when no binary is bundled. So install never
depends on a binary being present — the native path is a per-platform
acceleration, never a hard requirement.
"""
