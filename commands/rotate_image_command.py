"""Command: Rotate an ImageItem (undoable)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.image_item import ImageItem
    from ui.scene.page_scene import PageScene


class RotateImageCommand(QUndoCommand):
    """Undoable rotation of an ImageItem."""

    def __init__(
        self,
        item: ImageItem,
        old_rotation: float,
        new_rotation: float,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._old_rotation = old_rotation
        self._new_rotation = new_rotation
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        self.setText("Bild drehen")

    def undo(self) -> None:
        self._item.setRotation(self._old_rotation)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self._item.setRotation(self._new_rotation)
