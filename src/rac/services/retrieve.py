"""Compound deterministic grounding retrieval (ADR-113, grounding-retrieval-surface).

One call answers "what is the best grounding this corpus offers for a task":
keyword and tag discovery over the index (ADR-037/038/109), scope binding when a
code path is supplied (the ``decisions-for`` semantics — declared ``## Applies
To`` coverage, which binds regardless of keyword match), supersedes resolution to
live successors along the validated acyclic graph, the existing BM25F+RRF
ranking (ADR-078), then a top-k cut with per-item excerpt shaping under the
ADR-033 character budget. Every returned item carries provenance — the discovery
channels, the matched scope entry, the replaced retired ids, and the explain-hit
evidence — so a deterministic scorer can measure governing recall.

This is the one shared core (ADR-031) behind both faces: the ``rac retrieve``
CLI command and the ``retrieve_grounding`` MCP tool build the same payload here
and serialize it through the same budget mechanism, so their JSON is
byte-identical for the same corpus and arguments. Deterministic end to end
(ADR-002/ADR-066/ADR-097): a pure function of corpus bytes and the request —
no model, no network, no clock, no randomness. Retrieval, not reasoning
(ADR-034): the result is facts with provenance; the agent judges what they mean.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rac.core.markdown import parse_file
from rac.services.agent_rules import artifact_status, is_retired_status
from rac.services.derived_cache import (
    CorpusReadModel,
    build_derived_index,
    governing_decisions,
)
from rac.services.resolve import search_index

# Defaults pinned by the grounding-retrieval-surface design. The budget unit is
# characters of serialized JSON (ADR-033) and the default matches the server's
# per-response default, so the CLI and MCP faces agree without configuration.
DEFAULT_TOP_K = 5
DEFAULT_BUDGET = 10_000

# The supersedes relationship section name (snake_case, as resolved edges carry it).
_SUPERSEDES = "supersedes"
_DECISION_TYPE = "decision"

# Discovery channel names on the wire (pinned by the design).
CHANNEL_KEYWORD = "keyword"
CHANNEL_SCOPE = "scope"
CHANNEL_SUPERSEDES = "supersedes"


def _status_reader() -> Callable[[str], str]:
    """A memoised per-call status reader: path -> first ``## Status`` line.

    Re-reads the artifact's own bytes (the same corpus source every structure
    derives from), so the answer is deterministic; unreadable files report an
    empty status, which no type retires.
    """
    cache: dict[str, str] = {}

    def status_of(path: str) -> str:
        if path not in cache:
            try:
                cache[path] = artifact_status(parse_file(path))
            except (OSError, UnicodeDecodeError):
                cache[path] = ""
        return cache[path]

    return status_of


def _successor_map(relationships: list) -> dict[str, list[str]]:
    """Resolved supersedes edges inverted: retired target path -> superseding sources.

    Sources are sorted so successor traversal is deterministic regardless of
    graph discovery order; unresolved edges (no ``resolved_path``) never map.
    """
    by_target: dict[str, list[str]] = {}
    for rel in relationships:
        if rel.relationship == _SUPERSEDES and rel.resolved_path is not None:
            by_target.setdefault(rel.resolved_path, []).append(rel.source_path)
    return {target: sorted(set(sources)) for target, sources in by_target.items()}


def _live_successors(
    path: str,
    by_target: dict[str, list[str]],
    is_retired: Callable[[str], bool],
    visited: set[str],
) -> list[str]:
    """The live artifacts superseding ``path``, following chains to their live end.

    Walks the inbound supersedes edges (already validated acyclic; ``visited``
    guards defensively) and returns the live endpoints in deterministic order.
    A retired artifact with no successor contributes nothing — dropped, never
    substituted with something the corpus does not offer.
    """
    out: list[str] = []
    for source in by_target.get(path, ()):
        if source in visited:
            continue
        visited.add(source)
        if is_retired(source):
            out.extend(_live_successors(source, by_target, is_retired, visited))
        else:
            out.append(source)
    return out


def retrieve_grounding(
    directory: str,
    task: str,
    *,
    scope: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    budget: int = DEFAULT_BUDGET,
    live_only: bool = True,
    read_model: CorpusReadModel | None = None,
) -> dict:
    """The compound grounding payload for ``task`` (ADR-113) — pre-serialization.

    Returns the contract-shaped dict the faces serialize through the ADR-033
    budget mechanism (``rac.mcp.budget.serialize``); building and serializing
    apart keeps this a pure corpus function while the truncation guarantee stays
    in its single home. ``read_model`` may be supplied (the server's composed
    read-model, ADR-103); without it one fresh derived build serves the call
    (ADR-032). Items are ordered scope stratum first — a decision that declares
    it governs the path is categorically more binding than a lexical match —
    then keyword matches in the existing fused order, deduplicated by path with
    channels merged, cut to ``top_k``. Each item's ``excerpt`` is the head of
    the artifact's stored bytes capped at an even share of ``budget``, so the
    response distributes the budget across items instead of letting the first
    artifact consume it. An empty ``items`` list is a valid answer.
    """
    top_k = max(1, top_k)
    rm = read_model if read_model is not None else build_derived_index(directory)
    entry_by_path = {e.path: e for e in rm.index_entries}
    status_of = _status_reader()

    def is_retired(path: str) -> bool:
        entry = entry_by_path.get(path)
        artifact_type = entry.type if entry is not None else _DECISION_TYPE
        return is_retired_status(artifact_type, status_of(path))

    items: dict[str, dict] = {}
    order: list[str] = []

    def add(
        path: str,
        channel: str,
        *,
        item_id: str,
        item_type: str,
        title: str | None,
        status: str,
        matching_entry: str | None = None,
        superseded: str | None = None,
        evidence: dict | None = None,
    ) -> None:
        item = items.get(path)
        if item is None:
            item = {
                "id": item_id,
                "type": item_type,
                "title": title,
                "status": status,
                "path": path,
                "provenance": {"channels": []},
            }
            items[path] = item
            order.append(path)
        provenance = item["provenance"]
        if channel not in provenance["channels"]:
            provenance["channels"].append(channel)
        if matching_entry is not None and "matching_entry" not in provenance:
            provenance["matching_entry"] = matching_entry
        if superseded is not None:
            replaced = provenance.setdefault("superseded", [])
            if superseded not in replaced:
                replaced.append(superseded)
        if evidence is not None and "evidence" not in provenance:
            provenance["evidence"] = evidence

    # Scope stratum: the decisions whose declared ## Applies To covers the path
    # bind regardless of keyword match (the corpus-size-immune channel). The
    # scope rows are live by construction (decisions-for semantics), whatever
    # ``live_only`` says — a retired decision never governs.
    if scope:
        for governing in governing_decisions(rm.scope_rows, directory, scope).decisions:
            add(
                governing.path,
                CHANNEL_SCOPE,
                item_id=governing.id,
                item_type=_DECISION_TYPE,
                title=governing.title or None,
                status=governing.status,
                matching_entry=governing.matching_entry,
            )

    # Keyword stratum: the existing tiered match and fused ranking, unchanged.
    # With ``live_only`` a retired match is replaced by its live successors at
    # its rank position (the grounding-eval hard-violation case: a superseded
    # decision must lead to its replacement, never surface as current).
    keyword = search_index(rm.index_entries, task, field_tokens_by_path=rm.field_tokens_by_path)
    by_target = _successor_map(rm.relationships) if live_only else {}
    for match in keyword.matches:
        if live_only and is_retired(match.path):
            for successor_path in _live_successors(match.path, by_target, is_retired, {match.path}):
                successor = entry_by_path.get(successor_path)
                if successor is None:
                    continue
                add(
                    successor_path,
                    CHANNEL_SUPERSEDES,
                    item_id=successor.id,
                    item_type=successor.type,
                    title=successor.title,
                    status=status_of(successor_path),
                    superseded=match.id,
                )
            continue
        add(
            match.path,
            CHANNEL_KEYWORD,
            item_id=match.id,
            item_type=match.type,
            title=match.title,
            status=status_of(match.path),
            evidence=match.evidence,
        )

    selected = order[:top_k]
    # Even excerpt shaping (the design's fairness rule): each item's excerpt is
    # capped at the budget's per-item share, so k items each carry a comparable
    # slice — symmetric with a top-k chunk retriever — before the whole-payload
    # ADR-033 truncation guarantees the final cap.
    share = budget // max(1, min(top_k, len(selected))) if selected else 0
    shaped: list[dict] = []
    for path in selected:
        item = items[path]
        try:
            content = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        provenance = item.pop("provenance")
        item["excerpt"] = content[:share]
        item["provenance"] = provenance
        shaped.append(item)

    payload: dict = {"schema_version": "1", "task": task}
    if scope:
        payload["scope"] = scope
    payload["live_only"] = live_only
    payload["items"] = shaped
    return payload
