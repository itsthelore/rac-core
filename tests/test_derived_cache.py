"""Derived-index cache — content addressing, byte-parity, freshness (ADR-099).

Initiative 2 of ``lore-at-team-scale`` (itsthelore/rac-core#264). The cache
persists the expensive derived structures keyed on a corpus content hash. These
tests hold the requirement's contract (``rac-derived-index-cache``):

- **Byte-parity (REQ-002):** cache-on output is byte-identical to cache-off for
  every MCP tool and at the shared service seams the CLI uses.
- **Content addressing + freshness (REQ-004/REQ-006):** any byte change forces a
  rebuild and the next call reflects it; there is no time- or event-based path.
- **Disposable, never authoritative (REQ-003):** deleting the cache — or a
  corrupt or unwritable one — costs only latency, never correctness.
- **Latency floor (REQ-007):** repeated unchanged-corpus calls skip
  re-tokenisation, shown deterministically by a work counter.
"""

from __future__ import annotations

import asyncio
import shutil

import pytest
from conftest import fixture_path

from asdecided import cli
from asdecided.core.corpus import corpus_content_hash
from asdecided.services import derived_cache
from asdecided.services.derived_cache import (
    DerivedIndexCache,
    build_derived_index,
    from_json_obj,
    to_json_obj,
)
from asdecided.services.index import build_repository_index
from asdecided.services.resolve import (
    field_tokens_for_entries,
    find_decisions,
    find_decisions_in,
    live_decision_paths,
    search_index,
)

CORPUS = fixture_path("mcp", "corpus")

DEC = "RAC-MCPDEC000001"
REQ = "RAC-MCPREQ000001"

TOOL_CALLS: tuple[tuple[str, dict], ...] = (
    ("get_artifact", {"id": DEC}),
    ("search_artifacts", {"query": "RAC-MCP"}),
    ("find_decisions", {"topic": "RAC"}),
    ("find_decisions", {"topic": "", "path": "src/asdecided/mcp/server.py"}),
    ("get_related", {"id": REQ}),
    ("get_summary", {}),
)

# --- corpus content hash (REQ-001, REQ-004) ----------------------------------


