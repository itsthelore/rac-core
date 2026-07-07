"""`rac find --cache` byte-parity with the uncached walk (ADR-110).

One-shot `rac find --cache` serves from the persistent index store instead of a
fresh walk. The contract is that its output is byte-identical to the uncached
`rac find` for every mode, cold (store just written) and warm (store reused),
and that a cold run writes the store for the next invocation. When the store
cannot be written, `load_or_build` returns a fresh `DerivedIndex` and the CLI
serves from that — still byte-identical.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from rac.cli import main


def _decision(ident: str, title: str, *, tags: str, body: str) -> str:
    return (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\ntags: {tags}\n---\n"
        f"# {title}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        f"## Context\n\n{body}\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text(
        _decision("RAC-01JY4M8X2QA1", "Alpha", tags="[security, data-model]", body="shared alpha"),
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text(
        _decision("RAC-01JY4M8X2QB2", "Beta", tags="[performance]", body="shared beta"),
        encoding="utf-8",
    )
    monkeypatch.setenv("RAC_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param([], id="search"),
        pytest.param(["--type", "decision"], id="type"),
        pytest.param(["--tag", "security"], id="tag"),
        pytest.param(["--explain"], id="explain"),
        pytest.param(["--decisions"], id="decisions"),
    ],
)
def test_find_cache_is_byte_identical_to_the_walk(corpus, extra):
    base = ["find", "shared", str(corpus), "--json"]
    rc_walk, walk = _run(base + extra)
    rc_cold, cold = _run(base + ["--cache"] + extra)  # cold miss: builds + writes the store
    rc_warm, warm = _run(base + ["--cache"] + extra)  # warm hit: served from the store
    assert rc_walk == rc_cold == rc_warm == 0
    assert walk == cold, "cached (cold) output must equal the uncached walk"
    assert cold == warm, "warm store-served output must equal the cold run"


def test_cold_cache_run_writes_the_store(corpus):
    from rac.services.index_store import store_root

    _run(["find", "shared", str(corpus), "--json", "--cache"])
    root = store_root(corpus / "cache")
    assert root.exists() and any(root.iterdir()), "a cold --cache run must persist the store"


def test_cache_falls_back_to_fresh_when_store_unwritable(corpus, monkeypatch):
    # When the store can't be written, load_or_build returns a fresh DerivedIndex
    # and the CLI serves from that — output must still equal the walk.
    from rac.services.derived_cache import DerivedIndexCache

    monkeypatch.setattr(DerivedIndexCache, "_write_store", lambda self, h, d: False)
    rc_walk, walk = _run(["find", "shared", str(corpus), "--json"])
    rc_cache, cached = _run(["find", "shared", str(corpus), "--json", "--cache"])
    assert rc_walk == rc_cache == 0
    assert walk == cached


def test_top_level_composes_with_cache(corpus):
    # --cache honours --top-level (its own content-hash / store); still identical.
    base = ["find", "shared", str(corpus), "--json", "--top-level"]
    rc_walk, walk = _run(base)
    rc_cache, cached = _run(base + ["--cache"])
    assert rc_walk == rc_cache == 0
    assert walk == cached
