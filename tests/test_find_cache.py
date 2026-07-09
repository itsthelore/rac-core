"""`rac find` cache byte-parity with the uncached walk (ADR-112, née ADR-110).

One-shot `rac find` serves from the persistent index store by default. The
contract is that its output is byte-identical to `--no-cache` for every mode,
cold (store just written) and warm (store reused), and that a cold run writes
the store for the next invocation. When the store cannot be written,
`load_or_build` returns a fresh `DerivedIndex` and the CLI serves from that —
still byte-identical.
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
    rc_walk, walk = _run(base + ["--no-cache"] + extra)
    rc_cold, cold = _run(base + extra)  # default, cold miss: builds + writes the store
    rc_warm, warm = _run(base + extra)  # default, warm hit: served from the store
    rc_affirm, affirmed = _run(base + ["--cache"] + extra)  # explicit affirmation
    rc_verify, verified = _run(base + ["--verify"] + extra)  # full-hash floor
    assert rc_walk == rc_cold == rc_warm == rc_affirm == rc_verify == 0
    assert walk == cold, "cached (cold) output must equal the --no-cache walk"
    assert cold == warm == affirmed == verified, "every cached mode must serve the same bytes"


def test_cold_default_run_writes_the_store(corpus):
    from rac.services.index_store import store_root

    _run(["find", "shared", str(corpus), "--json"])
    root = store_root(corpus / "cache")
    assert root.exists() and any(root.iterdir()), "a cold default run must persist the store"


def test_no_cache_and_rac_no_cache_write_nothing(corpus, monkeypatch):
    _run(["find", "shared", str(corpus), "--json", "--no-cache"])
    assert not (corpus / "cache").exists(), "--no-cache must not touch the cache dir"
    monkeypatch.setenv("RAC_NO_CACHE", "1")
    _run(["find", "shared", str(corpus), "--json"])
    assert not (corpus / "cache").exists(), "RAC_NO_CACHE must disable the default cache"


def test_cache_falls_back_to_fresh_when_store_unwritable(corpus, monkeypatch):
    # When the store can't be written, load_or_build returns a fresh DerivedIndex
    # and the CLI serves from that — the default path must still equal the walk.
    from rac.services.derived_cache import DerivedIndexCache

    monkeypatch.setattr(DerivedIndexCache, "_write_store", lambda self, h, d: False)
    rc_walk, walk = _run(["find", "shared", str(corpus), "--json", "--no-cache"])
    rc_cache, cached = _run(["find", "shared", str(corpus), "--json"])
    assert rc_walk == rc_cache == 0
    assert walk == cached


def test_s5_rewrite_serves_stale_until_verify(corpus):
    # The accepted S5 miss (ADR-105/ADR-112) through the CLI: a size- and
    # mtime-preserving rewrite is invisible to the warm default run; --verify
    # is the full-hash floor that observes it and repairs the manifest.
    import os

    _run(["find", "shared", str(corpus), "--json"])  # cold: store + manifest written
    target = corpus / "a.md"
    st = target.stat()
    old = target.read_text(encoding="utf-8")
    new = old.replace("shared alpha", "shared aleph")  # same byte length
    assert len(new.encode()) == st.st_size and new != old
    target.write_text(new, encoding="utf-8")
    os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))

    _, stale = _run(["find", "aleph", str(corpus), "--json"])
    assert '"match_count": 0' in stale, "the S5 rewrite is the accepted stat miss"
    _, verified = _run(["find", "aleph", str(corpus), "--json", "--verify"])
    assert '"match_count": 1' in verified, "--verify must observe the rewrite"
    _, after = _run(["find", "aleph", str(corpus), "--json"])
    assert '"match_count": 1' in after, "verify must repair the manifest for later runs"


def test_default_find_survives_a_homeless_environment(corpus, monkeypatch):
    # Default-on must never fail a query because no cache location resolves
    # (ADR-112 degrade-never-fail): no HOME, no XDG_CACHE_HOME, no RAC_CACHE_DIR.
    from pathlib import Path

    def _no_home() -> Path:
        raise RuntimeError("no usable home directory")

    monkeypatch.delenv("RAC_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(_no_home))
    rc, out = _run(["find", "shared", str(corpus), "--json"])
    assert rc == 0 and '"match_count": 2' in out


def test_top_level_composes_with_cache(corpus):
    # The default cache honours --top-level (its own content-hash / store /
    # manifest key); still identical to the walk.
    base = ["find", "shared", str(corpus), "--json", "--top-level"]
    rc_walk, walk = _run(base + ["--no-cache"])
    rc_cache, cached = _run(base)
    assert rc_walk == rc_cache == 0
    assert walk == cached
