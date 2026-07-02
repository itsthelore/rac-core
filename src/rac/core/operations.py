"""Progress and cancellation primitives for long-lived consumers (v0.8.0).

A CLI invocation is short-lived -- walk, analyse, print, exit -- but an
interactive consumer such as the Explorer runs the same core operations
repeatedly inside one session. It needs to report progress and to cancel a walk
in flight, yet core must not learn anything about terminals or UI frameworks.

These primitives keep that seam clean: callbacks fire inline and synchronously
on the calling thread, and cancellation is a structural :class:`Protocol`, so a
Textual worker can bridge its own cancelled flag while tests drive the concrete
:class:`CancellationToken`. Neither the callback nor the token imports anything
UI-shaped into core.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from rac.errors import RACError


@dataclass(frozen=True)
class Progress:
    """A point-in-time progress report emitted during a long-running operation.

    ``total`` is ``None`` when the amount of work is not known up front.
    """

    phase: str
    completed: int
    total: int | None


# What a consumer supplies to receive :class:`Progress` reports.
ProgressCallback = Callable[[Progress], None]


class OperationCancelled(RACError):
    """Raised at a checkpoint when the supplied token has been cancelled."""


class CancelToken(Protocol):
    """Structural cancellation contract: anything exposing a ``cancelled`` flag.

    Consumers provide their own implementation (for example an Explorer worker
    that wraps Textual's cancelled state) without core ever importing it.
    """

    @property
    def cancelled(self) -> bool: ...


class CancellationToken:
    """The default in-process :class:`CancelToken`. Cancellation is one-way."""

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        # One-way latch: once set it never clears, so re-cancelling is a no-op.
        self._cancelled = True


def checkpoint(cancel: CancelToken | None) -> None:
    """Raise :class:`OperationCancelled` when ``cancel`` has been cancelled.

    Operations call this at safe boundaries (between files, between phases).
    ``None`` means the caller did not opt in to cancellation, so it is a no-op.
    """
    if cancel is not None and cancel.cancelled:
        raise OperationCancelled
