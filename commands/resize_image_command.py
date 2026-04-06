"""Command: Resize an ImageItem (undoable)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.image_item import ImageItem
    from ui.scene.page_scene import PageScene


class ResizeImageCommand(QUndoCommand):
    """Undoable resize of an ImageItem."""

    def __init__(
        self,
        item: ImageItem,
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
        self.setText("Bild skalieren")

    def undo(self) -> None:
        self._item.set_rect(self._old_rect)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self._item.set_rect(self._new_rect)
