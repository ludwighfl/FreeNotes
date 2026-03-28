"""Command: Add a TextBoxItem to the scene."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from items.text_box_item import TextBoxItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class AddTextBoxCommand(QUndoCommand):
    """Undoable command for adding a TextBoxItem.

    The first redo() is skipped because the item is already in the scene
    when this command is created.
    """

    def __init__(
        self,
        box: TextBoxItem,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._box: TextBoxItem = box
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True
        self.setText("Textbox hinzufügen")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        if self._box.scene() is scene:
            scene.removeItem(self._box)
        scene.remove_item_from_registry(self._box)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return
        if self._box.scene() is not scene:
            scene.addItem(self._box)
        scene.add_item_to_registry(self._box)
