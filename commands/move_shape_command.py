"""Command: Move a ShapeItem with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.shape_item import ShapeItem
    from ui.page_scene import PageScene


class MoveShapeCommand(QUndoCommand):
    """Undoable move of a ShapeItem."""

    def __init__(
        self,
        item: ShapeItem,
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
        self.setText("Form verschieben")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        self._item.setPos(self._old_pos)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        self._item.setPos(self._new_pos)
