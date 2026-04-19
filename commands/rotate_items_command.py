"""Command to rotate multiple items around a shared pivot point."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand
from PySide6.QtCore import QPointF, QRectF

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class RotateItemsCommand(QUndoCommand):
    """Undoable command to rotate multiple items together.
    
    Restores each item's specific state snapshot rather than
    attempting to inverse-rotate, preventing floating point drift.
    """

    def __init__(
        self,
        old_states: dict,
        new_states: dict,
        overlay_old_rect: QRectF,
        overlay_new_rect: QRectF,
        scene: PageScene,
        parent: QUndoCommand | None = None,
    ) -> None:
        """
        Args:
            old_states: Dict mapping item -> state tuple
            new_states: Dict mapping item -> state tuple
            overlay_old_rect: old bounding_rect of SelectionOverlayItem
            overlay_new_rect: new bounding_rect of SelectionOverlayItem
            scene: The page scene.
        """
        super().__init__(parent)
        self._old_states = old_states
        self._new_states = new_states
        self._overlay_old_rect = overlay_old_rect
        self._overlay_new_rect = overlay_new_rect
        self._scene_ref = weakref.ref(scene)
        self._first_redo = True
        
        count = len(self._old_states)
        if count == 1:
            self.setText("Element rotieren")
        else:
            self.setText(f"{count} Elemente rotieren")

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None:
            return
            
        self._apply_states(self._old_states)
        if hasattr(scene, "_selection_overlay"):
            scene._selection_overlay._bounding_rect = self._overlay_old_rect
            if hasattr(scene, "_update_selection_overlay"):
                scene._update_selection_overlay()

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
            
        scene = self._scene_ref()
        if scene is None:
            return
            
        self._apply_states(self._new_states)
        if hasattr(scene, "_selection_overlay"):
            scene._selection_overlay._bounding_rect = self._overlay_new_rect
            if hasattr(scene, "_update_selection_overlay"):
                scene._update_selection_overlay()

    def _apply_states(self, states: dict) -> None:
        """Apply state snapshots to standard items."""
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.shape_item import ShapeItem
        from items.text_box_item import TextBoxItem
        from items.image_item import ImageItem

        for item, state in states.items():
            if isinstance(item, (StrokeItem, HighlightItem)):
                # path, pos, [width]
                item.set_path_state(*state)
            elif isinstance(item, (ShapeItem, ImageItem)):
                # For shape/image, state is (rect, pos, rotation, transformOriginPoint)
                item.set_rect(state[0])
                item.setPos(state[1])
                item.setRotation(state[2])
                item.setTransformOriginPoint(state[3])
                item.update()
            elif isinstance(item, TextBoxItem):
                # TextBox state is rect, pos, rotation, origin
                item.set_rect(state[0])
                item.setPos(state[1])
                item.setRotation(state[2])
                item.setTransformOriginPoint(state[3])
                item.update()
