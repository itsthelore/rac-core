"""Bundled git-hook scripts (rac.hooks).

Each bundled hook ships as ``<style>.sh`` under this package, installed by
``rac hook install`` via ``importlib.resources`` rather than read from the
repository -- the same distribution pattern as :mod:`rac.skills` and
:mod:`rac.templates`. Discovery and loading live in :mod:`rac.core.hooks`.
"""
