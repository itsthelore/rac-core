"""Grounding retrieval benchmark — ``rac eval`` (v0.23.0, WS1).

A deterministic, offline benchmark that scores Lore's retrieval surface against
a versioned fixture corpus and query set, then gates CI against a committed
baseline. It is the proof that the core claim — "the agent retrieves the right
recorded decision" — holds and keeps holding (ADR-066, ADR-002).

Determinism is load-bearing. The *scored path* is a pure function of
``(corpus bytes, query set, retrieval code)``: no network, no API keys, no
randomness, and no clock (REQ-002). The two clock/identity values a run records
— ``generated_at`` and ``lore_version`` — live in ``metadata``, which the gate
excludes from comparison, so a wall clock never fails a build (REQ-005).

The benchmark guards the *real* surface, never a parallel scorer (REQ-002): a
``search_artifacts`` case scores the exact :func:`rac.services.resolve.search_index`
order the MCP ``search_artifacts`` tool returns, and a ``get_related`` case
scores the exact ``incoming`` neighborhood
:func:`rac.services.relationships.incoming_references` computes — the single
source of truth the MCP ``get_related`` tool also serializes, so the scored
surface cannot drift from the served one. Production retrieval order is consumed
verbatim — no re-sort, no re-rank (REQ-004). Because only returned-id
*membership* is compared, additive WS2 ``evidence`` fields cannot shift any
metric (REQ-010).

Metrics are Precision@k and Recall@k at ``k ∈ {1, 3, 5}``, macro-averaged
(equal weight per case), reported ``overall`` / ``by_category`` / ``by_tool``,
plus a summed hard-negative ``negative_violations`` count (REQ-003). Floats are
rounded to a fixed precision so the serialized ``metrics`` block is byte-stable
across runs on an unchanged corpus.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rac import __version__
from rac.core.corpus import walk_corpus
from rac.core.fs import find_markdown_files
from rac.services.index import build_repository_index, index_from_corpus
from rac.services.relationships import incoming_references, relationships_from_corpus
from rac.services.resolve import OUTCOME_RESOLVED, resolve_in_index, search_index

# The ranks the benchmark reports Precision@k / Recall@k at (REQ-003).
K_VALUES: tuple[int, ...] = (1, 3, 5)
# The window a hard-negative violation is judged in: the widest k, i.e. the
# top-5 an agent actually reads (REQ-003, design "Hard-negative violation").
NEGATIVE_K: int = max(K_VALUES)
# Metric floats are rounded to this many decimals so the serialized ``metrics``
# object is byte-identical across runs (the gate compares with tolerance, far
# coarser than this precision, so rounding never hides a real regression).
_PRECISION: int = 6

# Default fixture locations, resolved against the current working directory (the
# repo root in CI). The in-repo benchmark is a dev/CI surface; ``rac eval`` with
# no arguments runs it (REQ-001).
DEFAULT_CORPUS = "tests/eval/corpus"
DEFAULT_QUERIES = "tests/eval/queries.json"
DEFAULT_BASELINE = "tests/eval/baseline.json"
DEFAULT_CONFIG = "tests/eval/eval-config.json"

TOOL_SEARCH = "search_artifacts"
TOOL_GET_RELATED = "get_related"
_TOOLS = (TOOL_SEARCH, TOOL_GET_RELATED)


class EvalUsageError(Exception):
    """A usage/IO error — missing baseline, unreadable corpus, malformed input.

    The CLI maps this to exit code 2 (REQ-006), distinct from a gate failure
    (exit 1) and a clean run (exit 0).
    """


@dataclass(frozen=True)
class QueryCase:
    """One scored retrieval case (REQ-008).

    ``query`` is the search string for a ``search_artifacts`` case, or the
    artifact id to look up for a ``get_related`` case. ``relevant`` has at least
    one id by construction; ``must_not_return`` is the optional hard-negative
    set (e.g. a superseded decision that must not surface).
    """

    id: str
    tool: str
    query: str
    category: str
    relevant: tuple[str, ...]
    must_not_return: tuple[str, ...] = ()
    type: str | None = None  # optional artifact-type filter, search cases only


@dataclass
class CaseResult:
    """The scored outcome of one :class:`QueryCase` — a ``per_query`` row."""

    case: QueryCase
    returned: list[str]
    precision: dict[int, float]
    recall: dict[int, float]
    violations: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.case.id,
            "tool": self.case.tool,
            "category": self.case.category,
            "returned": self.returned,
            "relevant": list(self.case.relevant),
        }
        if self.case.must_not_return:
            payload["must_not_return"] = list(self.case.must_not_return)
        for k in K_VALUES:
            payload[f"p_at_{k}"] = _round(self.precision[k])
        for k in K_VALUES:
            payload[f"r_at_{k}"] = _round(self.recall[k])
        payload["violations"] = self.violations
        return payload


@dataclass
class Scorecard:
    """A full benchmark run: gated ``metrics`` plus diagnostic context.

    Only ``metrics`` is compared by the gate; ``metadata`` and ``per_query`` are
    diagnostic and excluded, so a clock or hash never fails a build (REQ-005).
    """

    metrics: dict[str, Any]
    metadata: dict[str, Any]
    per_query: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "metadata": self.metadata,
            "per_query": self.per_query,
        }


def _round(value: float) -> float:
    """Fixed-precision rounding for byte-stable metric serialization."""
    return round(value, _PRECISION)


# --- Loading committed inputs (usage errors → EvalUsageError) ----------------


def _load_json(path: str, what: str) -> Any:
    p = Path(path)
    if not p.is_file():
        raise EvalUsageError(f"{what} not found: {path}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise EvalUsageError(f"cannot read {what}: {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise EvalUsageError(f"malformed {what}: {path}: {exc}") from None


def load_query_set(path: str) -> list[QueryCase]:
    """Parse the committed query set, validating each case's shape (REQ-008)."""
    data = _load_json(path, "query set")
    cases_raw = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases_raw, list) or not cases_raw:
        raise EvalUsageError(f"malformed query set: {path}: expected a non-empty 'cases' list")
    cases: list[QueryCase] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(cases_raw):
        case = _parse_case(raw, path, i)
        if case.id in seen_ids:
            raise EvalUsageError(f"malformed query set: {path}: duplicate case id {case.id!r}")
        seen_ids.add(case.id)
        cases.append(case)
    return cases


