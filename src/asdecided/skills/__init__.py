"""Bundled Claude Code agent skills (v0.10.4).

One ``<skill-name>/SKILL.md`` per bundled skill. These files are the canonical
installation source for ``decided skill install``: packaged with the distribution
and loaded via ``importlib.resources`` (the ADR-021 pattern), never from the
dogfood repository. ``asdecided.core.skills`` owns discovery and loading; a test pins
each packaged file byte-for-byte against the repository's dogfood copy under
``.claude/skills/`` so the two instances cannot drift (REQ-007).
"""
