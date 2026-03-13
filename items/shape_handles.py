"""Shape-specific handle subclasses.

These thin subclasses override only the undo-command creation in
mouseReleaseEvent so that the correct Shape commands are used instead
of the TextBox-specific ones hardcoded in the base classes.
Also includes ShapeOptionsHandleItem (Copy / Cut / Delete bar).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent

from items.handle_item import ResizeHandleItem, HandlePosition
from items.move_handle_item import MoveHandleItem
from items.rotate_handle_item import RotateHandleItem
from items.options_handle_item import OptionsHandleItem

if TYPE_CHECKING:
    from items.shape_item import ShapeItem


# ======================================================================
# Resize handle for ShapeItem
# ======================================================================

class ShapeResizeHandle(ResizeHandleItem):
    """ResizeHandleItem that creates ResizeShapeCommand on release."""

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        parent: ShapeItem = self.parentItem()  # type: ignore[assignment]
        final_rect = parent.get_rect()
        if self._drag_start_rect is not None and final_rect != self._drag_start_rect:
            from commands.resize_shape_command import ResizeShapeCommand
            from core.undo_stack import get_stack

            cmd = ResizeShapeCommand(
                parent, self._drag_start_rect, final_rect, parent.scene(),
            )
            get_stack().push(cmd)

        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_rect = None
        event.accept()


# ======================================================================
# Move handle for ShapeItem
# ======================================================================

class ShapeMoveHandle(MoveHandleItem):
    """MoveHandleItem that creates MoveShapeCommand on release."""

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        if self._click_only and not self._dragging:
            # Click without drag → options popup
            box: ShapeItem = self.parentItem()  # type: ignore[assignment]
            if hasattr(box, "show_options_popup"):
                box.show_options_popup()

        elif self._dragging and self._drag_start_box_pos is not None:
            # Drag ended → undo command
            box: ShapeItem = self.parentItem()  # type: ignore[assignment]
            if box.pos() != self._drag_start_box_pos:
                from commands.move_shape_command import MoveShapeCommand
                from core.undo_stack import get_stack

                cmd = MoveShapeCommand(
                    box, self._drag_start_box_pos, box.pos(), box.scene(),
                )
                get_stack().push(cmd)

        self._dragging = False
        self._click_only = False
        self._drag_start_scene_pos = None
        self._drag_start_box_pos = None
        event.accept()


# ======================================================================
# Rotate handle for ShapeItem
# ======================================================================

class ShapeRotateHandle(RotateHandleItem):
    """RotateHandleItem that creates RotateShapeCommand on release."""

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        box: ShapeItem = self.parentItem()  # type: ignore[assignment]
        final = box.rotation()
        if abs(final - self._start_rotation) > 0.01:
            from commands.rotate_shape_command import RotateShapeCommand
            from core.undo_stack import get_stack

            cmd = RotateShapeCommand(
                box, self._start_rotation, final, box.scene(),
            )
            get_stack().push(cmd)
        event.accept()


# ======================================================================
# Options handle for ShapeItem (Copy / Cut / Delete)
# ======================================================================

class ShapeOptionsHandle(OptionsHandleItem):
    """OptionsHandleItem that uses shape-appropriate commands."""

    def _execute_action(self, index: int) -> None:
        item: ShapeItem = self.parentItem()  # type: ignore[assignment]
        if index == 0:
            self._do_copy_shape(item)
        elif index == 1:
            self._do_cut_shape(item)
        elif index == 2:
            self._do_delete_shape(item)
        self.hide()

    def _do_copy_shape(self, item: ShapeItem) -> None:
        scene = item.scene()
        if scene is None:
            return
        scene._copy_items_to_clipboard([item])

    def _do_cut_shape(self, item: ShapeItem) -> None:
        scene = item.scene()
        if scene is None:
            return
        scene.cut_selected()

    def _do_delete_shape(self, item: ShapeItem) -> None:
        from commands.delete_items_command import DeleteItemsCommand
        from core.undo_stack import get_stack

        scene = item.scene()
        if scene is None:
            return
        scene.clear_selection()
        scene.removeItem(item)
        scene.remove_item_from_registry(item)
        cmd = DeleteItemsCommand([item], scene)
        get_stack().push(cmd)