def _parse_case(raw: Any, path: str, index: int) -> QueryCase:
    if not isinstance(raw, dict):
        raise EvalUsageError(f"malformed query set: {path}: case {index} is not an object")

    def _require(field_name: str) -> Any:
        if field_name not in raw:
            raise EvalUsageError(
                f"malformed query set: {path}: case {index} missing {field_name!r}"
            )
        return raw[field_name]

    case_id = _require("id")
    tool = _require("tool")
    query = _require("query")
    category = _require("category")
    relevant = _require("relevant")
    if tool not in _TOOLS:
        raise EvalUsageError(
            f"malformed query set: {path}: case {case_id!r} tool must be one of {_TOOLS}"
        )
    if not isinstance(relevant, list) or not relevant:
        raise EvalUsageError(
            f"malformed query set: {path}: case {case_id!r} 'relevant' must be a non-empty list"
        )
    must_not = raw.get("must_not_return", [])
    if not isinstance(must_not, list):
        raise EvalUsageError(
            f"malformed query set: {path}: case {case_id!r} 'must_not_return' must be a list"
        )
    artifact_type = raw.get("type")
    if artifact_type is not None and not isinstance(artifact_type, str):
        raise EvalUsageError(
            f"malformed query set: {path}: case {case_id!r} 'type' must be a string"
        )
    return QueryCase(
        id=str(case_id),
        tool=str(tool),
        query=str(query),
        category=str(category),
        relevant=tuple(str(r) for r in relevant),
        must_not_return=tuple(str(m) for m in must_not),
        type=artifact_type,
    )


def load_baseline(path: str) -> dict[str, Any]:
    """Load the committed baseline ``metrics`` object (REQ-007)."""
    data = _load_json(path, "baseline")
    if not isinstance(data, dict) or "overall" not in data:
        raise EvalUsageError(f"malformed baseline: {path}: expected a metrics object")
    return data


def load_config(path: str) -> dict[str, Any]:
    """Load the committed gate config — floors and tolerance (REQ-006)."""
    data = _load_json(path, "config")
    if not isinstance(data, dict) or "floors" not in data or "tolerance" not in data:
        raise EvalUsageError(f"malformed config: {path}: expected 'floors' and 'tolerance'")
    return data


