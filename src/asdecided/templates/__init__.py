"""Bundled canonical artifact templates (v0.7.10).

One ``<artifact-type>.md`` per supported artifact spec. These files are the
canonical generation source for ``decided new`` (ADR-021): packaged with the
distribution and loaded via ``importlib.resources``, never from the dogfood
repository. ``asdecided.core.templates`` owns discovery and loading; tests pin each
file to the spec-derived render so templates cannot drift from validators.
"""
