"""Command: Remove TextBoxItem(s) from the scene."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from items.text_box_item import TextBoxItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class RemoveTextBoxCommand(QUndoCommand):
    """Undoable command for deleting one or more TextBoxItems.

    Items are already removed from the scene when this command is created.
    The first redo() is skipped.
    """

    def __init__(
        self,
        boxes: list[TextBoxItem],
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._boxes: list[TextBoxItem] = list(boxes)
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True

        if len(boxes) == 1:
            self.setText("Textbox löschen")
        else:
            self.setText(f"{len(boxes)} Textboxen löschen")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        for box in self._boxes:
            if box.scene() is not scene:
                scene.addItem(box)
            scene.add_item_to_registry(box)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return
        for box in self._boxes:
            if box.scene() is scene:
                scene.removeItem(box)
            scene.remove_item_from_registry(box)
