"""Tests for rac.core.idgen — opaque artifact ID generation (ADR-026).

The generator must be branch-safe and offline: deterministic under injected
clock/entropy, collision-resistant under real entropy, Crockford-canonical,
and time-sortable across millisecond ticks.
"""

from __future__ import annotations

import re

from rac.core.idgen import ALPHABET, SUFFIX_LENGTH, generate_id
from rac.core.metadata import is_valid_id

CANONICAL = re.compile(r"^RAC-[0-9A-HJKMNP-TV-Z]{12}$")


def test_format_is_canonical():
    artifact_id = generate_id("RAC")
    assert CANONICAL.match(artifact_id)
    assert is_valid_id(artifact_id)


def test_suffix_uses_only_crockford_alphabet():
    suffix = generate_id("RAC").split("-", 1)[1]
    assert len(suffix) == SUFFIX_LENGTH
    assert all(c in ALPHABET for c in suffix)
    assert not any(c in "ILOU" for c in suffix)


def test_repository_key_prefixes_id():
    assert generate_id("PROJ").startswith("PROJ-")


def test_deterministic_under_injected_clock_and_entropy():
    a = generate_id("RAC", clock=lambda: 1750000000.0, entropy=lambda bits: 12345)
    b = generate_id("RAC", clock=lambda: 1750000000.0, entropy=lambda bits: 12345)
    assert a == b


def test_distinct_entropy_distinct_ids_same_millisecond():
    def clock() -> float:
        return 1750000000.0

    a = generate_id("RAC", clock=clock, entropy=lambda bits: 1)
    b = generate_id("RAC", clock=clock, entropy=lambda bits: 2)
    assert a != b


def test_time_sortable_across_ticks():
    early = generate_id("RAC", clock=lambda: 1750000000.0, entropy=lambda bits: 0)
    late = generate_id("RAC", clock=lambda: 1750000999.0, entropy=lambda bits: 0)
    assert early < late


def test_unique_across_millisecond_ticks():
    # Uniqueness within one millisecond is the *caller's* job (index check +
    # regenerate in rac new; dedupe in batch tooling) — the generator itself
    # guarantees distinct IDs across ticks even with identical entropy.
    ids = {
        generate_id("RAC", clock=lambda ms=ms: ms / 1000.0, entropy=lambda bits: 7)
        for ms in range(1_750_000_000_000, 1_750_000_002_000)
    }
    assert len(ids) == 2000
