"""Bundled Claude Code agent skills (rac.skills).

Each bundled skill ships as ``<skill-name>/SKILL.md`` under this package -- the
canonical install source for ``rac skill install``, loaded via
``importlib.resources`` (the ADR-021 pattern) rather than from the dogfood
repository. Discovery and loading live in :mod:`rac.core.skills`; a test pins
every packaged file byte-for-byte against the repository's dogfood copy under
``.claude/skills/`` so the two surfaces cannot drift (REQ-007).
"""
