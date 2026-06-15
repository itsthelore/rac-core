"""Exception hierarchy for the RAC Python SDK.

Every error raised by a public RAC service derives from :class:`RACError`, so an
SDK consumer can catch the whole family with a single ``except rac.RACError``
without importing each service's exception module (ADR-062). The concrete
subclasses keep their own names and messages and live next to the service that
raises them; this module only owns the shared root.
"""

from __future__ import annotations


class RACError(Exception):
    """Base class for every error a RAC service raises.

    Catch this to handle any RAC failure generically; catch a concrete subclass
    (for example :class:`rac.services.create.OutputPathExists`) to handle a
    specific condition. The hierarchy is part of the SDK's public surface, so new
    service errors are expected to inherit from it rather than from
    :class:`Exception` directly.
    """
