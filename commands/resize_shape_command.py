"""Command: Resize a ShapeItem with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.shape_item import ShapeItem
    from ui.scene.page_scene import PageScene


class ResizeShapeCommand(QUndoCommand):
    """Undoable resize of a ShapeItem."""

    def __init__(
        self,
        item: ShapeItem,
        old_rect: QRectF,
        new_rect: QRectF,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._old_rect = QRectF(old_rect)
        self._new_rect = QRectF(new_rect)
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        self.setText("Form skalieren")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        self._item.set_rect(self._old_rect)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        self._item.set_rect(self._new_rect)
