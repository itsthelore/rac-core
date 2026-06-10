"""Operation primitives for long-lived consumers (v0.8.0).

CLI workflows are short-lived: walk, analyse, print, exit. An interactive
consumer such as the Explorer runs the same operations repeatedly inside a
long-lived session, so it needs progress reporting and cooperative
cancellation without core knowing anything about terminals or UI frameworks.
These primitives stay pure and synchronous — callbacks fire inline on the
calling thread, and cancellation is a structural protocol any consumer can
satisfy (a Textual worker bridges its own cancelled flag; tests use the
concrete :class:`CancellationToken`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Progress:
    """A point-in-time progress report for a long-running operation.

    ``total`` is ``None`` when the amount of work is not known up front.
    """

    phase: str
    completed: int
    total: int | None


ProgressCallback = Callable[[Progress], None]


class OperationCancelled(Exception):
    """Raised when an operation observes a cancelled token at a checkpoint."""


class CancelToken(Protocol):
    """Structural cancellation: anything exposing a ``cancelled`` flag.

    Consumers supply their own implementations (for example, an Explorer
    worker wrapping Textual's cancelled state) without core importing them.
    """

    @property
    def cancelled(self) -> bool: ...


class CancellationToken:
    """Default in-memory :class:`CancelToken`; cancellation is one-way."""

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


def checkpoint(cancel: CancelToken | None) -> None:
    """Raise :class:`OperationCancelled` if ``cancel`` has been cancelled.

    Operations call this at safe boundaries (between files, between phases);
    ``None`` means the caller did not request cancellation support.
    """
    if cancel is not None and cancel.cancelled:
        raise OperationCancelled
