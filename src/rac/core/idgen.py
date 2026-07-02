"""Opaque artifact ID generation (ADR-026).

An ID is ``<REPOSITORY_KEY>-<SUFFIX>``. The 12-character suffix is Crockford
base32 (uppercase, no I/L/O/U) split into two segments: an 8-character
millisecond timestamp (ULID-style, so IDs sort by creation time) followed by a
4-character CSPRNG segment. Generation is branch-safe and offline — no shared
allocation state, no git, no network — so two branches can mint IDs without
coordinating. Within a single millisecond the 20 random bits give a 2^-20
collision probability; a caller that can see the repository index (``rac new``)
additionally checks and regenerates on the rare clash.

``clock`` and ``entropy`` are injected (defaulting to the real wall clock and
``secrets``) so callers and tests can make generation fully deterministic
without the generator itself reaching for global state.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable

# Crockford base32 — the four visually ambiguous letters I, L, O, U are omitted.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Suffix layout. Each base32 character carries 5 bits, so the timestamp segment
# holds 40 bits of milliseconds (wraps roughly every 34 years) and the random
# segment holds 20 bits of entropy per millisecond tick.
_TIME_CHARS = 8
_RANDOM_CHARS = 4
_BITS_PER_CHAR = 5
SUFFIX_LENGTH = _TIME_CHARS + _RANDOM_CHARS


def _encode(value: int, chars: int) -> str:
    """Big-endian Crockford base32: ``value`` as exactly ``chars`` characters.

    The low 5 bits map to the least-significant (rightmost) character, so the
    digits are produced right-to-left and reversed into most-significant-first
    order — which is what keeps the timestamp segment lexicographically sortable.
    """
    digits: list[str] = []
    for _ in range(chars):
        digits.append(ALPHABET[value & 0x1F])
        value >>= _BITS_PER_CHAR
    return "".join(reversed(digits))


def generate_id(
    repository_key: str,
    *,
    clock: Callable[[], float] = time.time,
    entropy: Callable[[int], int] = secrets.randbits,
) -> str:
    """Mint one new opaque artifact ID under ``repository_key``.

    The caller owns key validity (``rac init`` defines the contract) and owns
    within-millisecond uniqueness where it can see an index; the generator only
    guarantees distinct IDs across distinct millisecond ticks.
    """
    time_bits = _TIME_CHARS * _BITS_PER_CHAR
    millis = int(clock() * 1000) & ((1 << time_bits) - 1)
    random_bits = entropy(_RANDOM_CHARS * _BITS_PER_CHAR)
    suffix = _encode(millis, _TIME_CHARS) + _encode(random_bits, _RANDOM_CHARS)
    return f"{repository_key}-{suffix}"
