"""Per-response character budget and whole-item truncation for Guide (v0.10.0).

Guide tool responses land directly in an agent's context window — the scarcest
resource in the session (ADR-033). A single oversized response can flood the
context and degrade the very grounding behaviour Guide exists to produce, so
every response is subject to a per-response character budget.

The budget is measured in characters of the serialized JSON, not tokens:
character counts are stable across models and tokenizer versions, which keeps
output deterministic and byte-stable (ADR-032, ADR-033). The default cap is
10,000 characters, configurable once at server startup (no per-call override
and no session state).

Truncation happens at whole-item boundaries — whole search matches, whole
``incoming`` relationship entries, whole content tails — never mid-element and
never mid-JSON. A truncated response carries an explicit marker:

- ``"truncated": true``
- ``"omitted": <count>`` — how many items were dropped (characters, for a
  content tail)
- ``"hint": "..."`` — how to narrow the request

``truncated`` is *absent* (not ``false``) on a complete response. The marker
field names and placement are part of the pinned tool output contract.

This module is the single home for budget enforcement: every tool serializes
through :func:`serialize`, so truncation logic cannot drift between tools.
"""

from __future__ import annotations

import json

# Default per-response character budget (ADR-033). Configurable at server
# startup via ``build_server(..., budget=...)``; there is no CLI flag and no
# per-call override.
DEFAULT_BUDGET = 10_000

# Pinned marker field names (part of the tool output contract).
MARKER_TRUNCATED = "truncated"
MARKER_OMITTED = "omitted"
MARKER_HINT = "hint"

# Narrowing hints, written as complete prose that stands alone in an agent
# transcript without the request context (design: Accessibility).
HINT_SEARCH = "Narrow the query or request a specific artifact ID."
HINT_RELATED = "Request the artifact directly, or narrow what you are changing."
HINT_CONTENT = "Request a more specific artifact, or read the file directly for the full content."
HINT_SUMMARY = (
    "The repository summary exceeds the response budget; raise the server "
    "budget to see the full overview."
)


def _length(payload: dict) -> int:
    """Serialized character length of ``payload`` (the unit the budget caps)."""
    return len(_dumps(payload))


def _dumps(payload: dict) -> str:
    """Serialize a tool payload deterministically (stable key order, no spaces).

    ``sort_keys`` is *not* used: each tool already emits its keys in the pinned
    contract order, and the budget measures that exact serialization.
    """
    return json.dumps(payload, ensure_ascii=False)


def serialize(payload: dict, budget: int = DEFAULT_BUDGET) -> str:
    """Serialize ``payload`` to JSON within ``budget``, truncating if needed.

    A payload that already fits is serialized unchanged (no marker). Otherwise
    the payload is truncated at whole-item boundaries — the truncatable list or
    content field is shortened and the pinned marker fields are added — and the
    smaller payload is serialized. The returned string is always valid JSON and
    never exceeds ``budget`` once truncation succeeds; if no whole-item
    reduction can bring it under budget, the marked-but-minimal payload is
    returned (a structurally valid over-budget response beats unparseable
    noise, ADR-033).
    """
    if _length(payload) <= budget:
        return _dumps(payload)
    return _dumps(_truncate(payload, budget))


def _truncate(payload: dict, budget: int) -> dict:
    """Reduce ``payload`` to whole-item boundaries until it fits ``budget``.

    Exactly one truncatable field is present per tool response shape:

    - ``matches`` (search_artifacts) — drop whole match entries from the tail.
    - ``incoming`` (get_related) — drop whole incoming entries from the tail.
    - ``content`` (get_artifact) — drop characters from the content tail.

    get_summary has no unbounded field; if it ever exceeds budget the marker is
    added without dropping data (its shape is fixed and small in practice).
    """
    if "matches" in payload:
        return _truncate_list(payload, "matches", budget, HINT_SEARCH)
    if "incoming" in payload:
        return _truncate_list(payload, "incoming", budget, HINT_RELATED)
    if "content" in payload:
        return _truncate_content(payload, budget)
    # No truncatable field (e.g. get_summary): mark it so the agent knows the
    # response is partial, without inventing a boundary to cut.
    marked = dict(payload)
    marked[MARKER_TRUNCATED] = True
    marked[MARKER_OMITTED] = 0
    marked[MARKER_HINT] = HINT_SUMMARY
    return marked


def _truncate_list(payload: dict, key: str, budget: int, hint: str) -> dict:
    """Drop whole entries from ``payload[key]`` until the response fits.

    The marker fields are added once truncation occurs; ``omitted`` counts the
    dropped entries. Determinism: entries are dropped from the tail only, so the
    kept prefix is identical for identical input.
    """
    items = list(payload[key])
    total = len(items)
    kept = items
    while kept:
        candidate = _with_marker(payload, key, kept, total - len(kept), hint)
        if _length(candidate) <= budget:
            return candidate
        kept = kept[:-1]
    # Even an empty list does not fit (the envelope alone is over budget):
    # return the marked empty-list payload — structurally valid, fully omitted.
    return _with_marker(payload, key, [], total, hint)


def _with_marker(payload: dict, key: str, kept: list, omitted: int, hint: str) -> dict:
    """A copy of ``payload`` with ``key`` set to ``kept`` and the marker added."""
    marked = dict(payload)
    marked[key] = kept
    marked[MARKER_TRUNCATED] = True
    marked[MARKER_OMITTED] = omitted
    marked[MARKER_HINT] = hint
    return marked


def _truncate_content(payload: dict, budget: int) -> dict:
    """Shorten ``payload['content']`` from the tail until the response fits.

    The content tail is the truncatable item: characters are dropped from the
    end so the kept head is identical for identical input. ``omitted`` is the
    number of characters removed. The search is a deterministic binary search
    for the largest fitting prefix, capped to keep at least an empty string.
    """
    content = payload["content"]
    total = len(content)
    # Cost of everything except the content string itself, plus the marker.
    # Find the largest prefix length whose response fits the budget.
    lo, hi = 0, total
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = _with_content(payload, content[:mid], total - mid)
        if _length(candidate) <= budget:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return _with_content(payload, content[:best], total - best)


def _with_content(payload: dict, kept: str, omitted: int) -> dict:
    """A copy of ``payload`` with truncated ``content`` and the marker added."""
    marked = dict(payload)
    marked["content"] = kept
    marked[MARKER_TRUNCATED] = True
    marked[MARKER_OMITTED] = omitted
    marked[MARKER_HINT] = HINT_CONTENT
    return marked
