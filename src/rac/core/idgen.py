"""Opaque artifact ID generation (ADR-026, v0.7.11).

Branch-safe and offline: no shared allocation state, no network, no git. An ID
is ``<REPOSITORY_KEY>-<SUFFIX>`` where the suffix is 12 characters of Crockford
base32 (uppercase, no I/L/O/U): an 8-character millisecond-timestamp segment
(time-sortable, ULID-style) followed by a 4-character CSPRNG segment. Two
artifacts created in the same millisecond collide with probability 2^-20;
callers that can see the repository index (``rac new``) additionally check and
regenerate.

``clock`` and ``entropy`` are injectable so tests are deterministic; the
defaults are the real wall clock and ``secrets``.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable

# Crockford base32: no I, L, O, U (visually ambiguous).
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_TIME_CHARS = 8  # 40 bits of millisecond timestamp (wraps ~every 34 years)
_RANDOM_CHARS = 4  # 20 bits of CSPRNG entropy per millisecond tick
SUFFIX_LENGTH = _TIME_CHARS + _RANDOM_CHARS


def _encode(value: int, chars: int) -> str:
    out = []
    for _ in range(chars):
        out.append(ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def generate_id(
    repository_key: str,
    *,
    clock: Callable[[], float] = time.time,
    entropy: Callable[[int], int] = secrets.randbits,
) -> str:
    """One new opaque artifact ID under ``repository_key``.

    The caller is responsible for key validity (``rac init`` owns that
    contract) and for uniqueness against an existing repository where it can
    check one.
    """
    millis = int(clock() * 1000) & ((1 << (_TIME_CHARS * 5)) - 1)
    random_bits = entropy(_RANDOM_CHARS * 5)
    return f"{repository_key}-{_encode(millis, _TIME_CHARS)}{_encode(random_bits, _RANDOM_CHARS)}"
