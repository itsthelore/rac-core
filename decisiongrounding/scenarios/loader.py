"""Load and validate scenarios from disk.

A scenario is a directory containing `scenario.json` and a `corpus/` of
markdown artifacts. Validation uses `jsonschema` (Draft 2020-12) when it is
importable, and falls back to a built-in required-key check so the spine runs
with no third-party dependencies installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from providers.base import CorpusArtifact, Task

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
_SCENARIO_SCHEMA = _SCHEMA_DIR / "scenario.schema.json"

_REQUIRED_TOP = (
    "scenario_id",
    "version",
    "scenario_type",
    "expected_tie",
    "corpus",
    "task",
    "binding_decisions",
    "relationships",
    "gold_label",
)
_VALID_TYPES = {
    "simple_adherence",
    "superseded_decision",
    "prohibition_at_point_of_action",
    "conflicting_scoped",
    "negative_control",
}


@dataclass(frozen=True)
class Relationship:
    source: str
    type: str
    target: str


@dataclass(frozen=True)
class GoldLabel:
    verdict: str
    governing_decision: str | None
    prohibited_actions: tuple[str, ...]
    required_actions: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    version: str
    scenario_type: str
    expected_tie: bool
    corpus: tuple[CorpusArtifact, ...]
    task: Task
    binding_decisions: tuple[str, ...]
    relationships: tuple[Relationship, ...]
    gold_label: GoldLabel
    directory: Path


def _validate(raw: dict) -> None:
    """Validate against the JSON Schema, or a built-in fallback check."""
    try:
        import jsonschema  # type: ignore
    except Exception:
        _fallback_validate(raw)
        return
    schema = json.loads(_SCENARIO_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(raw, schema)  # raises on invalid


def _fallback_validate(raw: dict) -> None:
    missing = [k for k in _REQUIRED_TOP if k not in raw]
    if missing:
        raise ValueError(f"scenario missing required keys: {missing}")
    if raw["scenario_type"] not in _VALID_TYPES:
        raise ValueError(f"unknown scenario_type: {raw['scenario_type']!r}")
    if not isinstance(raw["corpus"].get("artifacts"), list) or not raw["corpus"]["artifacts"]:
        raise ValueError("corpus.artifacts must be a non-empty list")
    for key in ("prompt", "proposed_action"):
        if key not in raw["task"]:
            raise ValueError(f"task missing required key: {key}")
    gold = raw["gold_label"]
    for key in ("verdict", "governing_decision", "prohibited_actions", "required_actions", "rationale"):
        if key not in gold:
            raise ValueError(f"gold_label missing required key: {key}")
    if gold["verdict"] not in ("permitted", "prohibited"):
        raise ValueError(f"invalid gold verdict: {gold['verdict']!r}")


def load_scenario(directory: str | Path) -> Scenario:
    directory = Path(directory)
    raw = json.loads((directory / "scenario.json").read_text(encoding="utf-8"))
    _validate(raw)

    artifacts: list[CorpusArtifact] = []
    for a in raw["corpus"]["artifacts"]:
        text = (directory / a["path"]).read_text(encoding="utf-8")
        artifacts.append(
            CorpusArtifact(
                id=a["id"],
                type=a["type"],
                path=a["path"],
                text=text,
                supersedes=tuple(a.get("supersedes", ())),
                filler=bool(a.get("filler", False)),
            )
        )

    gold = raw["gold_label"]
    return Scenario(
        scenario_id=raw["scenario_id"],
        version=raw["version"],
        scenario_type=raw["scenario_type"],
        expected_tie=bool(raw["expected_tie"]),
        corpus=tuple(artifacts),
        task=Task(prompt=raw["task"]["prompt"], proposed_action=raw["task"]["proposed_action"]),
        binding_decisions=tuple(raw["binding_decisions"]),
        relationships=tuple(
            Relationship(r["source"], r["type"], r["target"]) for r in raw["relationships"]
        ),
        gold_label=GoldLabel(
            verdict=gold["verdict"],
            governing_decision=gold["governing_decision"],
            prohibited_actions=tuple(gold["prohibited_actions"]),
            required_actions=tuple(gold["required_actions"]),
            rationale=gold["rationale"],
        ),
        directory=directory,
    )


def load_scenarios(root: str | Path) -> list[Scenario]:
    """Load every scenario directory (one containing scenario.json) under root."""
    root = Path(root)
    found = sorted(p.parent for p in root.glob("*/scenario.json"))
    return [load_scenario(d) for d in found]
