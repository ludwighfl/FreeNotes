"""Command: Paste annotation items with undo support."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class PasteItemsCommand(QUndoCommand):
    """Undoable command for pasting items from the clipboard.

    Items are already added to the scene when this command is created.
    The first redo() is skipped.
    """

    def __init__(
        self,
        new_items: list[QGraphicsItem],
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._new_items: list[QGraphicsItem] = list(new_items)
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True

        self.setText(f"{len(new_items)} Item(s) einfügen")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        scene.clear_selection()
        for item in self._new_items:
            if item.scene() is scene:
                scene.removeItem(item)
            scene.remove_item_from_registry(item)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return
        for item in self._new_items:
            if item.scene() is not scene:
                scene.addItem(item)
            scene.add_item_to_registry(item)
        scene.set_selection(self._new_items)
