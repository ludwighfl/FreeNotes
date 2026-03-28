"""Command: Cut (remove) a TextBoxItem from scene. Clipboard already set."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from items.text_box_item import TextBoxItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class CutTextBoxCommand(QUndoCommand):
    """Undoable cut: removes the box from the scene.

    The clipboard is set externally before this command is pushed.
    First redo() is skipped (item already removed by action).
    """

    def __init__(
        self,
        box: TextBoxItem,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._box = box
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True
        self.setText("Textbox ausschneiden")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        if self._box.scene() is not scene:
            scene.addItem(self._box)
        scene.add_item_to_registry(self._box)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            # Remove item on first push
            scene = self._scene_ref()
            if scene is None:
                return
            if self._box.scene() is scene:
                scene.removeItem(self._box)
            scene.remove_item_from_registry(self._box)
            return
        scene = self._scene_ref()
        if scene is None:
            return
        if self._box.scene() is scene:
            scene.removeItem(self._box)
        scene.remove_item_from_registry(self._box)
