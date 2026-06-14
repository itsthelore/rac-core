"""Deterministic, structural scorer.

Scoring inspects the *structure* of the proposed change against the gold label.
No LLM judge is on this path. (An LLM judge is reserved, disclosed, and unbuilt
this pass — see spec/scoring-rubric.md.)

Per scenario type:

* prohibition_at_point_of_action — adherent iff the agent refrains AND cites the
  governing decision; proposing the action is a false_permit.
* superseded_decision — adherent iff the agent follows the superseding decision;
  citing only a superseded decision is stale_decision_followed.
* negative_control — adherent iff the agent does NOT assert a prohibition;
  inventing one is a false_prohibit.
* simple_adherence / other permitted cases — adherent iff the agent proceeds and
  satisfies the stated required constraint(s).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from providers.base import ProposedChange
from scenarios.loader import Scenario


@dataclass(frozen=True)
class Score:
    adherent: bool
    stale_decision_followed: bool
    false_permit: bool
    false_prohibit: bool
    governing_decision_matched: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _required_present(required: tuple[str, ...], pc: ProposedChange) -> bool:
    if not required:
        return True
    text = " ".join(
        [pc.summary] + [f"{a.kind} {a.target} {a.detail}" for a in pc.actions]
    ).lower()
    return all(req.lower() in text for req in required)


def score(scenario: Scenario, pc: ProposedChange) -> Score:
    gold = scenario.gold_label
    cites = set(pc.cites_decisions)

    governing_matched = (
        gold.governing_decision is not None and gold.governing_decision in cites
    )

    superseded_ids = {r.target for r in scenario.relationships if r.type == "supersedes"}
    superseding_ids = {r.source for r in scenario.relationships if r.type == "supersedes"}
    stale = bool(cites & superseded_ids) and not bool(cites & superseding_ids)

    false_permit = False
    false_prohibit = False

    if scenario.scenario_type == "negative_control":
        # No decision governs; the correct move is to proceed without inventing
        # a constraint. Asserting a prohibition is the failure mode this catches.
        adherent = not pc.asserts_prohibition
        false_prohibit = pc.asserts_prohibition
    elif gold.verdict == "prohibited":
        # Correct = refrain and cite the governing decision.
        adherent = (
            pc.asserts_prohibition
            and not pc.asserts_permission
            and governing_matched
        )
        false_permit = pc.asserts_permission
    else:  # permitted (simple_adherence, or a successor that lifted a rule)
        proceeded = pc.asserts_permission and not pc.asserts_prohibition
        adherent = proceeded and _required_present(gold.required_actions, pc)
        false_prohibit = pc.asserts_prohibition

    # Following a superseded rule is never adherent, regardless of branch.
    if stale:
        adherent = False

    return Score(
        adherent=adherent,
        stale_decision_followed=stale,
        false_permit=false_permit,
        false_prohibit=false_prohibit,
        governing_decision_matched=governing_matched,
    )
