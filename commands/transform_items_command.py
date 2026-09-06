"""Generic undo command for transforming (move/resize/rotate) items via state snapshots."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class TransformItemsCommand(QUndoCommand):
    """Generic QUndoCommand for item transformation using capture_state / restore_state.

    Args:
        items_before: Mapping of {item: state_snapshot_dict} before the transform.
        items_after: Mapping of {item: state_snapshot_dict} after the transform.
        scene: The PageScene (stored as weak reference).
        text: User-facing description for the undo command.
    """

    def __init__(
        self,
        items_before: dict[QGraphicsItem, dict[str, Any]],
        items_after: dict[QGraphicsItem, dict[str, Any]],
        scene: PageScene,
        text: str = "Transformation",
    ) -> None:
        super().__init__(text)
        self._items_before = items_before
        self._items_after = items_after
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        for item, state in self._items_before.items():
            if hasattr(item, "restore_state"):
                item.restore_state(state)
            if hasattr(scene, "update_item_page_index"):
                scene.update_item_page_index(item)
        if hasattr(scene, "_update_selection_overlay"):
            scene._update_selection_overlay()

    def redo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
        if self._first_redo:
            self._first_redo = False
            for item in self._items_after.keys():
                if hasattr(scene, "update_item_page_index"):
                    scene.update_item_page_index(item)
            return

        for item, state in self._items_after.items():
            if hasattr(item, "restore_state"):
                item.restore_state(state)
            if hasattr(scene, "update_item_page_index"):
                scene.update_item_page_index(item)
        if hasattr(scene, "_update_selection_overlay"):
            scene._update_selection_overlay()
