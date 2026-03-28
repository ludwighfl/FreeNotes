"""Command: Rotate a ShapeItem with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.shape_item import ShapeItem
    from ui.scene.page_scene import PageScene


class RotateShapeCommand(QUndoCommand):
    """Undoable rotation of a ShapeItem."""

    def __init__(
        self,
        item: ShapeItem,
        old_rotation: float,
        new_rotation: float,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._old_rotation = old_rotation
        self._new_rotation = new_rotation
        self._transform_origin = QPointF(item.transformOriginPoint())
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        self.setText("Form rotieren")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        self._item.setTransformOriginPoint(self._transform_origin)
        self._item.setRotation(self._old_rotation)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        self._item.setTransformOriginPoint(self._transform_origin)
        self._item.setRotation(self._new_rotation)
