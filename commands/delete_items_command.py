"""Command: Delete selected annotation items with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class DeleteItemsCommand(QUndoCommand):
    """Undoable command for deleting one or more selected items.

    Items are still in the scene when this command is created.
    The first redo() removes them.
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

        count = len(items)
        self.setText(f"{count} Item(s) löschen")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        for item in self._items:
            if item.scene() is not scene:
                scene.addItem(item)
            scene.add_item_to_registry(item)
        scene.set_selection(self._items)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return
        scene.clear_selection()
        for item in self._items:
            if item.scene() is scene:
                scene.removeItem(item)
            scene.remove_item_from_registry(item)
