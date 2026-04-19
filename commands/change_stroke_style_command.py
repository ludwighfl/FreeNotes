"""Command: Change style (color/width) of Stroke or Highlight items."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsItem

from core.tool_style import ToolStyle

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class ChangeStrokeStyleCommand(QUndoCommand):
    """Undoable command to change the ToolStyle of multiple Stroke/Highlight items."""

    def __init__(
        self,
        item_data: list[tuple[QGraphicsItem, ToolStyle, ToolStyle]],
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        """
        Args:
            item_data: List of (item, old_style, new_style).
            scene: The page scene.
        """
        super().__init__(parent)
        self._item_data = item_data
        self._scene_ref = weakref.ref(scene)

        if len(item_data) == 1:
            self.setText("Stil ändern")
        else:
            self.setText(f"{len(item_data)} Stile ändern")

    def undo(self) -> None:
        self._apply_style(index=1)

    def redo(self) -> None:
        self._apply_style(index=2)

    def _apply_style(self, index: int) -> None:
        """Apply old (index=1) or new (index=2) style."""
        for item, old_style, new_style in self._item_data:
            style_to_apply = old_style if index == 1 else new_style
            item._style = style_to_apply.copy()
            item.prepareGeometryChange()
            item.update()
