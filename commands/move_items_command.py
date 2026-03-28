"""Undo command for moving multiple items at once."""

from __future__ import annotations

import weakref

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsItem

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class MoveItemsCommand(QUndoCommand):
    """Moves one or more QGraphicsItems with undo/redo support.

    Args:
        moves: Mapping of {item: (old_pos, new_pos)}.
        scene: The PageScene (stored as weak reference).
    """

    def __init__(
        self,
        moves: dict[QGraphicsItem, tuple[QPointF, QPointF]],
        scene: PageScene,
    ) -> None:
        count = len(moves)
        super().__init__(f"{count} Item(s) verschieben")
        self._moves = moves
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        for item, (old_pos, _) in self._moves.items():
            item.setPos(old_pos)
        scene._update_selection_overlay()

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return
        for item, (_, new_pos) in self._moves.items():
            item.setPos(new_pos)
        scene._update_selection_overlay()
