"""`rac` arm — deterministic typed retrieval via the system under test. STUB.

This arm assembles grounding by calling RAC's deterministic, typed retrieval
surface rather than embedding similarity. It is the layer whose value the whole
benchmark exists to test, so it gets NO special treatment: same answering model,
same scaffold, one symmetric grounding opportunity.

The thesis is that typed retrieval + relationship traversal preserves exactly
what naive_rag severs — notably supersession — by following `supersedes` edges
instead of hoping the superseding artifact lands in top-k.
"""

from __future__ import annotations

from .base import CorpusArtifact, GroundingContext, Provider, Task


class RacProvider(Provider):
    name = "rac"

    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        # TODO(rac-arm): index the corpus through RAC. In production this calls
        # the `lore` MCP server: `get_summary` once to learn what exists, then
        # `search_artifacts(query, type="decision")` to find candidates. For the
        # offline harness, shell out to the pinned `rac` CLI instead
        # (`rac find <q> . --type decision --json`).
        raise NotImplementedError("rac arm is a stub this pass")

    def respond(self, task: Task):
        # TODO(rac-arm): for each candidate decision, call `get_related(id)` (MCP)
        # or `rac relationships . --json` (CLI) and FOLLOW the `supersedes` edges
        # so the superseding decision replaces the one it supersedes. Assemble the
        # resolved, typed set into a GroundingContext and feed the held-constant
        # answering model. This is where the thesis is won or lost: deterministic
        # relationship traversal vs. embedding recall.
        raise NotImplementedError("rac arm is a stub this pass")
