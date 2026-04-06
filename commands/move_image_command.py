"""Command: Move an ImageItem (undoable)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.image_item import ImageItem
    from ui.scene.page_scene import PageScene


class MoveImageCommand(QUndoCommand):
    """Undoable move of an ImageItem."""

    def __init__(
        self,
        item: ImageItem,
        old_pos: QPointF,
        new_pos: QPointF,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._old_pos = QPointF(old_pos)
        self._new_pos = QPointF(new_pos)
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        self.setText("Bild verschieben")

    def undo(self) -> None:
        self._item.setPos(self._old_pos)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self._item.setPos(self._new_pos)
