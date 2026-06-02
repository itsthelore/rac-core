"""Portfolio-level statistics across a directory of requirement files.

`rac stats <directory>` walks the tree for Markdown files, parses and validates
each one, and aggregates the results. Like the rest of RAC, it works on the
Product AST: every `.md` is parsed into a :class:`~rac.models.Product`.

Counting basis: totals, averages, and the per-feature breakdown span *all*
parsed files (including ones that fail validation). A file counts as a *valid
feature* when it has no error-severity issues; invalid files are still counted
and are reported separately (never silently skipped).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .parser import parse_file
from .validate import validate


@dataclass
class FeatureStat:
    """Per-file result feeding the portfolio aggregate."""

    path: str
    name: str  # the feature title, or the filename stem if it has none
    valid: bool
    error_codes: list[str]
    requirements: int
    success_metrics: int
    risks: int


@dataclass
class PortfolioStats:
    """Aggregate view over all discovered requirement files."""

    directory: str
    features: list[FeatureStat] = field(default_factory=list)

    # --- counts (all parsed files) ---
    @property
    def files_found(self) -> int:
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


def _neg_name(name: str) -> tuple[int, ...]:
    """Sort key that makes earlier names 'larger' (for max() tie-breaks)."""
    return tuple(-ord(c) for c in name)


def find_markdown_files(directory: str) -> list[Path]:
    """Recursively find `*.md` files, skipping dotted dirs (.git, .venv, ...)."""
    root = Path(directory)
    found = [
        p
        for p in root.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(root).parts)
    ]
    return sorted(found)


def collect_stats(directory: str) -> PortfolioStats:
    """Parse and validate every Markdown file under ``directory``."""
    stats = PortfolioStats(directory=directory)
    for path in find_markdown_files(directory):
        product = parse_file(str(path))
        issues = validate(product)
        error_codes = [i.code for i in issues if i.severity == "error"]
        stats.features.append(
            FeatureStat(
                path=str(path),
                name=product.title or path.stem,
                valid=not error_codes,
                error_codes=error_codes,
                requirements=len(product.requirements),
                success_metrics=len(product.success_metrics),
                risks=len(product.risks),
            )
        )
    return stats
