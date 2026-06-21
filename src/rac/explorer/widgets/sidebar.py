"""The navigation sidebar — every artifact, one persistent tree (v0.8.7).

A titled panel ("Artifacts") that mirrors the repository's directory
structure by default (v0.8.10), or groups by type with counts, or lists
flat — per the grouping preference. Rows carry a fixed-width colour-coded
type tag next to the id and title, so meaning never rides on colour alone
(ADR-028). Everything renders from the already-loaded :class:`BrowserState`
— the sidebar never calls Core and derives no structure of its own
(ADR-015). The selected artifact's status chip shows in the border-bottom.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from rac.explorer.state import ArtifactRow, BrowserState, DirectoryNode

# Type → (tag, dark hue, light hue). The tag text always renders beside the
# name, so colour is reinforcement, never the only carrier of meaning (ADR-028).
# The hue adapts to the active theme (v0.26.1): the dark set on near-black, a
# deepened set on light so every tag stays legible on paper.
_TYPE_TAGS = {
    "requirement": ("REQ", "#46A758", "#2F6B22"),
    "decision": ("ADR", "#3B82F6", "#2457B8"),
    "roadmap": ("RMP", "#A855F7", "#7A35A8"),
    "prompt": ("PRM", "#06B6D4", "#0E6E7D"),
    "design": ("DSG", "#EC4899", "#B83275"),
}
_UNKNOWN_TAG = ("UNK", "bright_black", "#6B6253")


def type_tag(artifact_type: str, *, dark: bool = True) -> tuple[str, str]:
    """The (tag, colour) pair for ``artifact_type``, tuned to the theme.

    The hue adapts to a dark or light background so the tag reads clearly
    either way; the tag text is identical across themes, so meaning never
    depends on the palette (ADR-028).
    """
    tag, dark_hue, light_hue = _TYPE_TAGS.get(artifact_type, _UNKNOWN_TAG)
    return tag, (dark_hue if dark else light_hue)


def _row_label(row: ArtifactRow, *, dark: bool = True) -> Text:
    # The human title leads (the ID lives in the context panel and the
    # Inspection tab); invalid artifacts carry the ✗ marker beside the tag,
    # so repository trouble is visible from the tree (ADR-028: text, not
    # colour, carries the state).
    tag, colour = type_tag(row.type, dark=dark)
    label = Text()
    label.append(tag, style=f"bold {colour}")
    if "✗" in row.status_label:
        label.append(" ✗", style="bold")
    label.append(f" {row.title or row.id}")
    return label


class NavigationSidebar(Tree[str]):
    """The persistent artifact tree; node data is the artifact path."""

    BINDINGS = [Binding("e", "edit_highlighted", "Edit", show=False)]

    class EditRequested(Message):
        """`e` on a highlighted artifact row — open it in the editor."""

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    def __init__(self) -> None:
        super().__init__("Artifacts", id="sidebar")
        self.show_root = False
        self.guide_depth = 2
        self.border_title = "Artifacts"
        self._rows_by_group: dict[str, tuple[ArtifactRow, ...]] = {}
        self._status_by_path: dict[str, str] = {}
        # Every eagerly-built node by its data key (folder and flat modes,
        # plus type-mode group headers) — O(1) reveal and cursor restore.
        self._node_by_data: dict[str, TreeNode[str]] = {}

    def show_repository(self, browser: BrowserState | None) -> None:
        """Rebuild the tree from a loaded repository's browser state.

        Reloads keep the user's place: expanded nodes — nested directories
        included — stay expanded and the cursor returns to the same row when
        it still exists (v0.8.8, folders v0.8.10).
        """
        expanded = self._expanded_data()
        cursor = self.cursor_node.data if self.cursor_node is not None else None

        self.clear()
        self.border_subtitle = ""
        self._rows_by_group = {}
        self._status_by_path = {}
        self._node_by_data = {}
        if browser is None:
            return
        self._status_by_path = {
            row.path: row.status_label for _, rows in browser.groups for row in rows
        }
        dark = self._tag_dark()
        if browser.tree is not None:
            # Folders grouping (the default, v0.8.10): the real directory
            # structure, built eagerly but collapsed.
            self._add_directory(self.root, browser.tree, expanded, dark)
        elif len(browser.groups) == 1 and browser.groups[0][0] == "all":
            # Flat grouping (preference): rows directly, no type headers.
            for row in browser.groups[0][1]:
                leaf = self.root.add_leaf(_row_label(row, dark=dark), data=row.path)
                self._node_by_data[row.path] = leaf
        else:
            for group_type, rows in browser.groups:
                self._rows_by_group[group_type] = rows
                label = Text()
                label.append(f"{group_type.title():<14}")
                label.append(f"{len(rows):>4}", style="dim")
                node = self.root.add(label, data=f"group:{group_type}")
                self._node_by_data[f"group:{group_type}"] = node
                if node.data in expanded:
                    self._populate(node)
                    node.expand()
        if cursor is not None:
            self._restore_cursor(cursor)

    def _expanded_data(self) -> set[str]:
        """Data keys of every expanded node, however deep."""
        expanded: set[str] = set()
        stack = list(self.root.children)
        while stack:
            node = stack.pop()
            if node.allow_expand and node.is_expanded and node.data is not None:
                expanded.add(node.data)
            stack.extend(node.children)
        return expanded

    @staticmethod
    def _count_rows(directory: DirectoryNode) -> int:
        return len(directory.rows) + sum(
            NavigationSidebar._count_rows(child) for child in directory.dirs
        )

    def _tag_dark(self) -> bool:
        """Whether the active theme is dark, for theme-aware tag hues (v0.26.1)."""
        try:
            return bool(self.app.current_theme.dark)
        except Exception:  # noqa: BLE001 - no app/theme yet: assume the dark default
            return True

    def _add_directory(
        self, parent: TreeNode[str], directory: DirectoryNode, expanded: set[str], dark: bool
    ) -> None:
        """Render one directory's children: subdirectories first, then rows."""
        for child in directory.dirs:
            label = Text()
            label.append(f"{child.name}/")
            label.append(f"  {self._count_rows(child)}", style="dim")
            data = f"dir:{child.path}"
            node = parent.add(label, data=data)
            self._node_by_data[data] = node
            self._add_directory(node, child, expanded, dark)
            if data in expanded:
                node.expand()
        for row in directory.rows:
            leaf = parent.add_leaf(_row_label(row, dark=dark), data=row.path)
            self._node_by_data[row.path] = leaf

    def _restore_cursor(self, data: str) -> None:
        node = self._node_by_data.get(data)
        if node is not None:
            self.call_after_refresh(self.move_cursor, node)
            return
        # Type mode populates lazily, so a leaf may not be in the map yet.
        for group in self.root.children:
            for child in group.children:
                if child.data == data:
                    self.call_after_refresh(self.move_cursor, child)
                    return

    def _populate(self, node: TreeNode[str]) -> None:
        data = node.data or ""
        group_type = data.removeprefix("group:")
        if node.children or data == group_type:
            return  # already populated, or a leaf
        dark = self._tag_dark()
        for row in self._rows_by_group.get(group_type, ()):
            self._node_by_data[row.path] = node.add_leaf(_row_label(row, dark=dark), data=row.path)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded[str]) -> None:
        self._populate(event.node)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[str]) -> None:
        # The highlighted artifact's status chip in the border-bottom; group
        # rows clear it (their counts already carry the information).
        status = self._status_by_path.get(event.node.data or "")
        self.border_subtitle = status or ""

    def reveal(self, path: str) -> None:
        """Move the cursor to ``path`` (after a command-driven open).

        Expands the chain of containing directories (folders mode) or
        populates the containing group (type mode); moving the cursor
        selects nothing, so revealing never re-navigates.
        """
        node = self._node_by_data.get(path)
        if node is not None:
            ancestor = node.parent
            while ancestor is not None and ancestor is not self.root:
                ancestor.expand()
                ancestor = ancestor.parent
            # Newly expanded lines exist only after a refresh.
            self.call_after_refresh(self.move_cursor, node)
            return
        # Type mode populates lazily: find the group whose rows hold the path.
        for group in self.root.children:
            candidates = self._rows_by_group.get((group.data or "").removeprefix("group:"), ())
            if any(row.path == path for row in candidates):
                self._populate(group)
                group.expand()
                for child in group.children:
                    if child.data == path:
                        self.call_after_refresh(self.move_cursor, child)
                        return

    def show_status(self, status_label: str) -> None:
        """The selected artifact's status chip in the border-bottom."""
        self.border_subtitle = status_label

    def action_edit_highlighted(self) -> None:
        # Only artifact rows are editable — group headers and directories
        # carry no file of their own.
        node = self.cursor_node
        if node is not None and node.data is not None and node.data in self._status_by_path:
            self.post_message(self.EditRequested(node.data))
