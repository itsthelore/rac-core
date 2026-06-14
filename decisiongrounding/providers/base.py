"""Uniform provider-adapter contract shared by every benchmark arm.

Each arm is a `Provider`. It gets exactly one symmetric opportunity to
populate the answering model's context (`prepare`), then answers the task
(`respond`). Arms differ ONLY in how they select and assemble grounding from
the corpus; the answering model and the prompt scaffold are held constant.

This isolates *retrieval/assembly quality*. It does NOT test whether a
pull-based MCP actually gets consulted in production — that is a separate
deployment question (see README, "Symmetric injection caveat").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid an import cycle with answering.py
    from .answering import AnsweringModel


# The held-constant prompt scaffold. Every arm feeds its grounding into this
# identical frame, so any difference in outcome is attributable to grounding
# assembly, not to prompt phrasing.
SCAFFOLD = (
    "You are a senior engineer about to act on a task. Prior team decisions "
    "may bind your action. Using ONLY the grounding provided, decide whether "
    "the proposed action is permitted or prohibited, follow any superseding "
    "decision over the decision it supersedes, do not invent constraints that "
    "the grounding does not state, and cite the decision id(s) you relied on."
)


@dataclass(frozen=True)
class CorpusArtifact:
    """One markdown artifact in a scenario's project corpus."""

    id: str
    type: str
    path: str
    text: str
    supersedes: tuple[str, ...] = ()
    filler: bool = False


@dataclass(frozen=True)
class Task:
    """What the agent is asked to do, and the action it is on the verge of."""

    prompt: str
    proposed_action: str


@dataclass(frozen=True)
class GroundingContext:
    """What an arm placed in the answering model's context this run."""

    text: str
    artifacts_supplied: tuple[str, ...]
    token_estimate: int


@dataclass(frozen=True)
class Action:
    """A concrete step in a proposed change."""

    kind: str
    target: str
    detail: str


@dataclass
class ProposedChange:
    """The answering model's structured proposal, scored deterministically."""

    summary: str
    actions: list[Action] = field(default_factory=list)
    cites_decisions: list[str] = field(default_factory=list)
    asserts_prohibition: bool = False
    asserts_permission: bool = False


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token)."""
    return (len(text) + 3) // 4


class Provider(ABC):
    """Base arm. Subclasses implement `prepare`; `respond` is shared."""

    #: Stable arm name, matches the run_result.schema.json `arm` enum.
    name: str = "base"

    def __init__(self, answering_model: "AnsweringModel") -> None:
        self.answering_model = answering_model
        self._grounding: GroundingContext | None = None

    @abstractmethod
    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        """Assemble this arm's grounding from the corpus (called once)."""

    def respond(self, task: Task) -> ProposedChange:
        """Answer the task using the held-constant scaffold + answering model."""
        if self._grounding is None:
            raise RuntimeError(f"{self.name}: prepare() must run before respond()")
        return self.answering_model.respond(SCAFFOLD, self._grounding, task)

    @property
    def grounding(self) -> GroundingContext:
        if self._grounding is None:
            raise RuntimeError(f"{self.name}: prepare() has not run")
        return self._grounding
