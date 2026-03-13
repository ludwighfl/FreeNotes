"""Command: Resize a HighlightItem with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand, QPainterPath

if TYPE_CHECKING:
    from items.highlight_item import HighlightItem
    from ui.page_scene import PageScene


class ResizeHighlightCommand(QUndoCommand):
    """Undoable resize of a HighlightItem via bounding-box handles."""

    def __init__(
        self,
        item: HighlightItem,
        old_state: tuple[QPainterPath, QPointF],
        new_state: tuple[QPainterPath, QPointF],
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._old_state = old_state
        self._new_state = new_state
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        self.setText("Markierung skalieren")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        path, pos = self._old_state
        self._item.set_path_state(QPainterPath(path), QPointF(pos))

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        path, pos = self._new_state
        self._item.set_path_state(QPainterPath(path), QPointF(pos))
