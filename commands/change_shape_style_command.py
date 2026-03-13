"""Command: Change the visual style of a ShapeItem with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.shape_item import ShapeItem
    from core.shape_style import ShapeStyle
    from ui.page_scene import PageScene


class ChangeShapeStyleCommand(QUndoCommand):
    """Undoable change of a ShapeItem's stroke color/width."""

    def __init__(
        self,
        item: ShapeItem,
        old_style: ShapeStyle,
        new_style: ShapeStyle,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._old_style = old_style.copy()
        self._new_style = new_style.copy()
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        self.setText("Form-Stil ändern")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        self._item.set_style(self._old_style)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        self._item.set_style(self._new_style)
