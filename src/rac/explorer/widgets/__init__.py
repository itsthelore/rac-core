"""Explorer widgets — render UI state, own no intelligence (ADR-015).

Widgets consume :mod:`rac.explorer.state` types only; every status is spelled
out in text, so meaning never rides on colour alone (ADR-028).
"""

from __future__ import annotations

from textual.widgets import Static

from rac.explorer.state import (
    LoadErrorState,
    LoadProgressState,
    RepositorySummaryState,
    health_label,
)

# Home rendering and tests reach for this historical name; the one definition
# lives in rac.explorer.state so the health screen bands the score identically.
_health_label = health_label

# The summary panel aligns a leading label column to this width; the by-type
# rows indent two spaces then pad to _LABEL_WIDTH - 2 so both columns line up.
# These pads are byte-significant — tests assert the exact spacing.
_LABEL_WIDTH = 15


class RepositoryPanel(Static):
    """The home panel: progress, the loaded summary, onboarding, or an error.

    Which state it shows is the screen's decision; the panel only formats the
    state it is handed. Key hints belong to the status line, never to panel
    text (v0.8.8).
    """

    def show_progress(self, progress: LoadProgressState) -> None:
        self.update(f"{progress.label}…")

    def show_summary(self, summary: RepositorySummaryState) -> None:
        lines = [
            f"{'Repository':<{_LABEL_WIDTH}}{summary.directory}",
            "",
            f"{'Artifacts':<{_LABEL_WIDTH}}{summary.artifact_total}",
        ]
        lines.extend(f"  {name:<{_LABEL_WIDTH - 2}}{count}" for name, count in summary.by_type)

        broken = f" ({summary.broken_relationships} broken)" if summary.broken_relationships else ""
        diagnostics = f"{summary.error_count} errors, {summary.warning_count} warnings"
        # Two spaces before the label keep the health fragment aligned whether
        # the score is one digit or three; the spacing is load-bearing (tests).
        health = f"{summary.health_score} / 100  {_health_label(summary.health_score)}"
        lines.extend(
            [
                "",
                f"{'Relationships':<{_LABEL_WIDTH}}{summary.relationship_total}{broken}",
                f"{'Diagnostics':<{_LABEL_WIDTH}}{diagnostics}",
                f"{'Health':<{_LABEL_WIDTH}}{health}",
            ]
        )

        if summary.attention:
            lines.append("")
            lines.append("Attention")
            lines.extend(f"  ! {line}" for line in summary.attention)

        self.update("\n".join(lines))

    def show_onboarding(self, summary: RepositorySummaryState, header: str = "") -> None:
        """The first-run welcome (v0.8.1): empty, invalid, or healthy repository.

        The state is derived from repository content; Enter always continues
        into the normal summary — onboarding never forces setup
        (DESIGN-first-run-experience). ``header`` carries the optional welcome
        additions (mascot, recent repositories, a resume hint) the screen
        composes from preferences and the workspace; it is empty when those are
        disabled or absent.
        """
        lines = ["Welcome to RAC Explorer", "Your product knowledge workspace.", ""]
        if header:
            lines.extend([header, ""])

        if summary.artifact_total == 0:
            lines.extend(self._empty_repository_lines())
        elif summary.error_count:
            lines.extend(self._invalid_repository_lines(summary))
        else:
            lines.extend(self._healthy_repository_lines(summary))

        self.update("\n".join(lines))

    @staticmethod
    def _empty_repository_lines() -> list[str]:
        return [
            "No RAC artifacts found.",
            "",
            "Start by:",
            "  creating an artifact   rac new requirement <path>",
            "  importing a document   rac ingest <file>",
            "",
            "Press Enter to continue",
        ]

    @staticmethod
    def _invalid_repository_lines(summary: RepositorySummaryState) -> list[str]:
        return [
            "Repository issues found",
            "",
            f"  ✗ {summary.error_count} validation errors",
            f"  ! {summary.warning_count} warnings",
            "",
            "Press Enter to open anyway",
        ]

    @staticmethod
    def _healthy_repository_lines(summary: RepositorySummaryState) -> list[str]:
        lines = ["Repository found", ""]
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
        return lines

    def show_editor_prompt(self, resolved: str | None) -> None:
        """The optional first-run editor step (v0.8.11).

        One prefilled, skippable line: Enter accepts (empty keeps the
        ``$VISUAL``/``$EDITOR`` fallback), typing sets the preference, Esc
        skips — ``/settings`` can change it any time (DESIGN-editor-integration).
        """
        detected = f"Detected from environment: {resolved}" if resolved else "None detected"
        self.update(
            "\n".join(
                [
                    "Choose your editor",
                    "",
                    "  `e` opens artifacts in your own editor.",
                    f"  {detected}",
                    "",
                    "  Enter accepts · type a command to set one · Esc skips",
                ]
            )
        )

    def show_error(self, error: LoadErrorState) -> None:
        lines = [f"✗ {error.title}", "", error.detail]
        if error.can_retry:
            lines.extend(["", "Press r to retry."])
        self.update("\n".join(lines))
