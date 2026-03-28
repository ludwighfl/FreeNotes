"""Command: Create a ShapeItem with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.shape_item import ShapeItem
    from ui.scene.page_scene import PageScene


class CreateShapeCommand(QUndoCommand):
    """Undoable command for creating a ShapeItem.

    The item is already in the scene when this command is created.
    First redo() is skipped.
    """

    def __init__(
        self,
        item: ShapeItem,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        self.setText("Form erstellen")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        # Hide handles before removing
        self._item.set_selected_custom(False)
        scene.clear_selection()
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
        scene.set_selection([self._item])
