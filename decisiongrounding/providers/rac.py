"""`rac` arm — deterministic typed retrieval via the system under test.

This arm assembles grounding by calling RAC's deterministic, typed retrieval
surface rather than embedding similarity. It is the layer whose value the whole
benchmark exists to test, so it gets NO special treatment: same answering model,
same scaffold, one symmetric grounding opportunity.

RAC is treated as an EXTERNAL TOOL, never a Python import (ADR-0001): the arm
shells out to the pinned `rac` CLI (`rac find … --json`, `rac relationships …
--json`). The thesis is that typed retrieval + relationship traversal preserves
exactly what naive_rag severs — notably supersession — by FOLLOWING `supersedes`
edges instead of hoping the superseding artifact lands in top-k.

Requires the `rac` CLI on PATH (or set RAC_BIN). It does not run in the offline
demo; install `rac` to include this arm in a comparison.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import (
    SCAFFOLD,
    CorpusArtifact,
    GroundingContext,
    Provider,
    Task,
    estimate_tokens,
)
from .grounding_format import format_block


def resolve_supersedes(
    matched_ids: list[str],
    supersedes_edges: list[tuple[str, str]],
    corpus_ids: set[str],
    top_k: int,
) -> list[str]:
    """Follow `supersedes` edges so a superseding decision replaces the one it
    supersedes. Pure and deterministic — the heart of the typed-retrieval thesis.

    `supersedes_edges` are (source, target) pairs meaning source supersedes
    target. For each matched decision that is superseded by another decision in
    the corpus, swap in its (transitive) live successor and drop the stale one.
    Order is preserved (match rank), then capped to `top_k`.
    """
    superseded_by: dict[str, str] = {
        tgt: src for (src, tgt) in supersedes_edges if src in corpus_ids
    }

    def live(artifact_id: str, _seen: set[str] | None = None) -> str:
        seen = _seen or set()
        while artifact_id in superseded_by and artifact_id not in seen:
            seen.add(artifact_id)
            artifact_id = superseded_by[artifact_id]
        return artifact_id

    resolved: list[str] = []
    for mid in matched_ids:
        live_id = live(mid)
        if live_id not in resolved:
            resolved.append(live_id)
    return resolved[:top_k]


class RacProvider(Provider):
    name = "rac"

    def __init__(self, answering_model, top_k: int = 4):
        super().__init__(answering_model)
        self.top_k = top_k  # decision budget, parity with naive_rag's top-k
        self._dir: Path | None = None
        self._by_id: dict[str, CorpusArtifact] = {}

    @staticmethod
    def _bin() -> str:
        return os.environ.get("RAC_BIN", "rac")

    def _run(self, *args: str) -> dict:
        rac = self._bin()
        if shutil.which(rac) is None:
            raise RuntimeError(
                f"rac CLI not found ({rac!r}). Install `rac` or set RAC_BIN to "
                "include the rac arm. It does not run in the offline demo."
            )
        out = subprocess.run(
            [rac, *args], capture_output=True, text=True, check=True
        ).stdout
        return json.loads(out)

    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        # Write the corpus to a temp dir so the external `rac` CLI can index it.
        self._by_id = {a.id: a for a in corpus}
        tmp = Path(tempfile.mkdtemp(prefix="dg-rac-"))
        for a in corpus:
            (tmp / f"{a.id}.md").write_text(a.text, encoding="utf-8")
        self._dir = tmp
        self._grounding = GroundingContext(text="", artifacts_supplied=(), token_estimate=0)

    def respond(self, task: Task):
        if self._dir is None:
            raise RuntimeError("rac arm: prepare() must run before respond()")
        query = f"{task.prompt} {task.proposed_action}"

        # 1. Typed candidate decisions, ranked by rac's deterministic search.
        find = self._run("find", query, str(self._dir), "--type", "decision", "--json")
        matched = [m.get("id") for m in find.get("matches", []) if m.get("id")]

        # 2. Relationship graph → supersedes edges (source supersedes target).
        rels = self._run("relationships", str(self._dir), "--json")
        edges = _extract_supersedes_edges(rels)

        # 3. Follow the edges: replace superseded decisions with live successors.
        corpus_ids = set(self._by_id)
        resolved = resolve_supersedes(matched, edges, corpus_ids, self.top_k)

        blocks = [
            format_block(aid, self._by_id[aid].type, self._by_id[aid].text)
            for aid in resolved
            if aid in self._by_id
        ]
        text = "\n".join(blocks)
        self._grounding = GroundingContext(
            text=text,
            artifacts_supplied=tuple(resolved),
            token_estimate=estimate_tokens(text),
        )
        return self.answering_model.respond(SCAFFOLD, self._grounding, task)


def _extract_supersedes_edges(rels_json: dict) -> list[tuple[str, str]]:
    """Pull (source, target) supersedes pairs from `rac relationships --json`.

    Defensive against shape drift across rac versions: handles both a flat
    relationships list (entries with relationship == "supersedes") and an
    artifacts[] report carrying a per-artifact `relationships.supersedes` list.
    TODO(rac-arm): pin and verify against the installed rac version's JSON.
    """
    edges: list[tuple[str, str]] = []

    for rel in rels_json.get("relationships", []) or []:
        if rel.get("relationship") == "supersedes":
            src, tgt = rel.get("source"), rel.get("target")
            if src and tgt:
                edges.append((src, tgt))

    for art in rels_json.get("artifacts", []) or []:
        src = art.get("id")
        targets = (art.get("relationships") or {}).get("supersedes") or []
        for tgt in targets:
            if src and tgt:
                edges.append((src, tgt))

    return edges
