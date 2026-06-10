"""The navigation sidebar — every artifact, one persistent tree (v0.8.7).

A titled panel ("Artifacts") of type groups with counts; rows carry a
fixed-width colour-coded type tag next to the id and title, so meaning never
rides on colour alone (ADR-028). Children populate lazily on expand from the
already-loaded :class:`BrowserState` — the sidebar never calls Core
(ADR-015). The selected artifact's status chip shows in the border-bottom.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from rac.explorer.state import ArtifactRow, BrowserState

# Type → (fixed-width tag, hue). The tag text is always rendered beside the
# name, so the colour is reinforcement, never the only carrier of meaning.
_TYPE_TAGS = {
    "requirement": ("REQ", "#46A758"),
    "decision": ("ADR", "#3B82F6"),
    "roadmap": ("RMP", "#A855F7"),
    "prompt": ("PRM", "#06B6D4"),
    "design": ("DSG", "#EC4899"),
}
_UNKNOWN_TAG = ("UNK", "bright_black")


def type_tag(artifact_type: str) -> tuple[str, str]:
    """The (tag, colour) pair for ``artifact_type``."""
    return _TYPE_TAGS.get(artifact_type, _UNKNOWN_TAG)


def _row_label(row: ArtifactRow) -> Text:
    tag, colour = type_tag(row.type)
    label = Text()
    label.append(tag, style=f"bold {colour}")
    label.append(" ")
    label.append(row.id)
    if row.title and row.title != row.id:
        label.append(f" {row.title}", style="dim")
    return label


class NavigationSidebar(Tree[str]):
    """The persistent artifact tree; node data is the artifact path."""

    def __init__(self) -> None:
        super().__init__("Artifacts", id="sidebar")
        self.show_root = False
        self.guide_depth = 2
        self.border_title = "Artifacts"
        self._rows_by_group: dict[str, tuple[ArtifactRow, ...]] = {}
        self._status_by_path: dict[str, str] = {}

    def show_repository(self, browser: BrowserState | None) -> None:
        """Rebuild the tree from a loaded repository's browser state."""
        self.clear()
        self.border_subtitle = ""
        self._rows_by_group = {}
        self._status_by_path = {}
        if browser is None:
            return
        self._status_by_path = {
            row.path: row.status_label for _, rows in browser.groups for row in rows
        }
        if len(browser.groups) == 1 and browser.groups[0][0] == "all":
            # Flat grouping (preference): rows directly, no type headers.
            for row in browser.groups[0][1]:
                self.root.add_leaf(_row_label(row), data=row.path)
            return
        for group_type, rows in browser.groups:
            self._rows_by_group[group_type] = rows
            label = Text()
            label.append(group_type.title())
            label.append(f"  {len(rows)}", style="dim")
            self.root.add(label, data=f"group:{group_type}")

    def _populate(self, node: TreeNode[str]) -> None:
        data = node.data or ""
        group_type = data.removeprefix("group:")
        if node.children or data == group_type:
            return  # already populated, or a leaf
        for row in self._rows_by_group.get(group_type, ()):
            node.add_leaf(_row_label(row), data=row.path)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded[str]) -> None:
        self._populate(event.node)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[str]) -> None:
        # The highlighted artifact's status chip in the border-bottom; group
        # rows clear it (their counts already carry the information).
        status = self._status_by_path.get(event.node.data or "")
        self.border_subtitle = status or ""

    def reveal(self, path: str) -> None:
        """Move the cursor to ``path`` (after a command-driven open).

        Expands and populates the containing group if needed; moving the
        cursor selects nothing, so revealing never re-navigates.
        """
        for node in self.root.children:
            candidates = (
                self._rows_by_group.get((node.data or "").removeprefix("group:"), ())
                if node.allow_expand
                else ()
            )
            if node.data == path:
                self.call_after_refresh(self.move_cursor, node)
                return
            if any(row.path == path for row in candidates):
                self._populate(node)
                node.expand()
                for child in node.children:
                    if child.data == path:
                        # Newly expanded lines exist only after a refresh.
                        self.call_after_refresh(self.move_cursor, child)
                        return

    def show_status(self, status_label: str) -> None:
        """The selected artifact's status chip in the border-bottom."""
        self.border_subtitle = status_label

    def focus_group(self, artifact_type: str | None) -> bool:
        """Focus the tree at ``artifact_type``'s group (the `/browse` route).

        Returns False when the named group does not exist.
        """
        if artifact_type:
            for node in self.root.children:
                if node.data == f"group:{artifact_type}":
                    self._populate(node)
                    node.expand()
                    self.move_cursor(node)
                    self.focus()
                    return True
            return False
        self.focus()
        return True
