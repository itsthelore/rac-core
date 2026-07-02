"""Per-response character budget and whole-item truncation for Guide (ADR-033).

Guide tool responses are pasted straight into an agent's context window — the
scarcest resource in a session. One oversized response can flood that window
and drown out the very grounding Guide exists to provide, so every response
passes through a single per-response character budget before it reaches the
wire.

The budget counts *characters of the serialized JSON*, not tokens or bytes:
a character count is stable across models and tokenizer versions, which keeps
truncation deterministic and reproducible (ADR-032, ADR-033). The default cap
is 10,000 characters, fixed once at server startup — there is no per-call
override and no session state.

Reduction happens only at whole-item boundaries — whole search matches, whole
``incoming`` relationship entries, or a character prefix of a content tail —
never mid-element and never mid-JSON. A reduced response is stamped with three
marker fields, always appended *last* so the pinned field order of the tool
shapes survives:

- ``"truncated": true``
- ``"omitted": <count>`` — entries dropped, or characters dropped for a content
  tail
- ``"hint": "..."`` — how to narrow the request

A complete response carries none of these keys (``truncated`` is absent, not
``false``). The marker names and their trailing placement are part of the
pinned tool output contract.

Every tool serializes through :func:`serialize`, so truncation has exactly one
home and cannot drift between tools (ADR-033).
"""

from __future__ import annotations

import json

# Default per-response character budget (ADR-033). Set at startup via
# ``build_server(..., budget=...)``; no CLI flag, no per-call override.
DEFAULT_BUDGET = 10_000

# Pinned marker field names. Part of the output contract, so they are constants
# rather than string literals scattered through the truncation paths.
MARKER_TRUNCATED = "truncated"
MARKER_OMITTED = "omitted"
MARKER_HINT = "hint"

# Narrowing hints. Each is complete prose that stands alone in a transcript
# without the surrounding request (design: Accessibility).
HINT_SEARCH = "Narrow the query or request a specific artifact ID."
HINT_RELATED = "Request the artifact directly, or narrow what you are changing."
HINT_CONTENT = "Request a more specific artifact, or read the file directly for the full content."
HINT_SUMMARY = (
    "The repository summary exceeds the response budget; raise the server "
    "budget to see the full overview."
)


def serialize(payload: dict, budget: int = DEFAULT_BUDGET) -> str:
    """Serialize ``payload`` to JSON within ``budget``, truncating if needed.

    A payload that already fits is serialized unchanged, with no marker. One
    that does not is reduced at whole-item boundaries (see :func:`_truncate`)
    and stamped with the markers before serialization. The result is always
    valid JSON and, once a whole-item reduction fits, never exceeds ``budget``.
    When even the bare envelope is over budget, the marked-but-empty payload is
    returned — a structurally valid over-budget response beats unparseable
    noise (ADR-033).
    """
    if len(_encode(payload)) <= budget:
        return _encode(payload)
    return _encode(_truncate(payload, budget))


def _encode(payload: dict) -> str:
    """Serialize a tool payload deterministically — the unit the budget caps.

    ``ensure_ascii=False`` keeps a multibyte character as one character (the
    budget is a character count). ``sort_keys`` is deliberately omitted: each
    tool emits its keys in the pinned contract order, and the budget measures
    that exact serialization.
    """
    return json.dumps(payload, ensure_ascii=False)


def _truncate(payload: dict, budget: int) -> dict:
    """Reduce ``payload`` to fit ``budget``, dispatched on its truncatable field.

    Each tool shape carries exactly one unbounded field:

    - ``matches`` (search_artifacts) — drop whole match entries from the tail.
    - ``incoming`` (get_related) — drop whole incoming entries from the tail.
    - ``content`` (get_artifact) — drop characters from the content tail.

    get_summary has no unbounded field; an over-budget summary is marked without
    dropping data (``omitted == 0``), because there is no boundary to cut.
    """
    if "matches" in payload:
        return _truncate_list(payload, "matches", budget, HINT_SEARCH)
    if "incoming" in payload:
        return _truncate_list(payload, "incoming", budget, HINT_RELATED)
    if "content" in payload:
        return _truncate_content(payload, budget)
    return _marked(payload, HINT_SUMMARY, omitted=0)


def _truncate_list(payload: dict, key: str, budget: int, hint: str) -> dict:
    """Drop whole entries from the tail of ``payload[key]`` until it fits.

    Entries are dropped from the tail only, so the kept prefix is identical for
    identical input (determinism, ADR-032). ``omitted`` counts the dropped
    entries. If even the empty-list envelope is over budget, the fully-omitted
    marked payload is returned.
    """
    items = list(payload[key])
    total = len(items)
    kept = items
    while kept:
        candidate = _marked({**payload, key: kept}, hint, omitted=total - len(kept))
        if len(_encode(candidate)) <= budget:
            return candidate
        kept = kept[:-1]
    return _marked({**payload, key: []}, hint, omitted=total)


def _truncate_content(payload: dict, budget: int) -> dict:
    """Keep the largest head prefix of ``payload['content']`` that fits ``budget``.

    Characters are dropped from the tail so the kept head is identical for
    identical input. The largest fitting prefix is found by binary search over
    the prefix length; ``omitted`` is the number of characters removed. A tiny
    budget collapses the content to the empty string, still marked.
    """
    content = payload["content"]
    total = len(content)
    lo, hi, best = 0, total, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = _marked(
            {**payload, "content": content[:mid]}, HINT_CONTENT, omitted=total - mid
        )
        if len(_encode(candidate)) <= budget:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return _marked({**payload, "content": content[:best]}, HINT_CONTENT, omitted=total - best)


def _marked(base: dict, hint: str, *, omitted: int) -> dict:
    """Copy ``base`` and append the three truncation markers, in pinned order.

    ``base`` already carries any reduced field (a shorter list or a content
    prefix) in its original position; assigning the markers to the fresh copy
    lands them last, so each tool shape's pinned field order is preserved.
    """
    marked = dict(base)
    marked[MARKER_TRUNCATED] = True
    marked[MARKER_OMITTED] = omitted
    marked[MARKER_HINT] = hint
    return marked
