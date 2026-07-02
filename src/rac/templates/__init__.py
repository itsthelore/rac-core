"""Bundled canonical artifact templates (rac.templates).

Each supported artifact spec ships one ``<artifact-type>.md`` under this package
-- the canonical generation source for ``rac new`` (ADR-021), loaded via
``importlib.resources`` rather than from the dogfood repository. Discovery and
loading live in :mod:`rac.core.templates`; a test pins every packaged file to
the spec-derived render so a template can never drift from its validators.
"""
