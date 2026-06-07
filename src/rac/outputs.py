"""Compatibility shim — implementation moved to the :mod:`rac.output` package (v0.7.4).

Human-readable rendering now lives in :mod:`rac.output.human`, JSON in
:mod:`rac.output.json`, and Markdown templates in :mod:`rac.output.templates`.
"""

from rac.output import *  # noqa: F401,F403
