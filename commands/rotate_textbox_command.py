"""Undo command for TextBox rotation."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem
    from ui.page_scene import PageScene


class RotateTextBoxCommand(QUndoCommand):
    """Stores old/new rotation angles and restores on undo/redo."""

    def __init__(
        self,
        box: TextBoxItem,
        old_rotation: float,
        new_rotation: float,
        scene: PageScene,
    ) -> None:
        super().__init__()
        self._box = box
        self._old_rotation = old_rotation
        self._new_rotation = new_rotation
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True
        self.setText("Textbox rotieren")

    def undo(self) -> None:
        if self._scene_ref() is None:
            return
        self._apply_rotation(self._old_rotation)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        if self._scene_ref() is None:
            return
        self._apply_rotation(self._new_rotation)

    def _apply_rotation(self, angle: float) -> None:
        """Set rotation around box center."""
        self._box.setTransformOriginPoint(
            self._box._rect.width() / 2.0,
            self._box._rect.height() / 2.0,
        )
        self._box.setRotation(angle)
        self._box.update()
