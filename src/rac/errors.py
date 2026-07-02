"""The shared exception root for the RAC Python SDK.

RAC exposes many services, each with its own failure conditions. Rather than
make a consumer import and enumerate every service's exception type, every public
failure inherits from a single root, :class:`RACError`, so a caller can guard a
whole workflow with one ``except rac.RACError`` (ADR-062). The concrete
exceptions live beside the service that raises them; this module owns only the
root they share.
"""

from __future__ import annotations


class RACError(Exception):
    """Root of the RAC exception hierarchy.

    Every error a public RAC service raises derives from this class, so a caller
    can treat any RAC failure uniformly, or narrow to a concrete subclass (such as
    :class:`rac.services.create.OutputPathExists`) for a single condition. New
    service errors inherit from here rather than from :class:`Exception` directly,
    which keeps them part of the SDK's advertised surface.
    """
