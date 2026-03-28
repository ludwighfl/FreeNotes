"""Command: Edit text content of a TextBoxItem (HTML snapshot-based)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from items.text_box_item import TextBoxItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class EditTextCommand(QUndoCommand):
    """Undoable command for a checkpoint of text edits.

    Uses HTML snapshots to preserve formatting.
    The first redo() is skipped (edit already applied).
    """

    def __init__(
        self,
        box: TextBoxItem,
        old_html: str,
        new_html: str,
        scene: object,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._box: TextBoxItem = box
        self._old_html: str = old_html
        self._new_html: str = new_html
        self._scene_ref = weakref.ref(scene)  # type: ignore[arg-type]
        self._first_redo: bool = True
        self.setText("Text bearbeiten")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        # Save cursor position
        old_pos = self._box._cursor.position()
        # Restore HTML
        self._box._document.setHtml(self._old_html)
        # Clamp cursor position
        doc_len = len(self._box._document.toPlainText())
        self._box._cursor.setPosition(min(old_pos, doc_len))
        # Update snapshot state
        self._box._undo_snapshot = self._old_html
        self._box._undo_pending = False
        self._box.update()
        self._box.cursor_moved.emit()
        self._box._auto_resize()

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        old_pos = self._box._cursor.position()
        self._box._document.setHtml(self._new_html)
        doc_len = len(self._box._document.toPlainText())
        self._box._cursor.setPosition(min(old_pos, doc_len))
        self._box._undo_snapshot = self._new_html
        self._box._undo_pending = False
        self._box.update()
        self._box.cursor_moved.emit()
        self._box._auto_resize()
