"""Command: Resize a TextBoxItem."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF
from PySide6.QtGui import QUndoCommand

from items.text_box_item import TextBoxItem

if TYPE_CHECKING:
    from ui.page_scene import PageScene


class ResizeTextBoxCommand(QUndoCommand):
    """Undoable command for resizing a TextBoxItem.

    Stores old and new rects (scene coordinates).
    The first redo() is skipped.
    """

    def __init__(
        self,
        box: TextBoxItem,
        old_rect: QRectF,
        new_rect: QRectF,
        scene: object,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._box: TextBoxItem = box
        self._old_rect: QRectF = QRectF(old_rect)
        self._new_rect: QRectF = QRectF(new_rect)
        self._first_redo: bool = True
        self.setText("Textbox skalieren")

    def undo(self) -> None:
        self._box.set_rect(self._old_rect)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self._box.set_rect(self._new_rect)
