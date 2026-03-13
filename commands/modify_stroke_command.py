"""Command: Modify stroke path(s) via pixel eraser."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand, QPainterPath
from PySide6.QtWidgets import QGraphicsItem

from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem

if TYPE_CHECKING:
    from ui.page_scene import PageScene


def _deep_copy_path(path: QPainterPath) -> QPainterPath:
    """Create a true deep copy of a QPainterPath."""
    copy = QPainterPath()
    copy.addPath(path)
    return copy


class ModifyStrokeCommand(QUndoCommand):
    """Undoable command for pixel-eraser path modifications.

    Stores before/after paths for each affected item. Also handles
    newly created items from highlight splits.

    For StrokeItems, both before and after paths are always in outline
    mode (filled shapes). This avoids visual mismatches from
    thin↔outline mode transitions.
    """

    def __init__(
        self,
        affected: list[tuple[QGraphicsItem, QPainterPath]],
        deleted_items: list[QGraphicsItem],
        created_items: list[HighlightItem],
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene_ref = weakref.ref(scene)
        self._first_redo: bool = True

        # Deep-copy the affected list so command owns its own paths
        self._affected: list[tuple[QGraphicsItem, QPainterPath]] = [
            (item, _deep_copy_path(orig)) for item, orig in affected
        ]

        # Items fully deleted during this erase action
        self._deleted_ids: set[int] = {id(it) for it in deleted_items}

        # Items created by highlight splits
        self._created_items: list[HighlightItem] = list(created_items)

        # Capture after-state for redo (deep copies of current paths)
        self._after_paths: dict[int, QPainterPath | None] = {}
        # Capture outline_mode state for proper redo
        self._after_outline: dict[int, bool] = {}
        for item, _orig in affected:
            item_id = id(item)
            if item_id in self._deleted_ids:
                self._after_paths[item_id] = None
                self._after_outline[item_id] = True
            elif hasattr(item, "path"):
                self._after_paths[item_id] = _deep_copy_path(item.path)
                self._after_outline[item_id] = getattr(item, "_outline_mode", False)
            else:
                self._after_paths[item_id] = None
                self._after_outline[item_id] = False

        # Capture before-outline_mode state for undo
        self._before_outline: dict[int, bool] = {}
        for item, _orig in affected:
            self._before_outline[id(item)] = True  # always outline after ensure_outline_mode

        self.setText("Strich radieren")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return

        # 1. Remove created split items
        for created in self._created_items:
            if created.scene() is scene:
                scene.removeItem(created)
            scene.remove_item_from_registry(created)

        # 2. Restore original paths / re-add deleted items
        for item, original_path in self._affected:
            item_id = id(item)
            outline = self._before_outline.get(item_id, True)
            if item_id in self._deleted_ids:
                # Item was fully deleted → restore with original path
                if isinstance(item, StrokeItem):
                    item.restore_path(original_path, outline)
                elif isinstance(item, HighlightItem):
                    item.restore_original_path(original_path)
                if item.scene() is not scene:
                    scene.addItem(item)
                scene.add_item_to_registry(item)
            else:
                # Item was partially erased → restore original path
                if isinstance(item, StrokeItem):
                    item.restore_path(original_path, outline)
                elif isinstance(item, HighlightItem):
                    item.restore_original_path(original_path)

        scene.update()

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        scene = self._scene_ref()
        if scene is None:
            return

        # 1. Re-apply modifications / re-delete items
        for item, _original_path in self._affected:
            item_id = id(item)
            after_path = self._after_paths.get(item_id)
            if item_id in self._deleted_ids:
                if item.scene() is scene:
                    scene.removeItem(item)
                scene.remove_item_from_registry(item)
            elif after_path is not None:
                outline = self._after_outline.get(item_id, True)
                if isinstance(item, StrokeItem):
                    item.restore_path(after_path, outline)
                elif isinstance(item, HighlightItem):
                    item.prepareGeometryChange()
                    item._outline_mode = outline
                    copy = QPainterPath()
                    copy.addPath(after_path)
                    item._path = copy
                    item.update()

        # 2. Re-add created split items
        for created in self._created_items:
            if created.scene() is not scene:
                scene.addItem(created)
            scene.add_item_to_registry(created)

        scene.update()
