"""Portfolio-level statistics across a directory of knowledge artifacts.

`rac stats <directory>` walks the tree for Markdown files, parses and classifies
each one, and aggregates the results. Like the rest of RAC, it works on the
Product AST: every `.md` is parsed into a :class:`~rac.models.Product`.

Requirement, Decision, Roadmap, Prompt, and Design artifacts are aggregated separately so
that one never distorts another: requirement totals/averages span only requirement
files, decisions get their own status/category breakdown, and roadmaps and prompts
and designs each get a lightweight count of how many exist and how many are valid.

Counting basis: requirement totals, averages, and the per-feature breakdown span
*all* parsed requirement files (including ones that fail validation). A file
counts as a *valid feature* when it has no error-severity issues; invalid files
are still counted and are reported separately (never silently skipped).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .artifacts import RELATIONSHIP_SECTIONS, spec_for
from .fs import find_markdown_files
from .inspect import build_inspection
from .parser import parse_file
from .relationships import present_relationship_sections
from .validate import validate


@dataclass
class FeatureStat:
    """Per-file result for a Requirement artifact, feeding the portfolio aggregate."""

    path: str
    name: str  # the feature title, or the filename stem if it has none
    valid: bool
    error_codes: list[str]
    requirements: int
    success_metrics: int
    risks: int


@dataclass
class DecisionStat:
    """Per-file result for a Decision artifact (kept separate from features)."""

    path: str
    name: str  # the decision title, or the filename stem if it has none
    status: str | None = None
    category: str | None = None
    supersedes: str | None = None


@dataclass
class RoadmapStat:
    """Per-file result for a Roadmap artifact (kept separate from features).

    Deliberately lightweight (v0.6.0): identity plus validity. Section-completeness
    or quality breakdowns are intentionally absent — those belong to `rac improve`,
    not portfolio statistics.
    """

    path: str
    name: str  # the roadmap title, or the filename stem if it has none
    valid: bool
    error_codes: list[str]


@dataclass
class PromptStat:
    """Per-file result for a Prompt artifact (kept separate from features).

    Lightweight by design (v0.6.2): identity plus validity and error codes only.
    No prompt quality/completeness metrics — those are out of scope (REQ-010).
    """

    path: str
    name: str  # the prompt title, or the filename stem if it has none
    valid: bool
    error_codes: list[str]


@dataclass
class DesignStat:
    """Per-file result for a Design artifact (kept separate from features).

    Lightweight by design (v0.6.3): identity plus validity and error codes only.
    No section-completeness, visual, or design-system metrics.
    """

    path: str
    name: str  # the design title, or the filename stem if it has none
    valid: bool
    error_codes: list[str]


@dataclass
class PortfolioStats:
    """Aggregate view over all discovered requirement files."""

    directory: str
    features: list[FeatureStat] = field(default_factory=list)
    decisions: list[DecisionStat] = field(default_factory=list)
    roadmaps: list[RoadmapStat] = field(default_factory=list)
    prompts: list[PromptStat] = field(default_factory=list)
    designs: list[DesignStat] = field(default_factory=list)
    # Declared relationship-presence counts (v0.7.0, REQ-011): {normalized
    # section -> number of artifacts that declare it with >=1 reference}. Ordered
    # by RELATIONSHIP_SECTIONS. Not resolution, not edge totals — just presence.
    relationship_counts: dict[str, int] = field(default_factory=dict)

    # --- counts (requirement features) ---
    @property
    def files_found(self) -> int:
        # Legacy name: counts Requirement-style *features* only. Decisions,
        # roadmaps, and prompts are tracked in their own lists, not here.
        return len(self.features)

    @property
    def valid_features(self) -> int:
        return sum(1 for f in self.features if f.valid)

    @property
    def invalid_features(self) -> int:
        return sum(1 for f in self.features if not f.valid)

    @property
    def total_requirements(self) -> int:
        return sum(f.requirements for f in self.features)

    @property
    def total_metrics(self) -> int:
        return sum(f.success_metrics for f in self.features)

    @property
    def total_risks(self) -> int:
        return sum(f.risks for f in self.features)

    # --- quality ---
    @property
    def missing_metrics(self) -> list[str]:
        """Names of features that define no success metrics."""
        return [f.name for f in self.features if f.success_metrics == 0]

    @property
    def missing_risks(self) -> list[str]:
        """Names of features that define no risks."""
        return [f.name for f in self.features if f.risks == 0]

    @property
    def features_missing_metrics(self) -> int:
        return len(self.missing_metrics)

    @property
    def features_missing_risks(self) -> int:
        return len(self.missing_risks)

    @property
    def average_requirements(self) -> float:
        if not self.features:
            return 0.0
        return self.total_requirements / self.files_found

    @property
    def largest_feature(self) -> FeatureStat | None:
        if not self.features:
            return None
        # Most requirements wins; ties broken by name for stable output.
        return max(self.features, key=lambda f: (f.requirements, _neg_name(f.name)))

    @property
    def requirements_by_feature(self) -> list[FeatureStat]:
        """Features sorted by requirement count (desc), then name (asc)."""
        return sorted(self.features, key=lambda f: (-f.requirements, f.name))

    @property
    def invalid(self) -> list[FeatureStat]:
        return [f for f in self.features if not f.valid]

    # --- decisions ---
    @property
    def decision_count(self) -> int:
        return len(self.decisions)

    @property
    def decision_status_counts(self) -> dict[str, int]:
        """Decisions grouped by status, in schema order, omitting empty buckets."""
        return _bucket(self.decisions, "status", "status")

    @property
    def decision_category_counts(self) -> dict[str, int]:
        """Decisions grouped by category, in schema order, omitting empty buckets."""
        return _bucket(self.decisions, "category", "category")

    # --- roadmaps ---
    @property
    def roadmap_count(self) -> int:
        return len(self.roadmaps)

    @property
    def valid_roadmaps(self) -> int:
        return sum(1 for r in self.roadmaps if r.valid)

    @property
    def invalid_roadmaps(self) -> list[RoadmapStat]:
        return [r for r in self.roadmaps if not r.valid]

    # --- prompts ---
    @property
    def prompt_count(self) -> int:
        return len(self.prompts)

    @property
    def valid_prompts(self) -> int:
        return sum(1 for p in self.prompts if p.valid)

    @property
    def invalid_prompts(self) -> list[PromptStat]:
        return [p for p in self.prompts if not p.valid]

    # --- designs ---
    @property
    def design_count(self) -> int:
        return len(self.designs)

    @property
    def valid_designs(self) -> int:
        return sum(1 for d in self.designs if d.valid)

    @property
    def invalid_designs(self) -> list[DesignStat]:
        return [d for d in self.designs if not d.valid]


def _bucket(decisions: list[DecisionStat], attr: str, metadata_key: str) -> dict[str, int]:
    """Count ``decisions`` by ``attr`` in the artifact spec's declared order."""
    spec = spec_for("decision")
    order = spec.metadata.get(metadata_key, ()) if spec else ()
    counts: dict[str, int] = {}
    for d in decisions:
        value = getattr(d, attr)
        if value:
            counts[value] = counts.get(value, 0) + 1
    # Schema order first; then any out-of-vocabulary values seen, alphabetically.
    ordered = {v: counts[v] for v in order if v in counts}
    for v in sorted(counts):
        if v not in ordered:
            ordered[v] = counts[v]
    return ordered


