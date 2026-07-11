#!/usr/bin/env python3
"""Generate git-recency test vectors from the oracle (`rac.services.recency`).

REGENERABLE: these vectors are computed against THIS repository's real git
history for a few stable, long-committed paths. If those files are re-committed
(their `%cI` changes) the `last_committed` / `age_days` values shift — rerun:

    .venv-oracle/bin/python rust/spec/gen_vectors_gitinfo.py

Determinism: a fixed `reference` instant pins `age_days`; boundary thresholds
are derived from each path's age so the strict-greater `stale` rule
(PORT-CONTRACT.d/08 §4.3) is exercised regardless of the actual dates.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from rac.services import recency

REPO = Path(__file__).resolve().parents[2]  # /home/user/rac-core
OUT = Path(__file__).resolve().parents[1] / "rac-engine/tests/vectors/gitinfo.json"

# Fixed reference instant (UTC). Chosen after all commit dates so ages are
# positive; any fixed value works — it is recorded for the Rust replay.
REFERENCE = datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC)

# Stable, long-committed paths (repo-relative), plus one deliberately untracked.
TRACKED_PATHS = [
    "README.md",
    "CLAUDE.md",
    "rac/prompts/rac-agent-session-start.md",
    "rac/prompts/rac-agent-commit-guidelines.md",
    "rust/PORT-CONTRACT.md",
    "rust/PORT-CONTRACT.d/09-walk-stats-export-review-schema.md",
]
UNTRACKED_PATH = "this-file-does-not-exist-parity-xyz.md"


def raw_git_cI(pathspec: str) -> str | None:
    """The verbatim `git log -1 --format=%cI` string for a repo-relative path."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", pathspec],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    stamp = result.stdout.strip()
    return stamp or None


def main() -> None:
    repo_root = recency._repository_root(str(REPO))
    if repo_root is None:
        raise SystemExit("generator must run inside the rac-core git repo")

    paths_out = []
    for rel in TRACKED_PATHS:
        abspath = str(REPO / rel)
        last = recency._last_committed(repo_root, abspath)
        raw = raw_git_cI(rel)
        if last is None or raw is None:
            raise SystemExit(f"expected {rel} to be committed; got None")
        # The oracle parses %cI then re-isoformats; for a standard offset this is
        # byte-identical to the raw git string (the Rust port keeps it verbatim).
        assert last.isoformat() == raw, f"{rel}: {last.isoformat()!r} != {raw!r}"
        st = recency.staleness(last, threshold_days=recency.DEFAULT_STALE_AFTER_DAYS, reference=REFERENCE)
        age = st.age_days
        boundary = []
        for threshold in (age - 1, age, age + 1):
            b = recency.staleness(last, threshold_days=threshold, reference=REFERENCE)
            boundary.append({"threshold": threshold, "stale": b.stale})
        paths_out.append(
            {
                "path": rel,
                "tracked": True,
                "last_committed": raw,
                "age_days": age,
                "default_threshold": recency.DEFAULT_STALE_AFTER_DAYS,
                "default_stale": st.stale,
                "boundary": boundary,
            }
        )

    # Untracked path -> None everywhere.
    abspath = str(REPO / UNTRACKED_PATH)
    last = recency._last_committed(repo_root, abspath)
    st = recency.staleness(last, reference=REFERENCE)
    paths_out.append(
        {
            "path": UNTRACKED_PATH,
            "tracked": False,
            "last_committed": None,
            "age_days": st.age_days,
            "default_threshold": recency.DEFAULT_STALE_AFTER_DAYS,
            "default_stale": st.stale,
            "boundary": [],
        }
    )

    payload = {
        "regenerable": True,
        "note": "computed against rac-core git history; rerun gen_vectors_gitinfo.py if paths are re-committed",
        "reference_iso": REFERENCE.isoformat(),
        "reference_epoch": int(REFERENCE.timestamp()),
        "paths": paths_out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(paths_out)} paths, reference {REFERENCE.isoformat()})")


if __name__ == "__main__":
    main()