# --- Retrieval seam: the real surface, never a parallel scorer (REQ-002) -----


def _search_returned(root: str, entries: list, case: QueryCase) -> list[str]:
    """Returned ids for a ``search_artifacts`` case, production order verbatim.

    Calls :func:`rac.services.resolve.search_index` — the exact function the MCP
    ``search_artifacts`` tool calls — and consumes its ``(match_rank, path)``
    order unchanged (REQ-004).
    """
    result = search_index(entries, case.query, artifact_type=case.type)
    return [match.id for match in result.matches]


def _related_returned(root: str, case: QueryCase) -> list[str]:
    """Returned ids for a ``get_related`` case — the tool's ``incoming`` order.

    Builds the 1-hop neighborhood from the same services the MCP ``get_related``
    tool uses (a fresh corpus walk, the repository index, reference resolution,
    and :func:`rac.services.relationships.incoming_references`), then reads the
    ``incoming`` artifacts in the order the tool returns them: the
    reverse-reference / impact-analysis direction ("what references this
    artifact"), the highest-value grounding signal. A query that does not
    resolve to an artifact is a malformed case against this corpus — a usage
    error, not a silent empty result.
    """
    entries = list(walk_corpus(root, recursive=True))
    index = index_from_corpus(root, entries, recursive=True).artifacts
    resolution = resolve_in_index(index, case.query)
    if resolution.outcome != OUTCOME_RESOLVED or resolution.artifact is None:
        raise EvalUsageError(
            f"get_related case {case.id!r}: query {case.query!r} did not resolve to an "
            f"artifact in {root!r}"
        )
    relationships = relationships_from_corpus(entries)
    identity_by_path = {entry.path: (entry.id, entry.type, entry.title) for entry in index}
    incoming = incoming_references(relationships, identity_by_path, resolution.artifact.path)
    return [ref.id for ref in incoming.items]


def returned_ids(root: str, entries: list, case: QueryCase) -> list[str]:
    """The deterministic ranked id list the case's tool returns (REQ-002)."""
    if case.tool == TOOL_SEARCH:
        return _search_returned(root, entries, case)
    return _related_returned(root, case)


# --- Per-case scoring --------------------------------------------------------


def score_case(returned: list[str], case: QueryCase) -> CaseResult:
    """Precision@k, Recall@k, and hard-negative violations for one case.

    ``P@k = |Rel ∩ top_k| / k`` (empty slots count against precision);
    ``R@k = |Rel ∩ top_k| / |Rel|`` (``|Rel| ≥ 1`` by construction). A violation
    is a ``must_not_return`` id appearing in the top-``NEGATIVE_K`` window
    (REQ-003).
    """
    relevant = set(case.relevant)
    precision: dict[int, float] = {}
    recall: dict[int, float] = {}
    for k in K_VALUES:
        top_k = returned[:k]
        hits = sum(1 for rid in top_k if rid in relevant)
        precision[k] = hits / k
        recall[k] = hits / len(relevant)
    negatives = set(case.must_not_return)
    violations = sorted(rid for rid in returned[:NEGATIVE_K] if rid in negatives)
    return CaseResult(
        case=case, returned=returned, precision=precision, recall=recall, violations=violations
    )


# --- Aggregation -------------------------------------------------------------


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _overall(results: list[CaseResult]) -> dict[str, Any]:
    overall: dict[str, Any] = {}
    for k in K_VALUES:
        overall[f"p_at_{k}"] = _round(_mean([r.precision[k] for r in results]))
    for k in K_VALUES:
        overall[f"r_at_{k}"] = _round(_mean([r.recall[k] for r in results]))
    overall["negative_violations"] = sum(len(r.violations) for r in results)
    return overall


def _grouped(results: list[CaseResult], key: Any) -> dict[str, Any]:
    """``{group -> {p_at_1, r_at_5}}`` macro-averaged within each group.

    The gated breakdown surface (per-category is gated, per-tool diagnostic):
    p_at_1 and r_at_5 mirror the overall floors the gate enforces (REQ-006).
    """
    groups: dict[str, list[CaseResult]] = {}
    for result in results:
        groups.setdefault(key(result), []).append(result)
    out: dict[str, Any] = {}
    for name in sorted(groups):
        members = groups[name]
        out[name] = {
            "p_at_1": _round(_mean([r.precision[1] for r in members])),
            "r_at_5": _round(_mean([r.recall[5] for r in members])),
        }
    return out