def _neg_name(name: str) -> tuple[int, ...]:
    """Sort key that makes earlier names 'larger' (for max() tie-breaks)."""
    return tuple(-ord(c) for c in name)


def collect_stats(directory: str) -> PortfolioStats:
    """Parse and classify every Markdown file under ``directory``.

    Decisions, roadmaps, prompts, and designs are each routed to their own aggregate;
    everything else is treated as a requirement feature (preserving prior behavior
    for requirement repositories).
    """
    stats = PortfolioStats(directory=directory)
    rel_counts: dict[str, int] = {}
    for path in find_markdown_files(directory):
        product = parse_file(str(path))
        name = product.title or path.stem
        result = build_inspection(product)
        # Declared relationship-presence counts span every artifact type, so they
        # are tallied before the per-type routing below (each branch continues).
        spec = spec_for(result.type)
        if spec is not None:
            for section in present_relationship_sections(product, spec):
                rel_counts[section] = rel_counts.get(section, 0) + 1
        if result.type == "decision":
            stats.decisions.append(
                DecisionStat(
                    path=str(path),
                    name=name,
                    status=result.status,
                    category=result.category,
                    supersedes=result.supersedes,
                )
            )
            continue
        if result.type == "roadmap":
            issues = validate(product)
            error_codes = [i.code for i in issues if i.severity == "error"]
            stats.roadmaps.append(
                RoadmapStat(
                    path=str(path),
                    name=name,
                    valid=not error_codes,
                    error_codes=error_codes,
                )
            )
            continue
        if result.type == "prompt":
            issues = validate(product)
            error_codes = [i.code for i in issues if i.severity == "error"]
            stats.prompts.append(
                PromptStat(
                    path=str(path),
                    name=name,
                    valid=not error_codes,
                    error_codes=error_codes,
                )
            )
            continue
        if result.type == "design":
            issues = validate(product)
            error_codes = [i.code for i in issues if i.severity == "error"]
            stats.designs.append(
                DesignStat(
                    path=str(path),
                    name=name,
                    valid=not error_codes,
                    error_codes=error_codes,
                )
            )
            continue
        issues = validate(product)
        error_codes = [i.code for i in issues if i.severity == "error"]
        stats.features.append(
            FeatureStat(
                path=str(path),
                name=name,
                valid=not error_codes,
                error_codes=error_codes,
                requirements=len(product.requirements),
                success_metrics=len(product.success_metrics),
                risks=len(product.risks),
            )
        )
    # Order the relationship counts by the canonical vocabulary for stable output.
    stats.relationship_counts = {
        section: rel_counts[section]
        for section in RELATIONSHIP_SECTIONS
        if section in rel_counts
    }
    return stats