def _make_corpus(root, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")


def test_corpus_hash_is_stable_across_runs(tmp_path):
    root = tmp_path / "c"
    _make_corpus(root, {"a.md": "# A\n\nbody\n", "b.md": "# B\n\nmore\n"})
    assert corpus_content_hash(str(root)) == corpus_content_hash(str(root))


def test_corpus_hash_changes_on_any_byte_change(tmp_path):
    root = tmp_path / "c"
    _make_corpus(root, {"a.md": "# A\n\nbody\n"})
    before = corpus_content_hash(str(root))
    (root / "a.md").write_text("# A\n\nbody edited\n", encoding="utf-8")
    assert corpus_content_hash(str(root)) != before


def test_corpus_hash_changes_on_add_remove_rename(tmp_path):
    root = tmp_path / "c"
    _make_corpus(root, {"a.md": "# A\n"})
    base = corpus_content_hash(str(root))
    (root / "b.md").write_text("# B\n", encoding="utf-8")
    added = corpus_content_hash(str(root))
    assert added != base
    (root / "b.md").unlink()
    assert corpus_content_hash(str(root)) == base  # removal returns to base
    (root / "a.md").rename(root / "z.md")
    assert corpus_content_hash(str(root)) != base  # rename changes the path set


# --- serialization round-trip (REQ-002) --------------------------------------


def test_derived_index_json_round_trip_is_identity():
    derived = build_derived_index(CORPUS)
    assert from_json_obj(to_json_obj(derived)) == derived


# --- byte-parity across MCP tools (REQ-002) ----------------------------------


def _tool_text(server, name, args) -> str:
    content, _structured = asyncio.run(server.call_tool(name, args))
    return content[0].text


def test_cache_on_matches_cache_off_across_all_tools(tmp_path):
    from asdecided.mcp.server import build_server

    off = build_server(CORPUS)
    on = build_server(CORPUS, cache=DerivedIndexCache(tmp_path / "cache"))
    for name, args in TOOL_CALLS:
        assert _tool_text(off, name, args) == _tool_text(on, name, args), f"parity drift: {name}"


# --- byte-parity at the CLI-facing service seams (REQ-002) -------------------


def test_search_index_parity_with_injected_field_tokens():
    entries = build_repository_index(CORPUS).artifacts
    fresh = search_index(entries, "RAC-MCP")
    injected = search_index(
        entries, "RAC-MCP", field_tokens_by_path=field_tokens_for_entries(entries)
    )
    assert fresh.to_dict() == injected.to_dict()


def test_find_decisions_parity_with_derived_core():
    from asdecided.core.corpus import walk_corpus

    entries = list(walk_corpus(CORPUS))
    index = build_repository_index(CORPUS).artifacts
    fresh = find_decisions(CORPUS, "RAC")
    derived = find_decisions_in(
        index,
        live_decision_paths(entries),
        "RAC",
        field_tokens_by_path=field_tokens_for_entries(index),
    )
    assert fresh.to_dict() == derived.to_dict()


# --- cache hit / miss, corruption, unwritable (REQ-003) ----------------------


def test_second_call_is_a_hit_not_a_rebuild(tmp_path, monkeypatch):
    # The cold miss now builds through the parallel cold-build seam (ADR-107); the
    # rebuild counter observes that entrypoint. Intent is unchanged: the second
    # unchanged-corpus call must read the store, not rebuild.
    from asdecided.services import parallel_build

    builds: list[int] = []
    original = parallel_build.build_derived_index_parallel
    monkeypatch.setattr(
        parallel_build,
        "build_derived_index_parallel",
        lambda *a, **k: (builds.append(1), original(*a, **k))[1],
    )
    cache = DerivedIndexCache(tmp_path / "cache")
    first = cache.load_or_build(CORPUS)
    second = cache.load_or_build(CORPUS)
    assert builds == [1], "the second unchanged-corpus call must read the cache, not rebuild"
    assert first == second


def test_corrupt_cache_file_is_a_miss_not_a_failure(tmp_path):
    cache = DerivedIndexCache(tmp_path / "cache")
    expected = cache.load_or_build(CORPUS)
    # Corrupt the on-disk file; the next load must rebuild transparently.
    cache_file = next((tmp_path / "cache").glob("*.json"))
    cache_file.write_text("{not valid json", encoding="utf-8")
    assert cache.load_or_build(CORPUS) == expected


def test_schema_mismatch_is_a_miss(tmp_path):
    cache = DerivedIndexCache(tmp_path / "cache")
    expected = cache.load_or_build(CORPUS)
    cache_file = next((tmp_path / "cache").glob("*.json"))
    obj = to_json_obj(expected)
    obj["schema_version"] = "999"
    cache_file.write_text(__import__("json").dumps(obj), encoding="utf-8")
    assert cache.load_or_build(CORPUS) == expected


def test_unwritable_cache_dir_degrades_to_build(tmp_path):
    # Point the cache dir *inside* a regular file: it can never be created.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    cache = DerivedIndexCache(blocker / "cache")
    result = cache.load_or_build(CORPUS)
    assert result == build_derived_index(CORPUS)  # correct output, no raise


# --- freshness + disposability (REQ-006, REQ-003) ----------------------------


def test_edit_forces_rebuild_and_next_call_reflects_it(tmp_path):
    root = tmp_path / "corpus"
    shutil.copytree(CORPUS, root)
    cache = DerivedIndexCache(tmp_path / "cache")
    before = cache.load_or_build(str(root))

    # Edit one artifact's title; the corpus hash changes, so the next call must
    # reflect the edit rather than serve the cached structures.
    target = next(p for p in root.rglob("*.md"))
    target.write_text(
        target.read_text(encoding="utf-8").replace("# ", "# Edited ", 1), encoding="utf-8"
    )
    after = cache.load_or_build(str(root))
    assert after != before
    assert after == build_derived_index(str(root))


def test_deleting_cache_mid_session_rebuilds_identically(tmp_path):
    cache_dir = tmp_path / "cache"
    cache = DerivedIndexCache(cache_dir)
    first = cache.load_or_build(CORPUS)
    shutil.rmtree(cache_dir)  # disposable: gone mid-session
    second = cache.load_or_build(CORPUS)
    assert second == first


# --- latency floor: repeated calls skip re-tokenisation (REQ-007) ------------


def test_warm_cache_skips_retokenization(tmp_path, monkeypatch):
    # A deterministic larger corpus so the floor is meaningful.
    root = tmp_path / "big"
    _make_corpus(
        root, {f"doc-{i:03d}.md": f"# Doc {i}\n\nalpha beta gamma {i}\n" for i in range(200)}
    )

    tokenizations: list[int] = []
    original = derived_cache.field_tokens_for_entries
    monkeypatch.setattr(
        derived_cache,
        "field_tokens_for_entries",
        lambda entries: (tokenizations.append(len(entries)), original(entries))[1],
    )
    cache = DerivedIndexCache(tmp_path / "cache")
    cache.load_or_build(str(root))  # cold: tokenizes all 200
    cache.load_or_build(str(root))  # warm: tokenizes nothing
    cache.load_or_build(str(root))  # warm: tokenizes nothing
    assert tokenizations == [200], "warm unchanged-corpus calls must skip re-tokenisation"


# --- CLI wiring (REQ-001) ----------------------------------------------------


def test_cache_flag_defaults_on_with_no_cache_escape():
    # ADR-112: default-on across all three surfaces, --no-cache restores the
    # walk, --cache stays parseable as an explicit affirmation, and --verify
    # (the full-hash floor) exists on find/validate but not mcp.
    parser = cli.build_parser()
    for argv in (["mcp", "--root", CORPUS], ["find", "q", CORPUS], ["validate", CORPUS]):
        assert parser.parse_args(argv).cache is True, f"{argv[0]} must default cache-on"
        assert parser.parse_args(argv + ["--cache"]).cache is True
        assert parser.parse_args(argv + ["--no-cache"]).cache is False
    assert parser.parse_args(["find", "q", CORPUS, "--verify"]).verify is True
    assert parser.parse_args(["validate", CORPUS, "--verify"]).verify is True
    with pytest.raises(SystemExit):
        parser.parse_args(["mcp", "--root", CORPUS, "--verify"])


def test_rac_no_cache_env_disables_the_default(monkeypatch):
    parser = cli.build_parser()
    args = parser.parse_args(["find", "q", CORPUS])
    monkeypatch.delenv("DECIDED_NO_CACHE", raising=False)
    assert cli._cache_enabled(args) is True
    monkeypatch.setenv("DECIDED_NO_CACHE", "1")
    assert cli._cache_enabled(args) is False


def test_run_server_cache_enabled_builds_a_cache(monkeypatch):
    from asdecided.mcp import server as mcp_server

    captured: dict = {}

    class _FakeServer:
        def run(self, transport: str) -> None:
            pass

    def _fake_build(root, *, budget, recorder, audit_recorder, cache):
        captured["cache"] = cache
        return _FakeServer()

    monkeypatch.setattr(mcp_server, "build_server", _fake_build)
    monkeypatch.setattr(mcp_server, "_maybe_start_sharing", lambda *a, **k: None)
    monkeypatch.setattr(mcp_server, "_check_corpus", lambda *a, **k: None)
    assert mcp_server.run_server(CORPUS) == 0, "cache_enabled must default on (ADR-112)"
    assert isinstance(captured["cache"], DerivedIndexCache)
    captured.clear()
    assert mcp_server.run_server(CORPUS, cache_enabled=False) == 0
    assert captured["cache"] is None, "cache_enabled=False must build no cache"
