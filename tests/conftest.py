"""Shared pytest fixtures: paths to the Markdown fixture files."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def fixture_path(*parts: str) -> str:
    return str(FIXTURES.joinpath(*parts))


@pytest.fixture(autouse=True)
def _isolated_xdg(tmp_path_factory, monkeypatch):
    """Point XDG config/state/cache at a temp dir for every test.

    No test may read or write real user state — and with a live PostHog key
    in source (ADR-041), no test run may ever find a developer's consent
    record and phone home. The cache isolation is load-bearing since the
    persistent cache went default-on (ADR-112): a test driving the CLI would
    otherwise write to the developer's real ``~/.cache/rac``. Tests that need
    specific locations still override these variables locally.
    """
    base = tmp_path_factory.mktemp("xdg")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(base / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(base / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(base / "cache"))
    monkeypatch.delenv("RAC_CACHE_DIR", raising=False)
    monkeypatch.delenv("RAC_NO_CACHE", raising=False)