# --- Hashing the inputs (diagnostic metadata, excluded from the gate) --------


def corpus_hash(root: str) -> str:
    """A stable ``sha256:…`` over the fixture corpus files (REQ-005).

    Covers exactly the Markdown files the benchmark scores, each prefixed by its
    repo-relative path, in the corpus walk's sorted order.
    """
    root_path = Path(root)
    digest = hashlib.sha256()
    for file_path in find_markdown_files(root):
        rel = file_path.relative_to(root_path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def query_set_hash(path: str) -> str:
    """A stable ``sha256:…`` over the query set file bytes (REQ-005)."""
    digest = hashlib.sha256(Path(path).read_bytes())
    return "sha256:" + digest.hexdigest()


# --- Top-level run -----------------------------------------------------------


def run_eval(
    root: str = DEFAULT_CORPUS,
    queries_path: str = DEFAULT_QUERIES,
    *,
    generated_at: str | None = None,
) -> Scorecard:
    """Score the retrieval tools over the corpus and query set (REQ-001..REQ-005).

    Pure over the scored path: ``generated_at`` (a clock) is injected only into
    diagnostic ``metadata``, never the gated ``metrics``. Raises
    :class:`EvalUsageError` on an unreadable corpus or a malformed query set.
    """
    if not Path(root).is_dir():
        raise EvalUsageError(f"corpus not found or not a directory: {root}")
    cases = load_query_set(queries_path)
    entries = build_repository_index(root, recursive=True).artifacts

    results = [score_case(returned_ids(root, entries, case), case) for case in cases]
    results.sort(key=lambda r: r.case.id)

    metrics: dict[str, Any] = {
        "overall": _overall(results),
        "by_category": _grouped(results, lambda r: r.case.category),
        "by_tool": _grouped(results, lambda r: r.case.tool),
    }
    metadata: dict[str, Any] = {
        "lore_version": __version__,
        "corpus_hash": corpus_hash(root),
        "query_set_hash": query_set_hash(queries_path),
        "n_queries": len(cases),
        "generated_at": generated_at if generated_at is not None else _now_iso(),
    }
    per_query = [result.to_dict() for result in results]
    return Scorecard(metrics=metrics, metadata=metadata, per_query=per_query)


def _now_iso() -> str:
    """Wall-clock stamp for diagnostic metadata only (excluded from the gate)."""
    return datetime.now(UTC).isoformat()


# --- The gate (`rac eval --check`) -------------------------------------------

RULE_NEGATIVE = "negative_violations"
RULE_FLOOR = "floor"
RULE_REGRESSION = "regression"


@dataclass(frozen=True)
class GateFailure:
    """One fired gate rule, with the metric and the values that fired it."""

    rule: str
    metric: str
    threshold: float
    current: float

    def render(self) -> str:
        if self.rule == RULE_NEGATIVE:
            return (
                f"FAIL [negative_violations] {self.metric}: "
                f"limit {self.threshold:.0f}, current {self.current:.0f}"
            )
        label = "floor" if self.rule == RULE_FLOOR else "baseline"
        return (
            f"FAIL [{self.rule}] {self.metric}: "
            f"{label} {self.threshold:.6f}, current {self.current:.6f}"
        )


def _gated_pairs(config: dict[str, Any]) -> list[tuple[str, str, str]]:
    """The (scope, name, metric) triples the gate enforces beyond negatives.

    ``overall`` floors plus each per-category floor declared in config (REQ-006).
    Per-tool figures are diagnostic this release and are not enumerated here.
    """
    pairs: list[tuple[str, str, str]] = []
    floors = config["floors"]
    for metric in ("p_at_1", "r_at_5"):
        if metric in floors.get("overall", {}):
            pairs.append(("overall", "", metric))
    for category in sorted(floors.get("by_category", {})):
        for metric in ("p_at_1", "r_at_5"):
            if metric in floors["by_category"][category]:
                pairs.append(("by_category", category, metric))
    return pairs


def _metric_value(metrics: dict[str, Any], scope: str, name: str, metric: str) -> float | None:
    block = metrics.get(scope, {})
    if scope == "overall":
        value = block.get(metric)
    else:
        value = block.get(name, {}).get(metric)
    return float(value) if value is not None else None


def evaluate_gate(
    current: dict[str, Any], baseline: dict[str, Any], config: dict[str, Any]
) -> list[GateFailure]:
    """Compare current ``metrics`` against floors and baseline (REQ-006).

    Fires when any of: (a) ``negative_violations > 0``; (b) a gated metric is
    below its floor; (c) a gated metric is below ``baseline − tolerance``.
    Returns one :class:`GateFailure` per fired rule, in a deterministic order.
    """
    failures: list[GateFailure] = []
    tolerance = float(config["tolerance"])
    floors = config["floors"]

    # (a) Hard-negative violations — always gated, floor is the configured max.
    negatives = int(current.get("overall", {}).get("negative_violations", 0))
    negatives_max = int(floors.get("negative_violations", 0))
    if negatives > negatives_max:
        failures.append(
            GateFailure(RULE_NEGATIVE, "overall.negative_violations", negatives_max, negatives)
        )

    for scope, name, metric in _gated_pairs(config):
        dotted = f"{scope}.{name}.{metric}" if name else f"{scope}.{metric}"
        value = _metric_value(current, scope, name, metric)
        if value is None:
            # A gated metric the current run does not report (e.g. a category
            # that vanished from the corpus) is itself a regression.
            missing_floor = _floor(floors, scope, name, metric)
            failures.append(
                GateFailure(
                    RULE_FLOOR, dotted, missing_floor if missing_floor is not None else 0.0, 0.0
                )
            )
            continue
        floor = _floor(floors, scope, name, metric)
        if floor is not None and value < floor:
            failures.append(GateFailure(RULE_FLOOR, dotted, floor, value))
        base = _metric_value(baseline, scope, name, metric)
        if base is not None and value < base - tolerance:
            failures.append(GateFailure(RULE_REGRESSION, dotted, base, value))
    return failures


def _floor(floors: dict[str, Any], scope: str, name: str, metric: str) -> float | None:
    if scope == "overall":
        value = floors.get("overall", {}).get(metric)
    else:
        value = floors.get(scope, {}).get(name, {}).get(metric)
    return float(value) if value is not None else None


# --- Rendering ---------------------------------------------------------------


def render_scorecard_json(scorecard: Scorecard) -> str:
    """The full scorecard as pretty JSON, key order preserved (REQ-005)."""
    return json.dumps(scorecard.to_dict(), indent=2, ensure_ascii=False)


def render_metrics_json(metrics: dict[str, Any]) -> str:
    """The gated ``metrics`` block alone — what ``--update-baseline`` writes."""
    return json.dumps(metrics, indent=2, ensure_ascii=False)


def render_scorecard_human(scorecard: Scorecard) -> str:
    """A terminal-legible summary: overall, by-category, by-tool, Violations."""
    metrics = scorecard.metrics
    lines: list[str] = []

    overall = metrics["overall"]
    lines.append("Overall")
    header = "  " + "".join(f"{f'P@{k}':>8}{f'R@{k}':>8}" for k in K_VALUES)
    lines.append(header)
    overall_row = "  " + "".join(
        f"{overall[f'p_at_{k}']:>8.3f}{overall[f'r_at_{k}']:>8.3f}" for k in K_VALUES
    )
    lines.append(overall_row)
    lines.append(f"  negative_violations: {overall['negative_violations']}")
    lines.append("")

    lines.append("By category")
    lines.extend(_render_group(metrics["by_category"]))
    lines.append("")

    lines.append("By tool")
    lines.extend(_render_group(metrics["by_tool"]))
    lines.append("")

    lines.append("Violations")
    offenders = [entry for entry in scorecard.per_query if entry["violations"]]
    if not offenders:
        lines.append("  none")
    else:
        for offender in offenders:
            lines.append(
                f"  {offender['id']} ({offender['tool']}): returned {offender['violations']} "
                f"in top-{NEGATIVE_K} [returned={offender['returned']}]"
            )
    return "\n".join(lines)


def _render_group(group: dict[str, Any]) -> list[str]:
    if not group:
        return ["  (none)"]
    width = max(len(name) for name in group)
    lines = [f"  {'':{width}}    P@1     R@5"]
    for name in group:
        cell = group[name]
        lines.append(f"  {name:{width}}  {cell['p_at_1']:>6.3f}  {cell['r_at_5']:>6.3f}")
    return lines
