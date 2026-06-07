"""Compatibility shim — implementation moved to :mod:`rac.services.ingest` (v0.7.4)."""

from rac.services.ingest import *  # noqa: F401,F403

# Private helpers exercised directly by the test suite (`import *` skips _names).
from rac.services.ingest import (  # noqa: F401
    _is_missing_dependency,
    _missing_extra_message,
)
