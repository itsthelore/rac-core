"""The held-constant answering model.

Every arm feeds its assembled grounding into the SAME answering model behind
the SAME scaffold. Arms differ only in the grounding; the answering model is a
fixed function of (scaffold, grounding, task).

Two implementations:

* `ScriptedAnsweringModel` — a deterministic, offline stand-in. It reads ONLY
  the grounding text and applies a transparent prose-reading policy: refrain
  when a relevant, non-superseded decision prohibits the action; otherwise
  proceed, folding in any stated constraint; follow a decision over one it
  visibly supersedes; never invent a constraint the grounding does not state.
  CRUCIALLY its behaviour depends only on what is *visible in the grounding*,
  never on the gold label — so the demo honestly exercises retrieval/assembly
  quality. Its output is a plumbing illustration, NOT a benchmark result.

* `ClaudeAnsweringModel` — the real, pinned answering model (stub). Renders one
  prompt, calls the API at temperature 0 with a fixed seed, parses a structured
  ProposedChange back. Filled in behind the `[real]` extra.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from .base import Action, GroundingContext, ProposedChange, Task
from .grounding_format import parse_blocks

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "to", "of", "and", "or", "for", "in", "on", "with", "without",
    "is", "are", "be", "as", "by", "this", "that", "it", "its", "our", "we", "you",
    "must", "not", "no", "do", "does", "should", "shall", "may", "can", "will",
    "all", "any", "from", "into", "at", "use", "using", "team", "service", "api",
}

# Prose signals an agent would read out of plain markdown. Arm-agnostic: the
# same extraction runs over whatever text is present in the grounding.
_PROHIBIT = re.compile(
    r"(must not|may not|shall not|do not|does not|cannot|never|prohibit|"
    r"forbidden|not permitted|not allowed|without (?:explicit )?authorization|"
    r"requires? (?:explicit )?authorization|requires? sign-?off)",
    re.IGNORECASE,
)
_CONSTRAINT = re.compile(
    r"\b(?:must|shall|are required to|is required to|always)\s+([^.\n]+)",
    re.IGNORECASE,
)
# A lone "Superseded" status line marks an artifact as retired. We deliberately
# do NOT treat the prose "superseded by ..." as self-marking, because a
# superseding decision routinely mentions that phrase about the decision it
# replaces — reading it as self-marking would retire the wrong artifact.
_SUPERSEDED_SELF = re.compile(r"^\s*superseded\s*$", re.IGNORECASE | re.MULTILINE)
_SUPERSEDES_OTHER = re.compile(r"supersedes\s+([A-Za-z0-9-]+)", re.IGNORECASE)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 2}


class AnsweringModel(ABC):
    name: str = "base"
    version: str = "0"
    temperature: float | None = 0.0  # None when the pinned model exposes no knob
    seed: int = 0

    @abstractmethod
    def respond(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> ProposedChange:
        ...


class ScriptedAnsweringModel(AnsweringModel):
    """Deterministic offline agent. Reads only the grounding; ignores gold."""

    name = "offline-stub"
    version = "scaffold-0"
    temperature = 0.0

    def __init__(self, seed: int = 0, relevance_threshold: int = 2) -> None:
        self.seed = seed
        self.relevance_threshold = relevance_threshold

    def respond(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> ProposedChange:
        blocks = parse_blocks(grounding.text)
        action_tokens = _content_tokens(task.proposed_action)

        # 1. Which artifact ids are *visibly* superseded in this grounding?
        superseded: set[str] = set()
        for artifact_id, _type, body in blocks:
            if _SUPERSEDED_SELF.search(body):
                superseded.add(artifact_id)
            for other in _SUPERSEDES_OTHER.findall(body):
                superseded.add(other)

        # 2. Relevant, non-superseded decisions the agent would act on.
        relevant_active: list[str] = []
        prohibiting: list[str] = []
        constraints: list[tuple[str, str]] = []  # (artifact_id, constraint_clause)
        for artifact_id, artifact_type, body in blocks:
            if artifact_type != "decision" or artifact_id in superseded:
                continue
            overlap = len(action_tokens & _content_tokens(body))
            if overlap < self.relevance_threshold:
                continue
            relevant_active.append(artifact_id)
            if _PROHIBIT.search(body):
                prohibiting.append(artifact_id)
            else:
                m = _CONSTRAINT.search(body)
                if m:
                    constraints.append((artifact_id, m.group(1).strip()))

        # 3. Decide. Refrain on a live prohibition; otherwise proceed.
        if prohibiting:
            return ProposedChange(
                summary=(
                    "A prior decision prohibits this action; escalate for "
                    "explicit authorization instead of proceeding."
                ),
                actions=[
                    Action(
                        kind="escalate",
                        target="authorization",
                        detail="Request explicit sign-off before taking the action.",
                    )
                ],
                cites_decisions=sorted(set(prohibiting)),
                asserts_prohibition=True,
                asserts_permission=False,
            )

        # Proceed. Cite every relevant, live decision the agent relied on
        # (permitting ones included) so a later stale-decision check can see
        # whether the agent leaned on a superseded rule.
        detail = f"Proceed with: {task.proposed_action}."
        cites = sorted(set(relevant_active))
        if constraints:
            detail += " Constraint(s): " + "; ".join(c for _, c in constraints) + "."
        return ProposedChange(
            summary="No live decision prohibits this action; proceed.",
            actions=[Action(kind="implement", target="proposed_action", detail=detail)],
            cites_decisions=cites,
            asserts_prohibition=False,
            asserts_permission=True,
        )


# JSON Schema the answering model must return — mirrors providers.base.ProposedChange.
_PROPOSED_CHANGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string"},
                    "target": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["kind", "target", "detail"],
            },
        },
        "cites_decisions": {"type": "array", "items": {"type": "string"}},
        "asserts_prohibition": {"type": "boolean"},
        "asserts_permission": {"type": "boolean"},
    },
    "required": [
        "summary",
        "actions",
        "cites_decisions",
        "asserts_prohibition",
        "asserts_permission",
    ],
}


class ClaudeAnsweringModel(AnsweringModel):
    """Real pinned answering model (Claude Opus 4.8), wired behind `[real]`.

    Held identical across arms; only the grounding varies. Note: Opus 4.8
    rejects `temperature`/`top_p`/`seed` (400), so there is no temperature/seed
    knob to pin — determinism is approximated by the fixed model id + scaffold +
    structured JSON output, and run-to-run variance is reported as a metric.
    `temperature` is recorded as None and `seed` is bookkeeping only.
    """

    name = "claude"
    version = "claude-opus-4-8"  # pinned model id
    temperature = None

    def __init__(self, seed: int = 0, effort: str = "low") -> None:
        self.seed = seed
        self.effort = effort  # low keeps the constrained decision task cheap/stable
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # type: ignore  # provided by the [real] extra

            self._client = anthropic.Anthropic()
        return self._client

    def respond(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> ProposedChange:
        client = self._ensure_client()
        user = (
            f"GROUNDING (use only this):\n{grounding.text}\n\n"
            f"TASK: {task.prompt}\n"
            f"PROPOSED ACTION: {task.proposed_action}\n\n"
            "Return a ProposedChange. Set asserts_prohibition=true and refrain "
            "(no prohibited action in `actions`) if a governing decision forbids "
            "the action; set asserts_permission=true and proceed otherwise. Cite "
            "the decision id(s) you relied on. Do not invent constraints absent "
            "from the grounding."
        )
        # No temperature / seed: Opus 4.8 rejects them. Thinking omitted (off) and
        # effort pinned for stability across arms; structured output forces shape.
        resp = client.messages.create(
            model=self.version,
            max_tokens=2048,
            system=scaffold,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": _PROPOSED_CHANGE_SCHEMA},
            },
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            # Treat a safety refusal as a non-answer: assert nothing, cite nothing.
            return ProposedChange(summary="model refused", actions=[])
        import json

        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        return ProposedChange(
            summary=data["summary"],
            actions=[Action(a["kind"], a["target"], a["detail"]) for a in data["actions"]],
            cites_decisions=list(data["cites_decisions"]),
            asserts_prohibition=bool(data["asserts_prohibition"]),
            asserts_permission=bool(data["asserts_permission"]),
        )
