"""Command: Remove annotation item(s) via object eraser."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from ui.page_scene import PageScene


class RemoveItemCommand(QUndoCommand):
    """Undoable command for deleting one or more annotation items.

    Used by the object eraser. Items are already removed from the scene
    when this command is created. The first redo() is skipped.
    """

    def __init__(
        self,
        items: list[QGraphicsItem],
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[QGraphicsItem] = list(items)
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True

        if len(items) == 1:
            self.setText("Strich löschen")
        else:
            self.setText(f"{len(items)} Elemente löschen")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        for item in self._items:
            if item.scene() is not scene:
                scene.addItem(item)
            scene.add_item_to_registry(item)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return
        for item in self._items:
            if item.scene() is scene:
                scene.removeItem(item)
            scene.remove_item_from_registry(item)
