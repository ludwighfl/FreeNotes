"""Command: Add an annotation item (pen stroke or highlighter mark)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsItem

from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem

if TYPE_CHECKING:
    from ui.page_scene import PageScene


class AddItemCommand(QUndoCommand):
    """Undoable command for adding a StrokeItem or HighlightItem.

    The item is already in the scene when this command is created.
    The first redo() call (triggered automatically by QUndoStack.push)
    is skipped to avoid double-insertion.
    """

    def __init__(
        self,
        item: StrokeItem | HighlightItem,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item: QGraphicsItem = item
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True

        if isinstance(item, StrokeItem):
            self.setText("Strich hinzufügen")
        elif isinstance(item, HighlightItem):
            self.setText("Markierung hinzufügen")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        if self._item.scene() is scene:
            scene.removeItem(self._item)
        scene.remove_item_from_registry(self._item)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return
        if self._item.scene() is not scene:
            scene.addItem(self._item)
        scene.add_item_to_registry(self._item)
