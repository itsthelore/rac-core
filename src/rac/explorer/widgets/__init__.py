"""Explorer widgets — render UI state, own no intelligence (ADR-015).

Widgets consume :mod:`rac.explorer.state` types only. Meaning never depends
on colour alone (DESIGN-visual-system): every status carries a text label.
"""

from __future__ import annotations

from textual.widgets import Static

from rac.explorer.state import (
    LoadErrorState,
    LoadProgressState,
    RepositorySummaryState,
    health_label,
)

# Re-exported under the historical name used by home rendering and tests; the
# single definition lives in rac.explorer.state so the health screen agrees.
_health_label = health_label


class RepositoryPanel(Static):
    """The single content panel of the v0.8.0 shell.

    Renders whichever state the screen is in: loading progress, the
    repository summary, or a recoverable error.
    """

    def show_progress(self, progress: LoadProgressState) -> None:
        self.update(f"{progress.label}…")

    def show_summary(self, summary: RepositorySummaryState) -> None:
        lines = [
            f"Repository  {summary.directory}",
            "",
            f"Artifacts   {summary.artifact_total}",
        ]
        lines.extend(f"  {name:<12} {count}" for name, count in summary.by_type)
        broken = f" ({summary.broken_relationships} broken)" if summary.broken_relationships else ""
        health = f"{summary.health_score} / 100  {_health_label(summary.health_score)}"
        lines.extend(
            [
                "",
                f"Relationships  {summary.relationship_total}{broken}",
                f"Diagnostics    {summary.error_count} errors, {summary.warning_count} warnings",
                f"Health         {health}",
            ]
        )
        if summary.attention:
            lines.extend(["", "Attention"])
            lines.extend(f"  ! {line}" for line in summary.attention)
        lines.extend(["", "Press / for anything · Enter to browse"])
        self.update("\n".join(lines))

    def show_onboarding(self, summary: RepositorySummaryState) -> None:
        """The first-run state (v0.8.1): existing, empty, or invalid repository.

        Derived from repository content; Enter always continues into the
        normal summary (no forced setup, DESIGN-first-run-experience).
        """
        lines = ["Welcome to RAC Explorer", "Your product knowledge workspace.", ""]
        if summary.artifact_total == 0:
            lines.extend(
                [
                    "No RAC artifacts found.",
                    "",
                    "Start by:",
                    "  creating an artifact   rac new requirement <path>",
                    "  importing a document   rac ingest <file>",
                    "",
                    "Press Enter to continue",
                ]
            )
        elif summary.error_count:
            lines.extend(
                [
                    "Repository issues found",
                    "",
                    f"  ✗ {summary.error_count} validation errors",
                    f"  ! {summary.warning_count} warnings",
                    "",
                    "Press Enter to open anyway",
                ]
            )
        else:
            lines.append("Repository found")
            lines.append("")
            lines.extend(f"  ✓ {name}  {count}" for name, count in summary.by_type)
            lines.extend(
                [
                    f"  ✓ relationships  {summary.relationship_total}",
                    "",
                    "Navigation",
                    "  /      search and commands",
                    "  ↑ ↓    move",
                    "  Enter  open",
                    "  Esc    back",
                    "  q      quit",
                    "",
                    "Press / for anything · Enter to continue",
                ]
            )
        self.update("\n".join(lines))

    def show_error(self, error: LoadErrorState) -> None:
        lines = [f"✗ {error.title}", "", error.detail]
        if error.can_retry:
            lines.extend(["", "Press r to retry."])
        self.update("\n".join(lines))
