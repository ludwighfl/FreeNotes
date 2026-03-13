"""Undo command for TextBox move (drag via MoveHandleItem)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem
    from ui.page_scene import PageScene


class MoveTextBoxCommand(QUndoCommand):
    """Stores old/new position and restores on undo/redo."""

    def __init__(
        self,
        box: TextBoxItem,
        old_pos: QPointF,
        new_pos: QPointF,
        scene: PageScene,
    ) -> None:
        super().__init__()
        self._box = box
        self._old_pos = QPointF(old_pos)
        self._new_pos = QPointF(new_pos)
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True
        self.setText("Textbox verschieben")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        self._box.setPos(self._old_pos)
        self._box._update_handle_positions()
        self._box.update()

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        self._box.setPos(self._new_pos)
        self._box._update_handle_positions()
        self._box.update()
