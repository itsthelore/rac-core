"""Idempotent content-hash processing (v0.23.0, WS8).

Within one CLI invocation a `CorpusCache` content-hashes each artifact (full
on-disk source bytes; ADR-032's collect_corpus seam) so phases after the first
reuse the parsed snapshot instead of reparsing — a per-invocation performance
path only. These tests pin: the hash is source-only and mtime-independent
(REQ-002); the short-circuit reuses unchanged artifacts and reprocesses only an
edited one (REQ-001); derived output is byte-identical to a full reprocess and
stable across runs (REQ-003); and the MCP serving path is never cached — it
re-reads on every call (REQ-004, ADR-032).
"""

from __future__ import annotations

import asyncio
import json
import os

from asdecided.core.corpus import CorpusCache, content_hash, walk_corpus
from asdecided.mcp.server import build_server
from asdecided.services.doctor import diagnose
from asdecided.services.relationships import validate_relationships
from asdecided.services.validate import validate_directory

DECISION = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n# {title}\n\n"
    "## Status\n\n{status}\n\n## Context\n\nWhy.\n\n## Decision\n\nDo it.\n\n"
    "## Consequences\n\nFine.\n"
)


def _decision(root, name: str, aid: str, *, status: str = "Accepted") -> None:
    (root / f"{name}.md").write_text(
        DECISION.format(id=aid, title=name, status=status), encoding="utf-8"
    )


def _corpus(root) -> None:
    _decision(root, "alpha", "RAC-HASHAAAAAAA1")
    _decision(root, "bravo", "RAC-HASHAAAAAAA2")
    _decision(root, "charlie", "RAC-HASHAAAAAAA3")


# --- content hash: source-only, mtime-independent (REQ-002) ------------------


def test_content_hash_is_source_only_and_mtime_independent(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("hello world", encoding="utf-8")
    original = content_hash(path)

    # Touching the file (new mtime, same bytes) does not change the hash.
    future = 2_000_000_000.0
    os.utime(path, (future, future))
    assert content_hash(path) == original

    # A whitespace-only edit changes the hash (any byte change does).
    path.write_text("hello world ", encoding="utf-8")
    assert content_hash(path) != original


def test_content_hash_degrades_for_unreadable_path(tmp_path):
    # A path that cannot be read hashes to a stable sentinel rather than raising.
    missing = tmp_path / "gone.md"
    assert content_hash(missing) == content_hash(missing)


# --- short-circuit: reuse unchanged, reprocess only the edited (REQ-001) -----


def test_cache_reuses_unchanged_and_reprocesses_only_edited(tmp_path):
    _corpus(tmp_path)
    cache = CorpusCache()

    first = cache.collect(str(tmp_path))
    assert len(first) == 3
    assert cache.reprocessed == 3
    assert cache.reused == 0

    # Second collect on an unchanged corpus reparses nothing; entries are reused
    # by identity (the very objects parsed on the first pass).
    reprocessed_before = cache.reprocessed
    second = cache.collect(str(tmp_path))
    assert cache.reprocessed - reprocessed_before == 0
    assert cache.reused == 3
    assert all(s is f for s, f in zip(second, first, strict=True))

    # Editing exactly one artifact reprocesses exactly that one.
    reprocessed_before = cache.reprocessed
    _decision(tmp_path, "bravo", "RAC-HASHAAAAAAA2", status="Superseded")
    third = cache.collect(str(tmp_path))
    assert cache.reprocessed - reprocessed_before == 1
    # alpha and charlie are still the original objects; bravo is freshly parsed.
    assert third[0] is first[0]
    assert third[2] is first[2]
    assert third[1] is not first[1]


# --- byte-identical to a full reprocess, stable across runs (REQ-003) --------


def test_short_circuit_output_is_byte_identical_to_full_reprocess(tmp_path):
    _corpus(tmp_path)
    cache = CorpusCache()
    cache.collect(str(tmp_path))  # warm: every entry now reused on the cached path

    # Validation: cached snapshot vs a fresh full walk.
    assert (
        validate_directory(str(tmp_path), cache=cache).to_dict()
        == validate_directory(str(tmp_path)).to_dict()
    )

    # Relationship integrity: cached snapshot vs a fresh full walk.
    cached_rel = validate_relationships(str(tmp_path), cache=cache)
    fresh_rel = validate_relationships(str(tmp_path))
    assert cached_rel.relationships_checked == fresh_rel.relationships_checked
    assert cached_rel.issues == fresh_rel.issues


def test_doctor_report_is_idempotent_across_runs(tmp_path):
    # diagnose shares one cache across its phases; its report is byte-stable on
    # repeated runs over an unchanged corpus.
    _corpus(tmp_path)
    assert diagnose(str(tmp_path)).to_dict() == diagnose(str(tmp_path)).to_dict()


def test_cached_snapshot_matches_fresh_walk(tmp_path):
    # The short-circuit never alters the snapshot: cached entries classify and
    # parse identically to a fresh walk, in the same order.
    _corpus(tmp_path)
    cache = CorpusCache()
    cache.collect(str(tmp_path))
    cached = cache.collect(str(tmp_path))  # fully reused
    fresh = list(walk_corpus(str(tmp_path)))
    assert [(e.path, e.artifact_type) for e in cached] == [(e.path, e.artifact_type) for e in fresh]
    assert [e.product.sections for e in cached] == [e.product.sections for e in fresh]


# --- the MCP serving path is never cached (REQ-004, ADR-032) -----------------


def test_mcp_serving_path_reflects_interleaved_edit(tmp_path):
    # The server re-reads on every call and does not use the WS8 cache: an edit
    # between two calls is visible in the second response.
    _decision(tmp_path, "delta", "RAC-HASHAAAAAAA4", status="Proposed")
    server = build_server(str(tmp_path))

    before = json.loads(
        asyncio.run(server.call_tool("get_artifact", {"id": "RAC-HASHAAAAAAA4"}))[0][0].text
    )
    _decision(tmp_path, "delta", "RAC-HASHAAAAAAA4", status="Accepted")
    after = json.loads(
        asyncio.run(server.call_tool("get_artifact", {"id": "RAC-HASHAAAAAAA4"}))[0][0].text
    )

    assert "Proposed" in before["content"]
    assert "Accepted" in after["content"]
    assert before["content"] != after["content"]
