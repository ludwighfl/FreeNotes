"""Undo command for text formatting changes (bold, italic, font size, etc.)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem
    from ui.scene.page_scene import PageScene


class FormatTextCommand(QUndoCommand):
    """Stores HTML snapshots before/after a formatting change for undo/redo."""

    def __init__(
        self,
        box: TextBoxItem,
        old_html: str,
        new_html: str,
        description: str,
        scene: PageScene,
    ) -> None:
        super().__init__()
        self._box = box
        self._old_html = old_html
        self._new_html = new_html
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True
        self.setText(description)

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None or self._box is None:
            return
        old_pos = min(
            self._box._cursor.position(),
            len(self._box._document.toPlainText()),
        )
        self._box._document.setHtml(self._old_html)
        self._box._cursor.setPosition(
            min(old_pos, len(self._box._document.toPlainText()))
        )
        self._box._auto_resize()
        self._box.update()
        self._box.cursor_moved.emit()

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None or self._box is None:
            return
        old_pos = min(
            self._box._cursor.position(),
            len(self._box._document.toPlainText()),
        )
        self._box._document.setHtml(self._new_html)
        self._box._cursor.setPosition(
            min(old_pos, len(self._box._document.toPlainText()))
        )
        self._box._auto_resize()
        self._box.update()
        self._box.cursor_moved.emit()
