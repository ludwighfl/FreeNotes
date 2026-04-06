"""Image-specific handle subclasses.

These thin subclasses override only the undo-command creation in
mouseReleaseEvent so that the correct Image commands are used.
Also includes ImageOptionsHandleItem (Copy / Cut / Delete bar).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from items.handle_item import ResizeHandleItem, HandlePosition
from items.move_handle_item import MoveHandleItem
from items.rotate_handle_item import RotateHandleItem
from items.options_handle_item import OptionsHandleItem

if TYPE_CHECKING:
    from items.image_item import ImageItem


# ======================================================================
# Resize handle for ImageItem
# ======================================================================

class ImageResizeHandle(ResizeHandleItem):
    """ResizeHandleItem that creates ResizeImageCommand on release."""

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        parent: ImageItem = self.parentItem()  # type: ignore[assignment]
        final_rect = parent.get_rect()
        if self._drag_start_rect is not None and final_rect != self._drag_start_rect:
            from commands.resize_image_command import ResizeImageCommand
            from core.undo_stack import get_stack

            cmd = ResizeImageCommand(
                parent, self._drag_start_rect, final_rect, parent.scene(),
            )
            get_stack().push(cmd)

        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_rect = None
        event.accept()


# ======================================================================
# Move handle for ImageItem
# ======================================================================

class ImageMoveHandle(MoveHandleItem):
    """MoveHandleItem that creates MoveImageCommand on release."""

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        if self._click_only and not self._dragging:
            # Click without drag → options popup
            box: ImageItem = self.parentItem()  # type: ignore[assignment]
            if hasattr(box, "show_options_popup"):
                box.show_options_popup()

        elif self._dragging and self._drag_start_box_pos is not None:
            # Drag ended → undo command
            box: ImageItem = self.parentItem()  # type: ignore[assignment]
            if box.pos() != self._drag_start_box_pos:
                from commands.move_image_command import MoveImageCommand
                from core.undo_stack import get_stack

                cmd = MoveImageCommand(
                    box, self._drag_start_box_pos, box.pos(), box.scene(),
                )
                get_stack().push(cmd)

        self._dragging = False
        self._click_only = False
        self._drag_start_scene_pos = None
        self._drag_start_box_pos = None
        event.accept()


# ======================================================================
# Rotate handle for ImageItem
# ======================================================================

class ImageRotateHandle(RotateHandleItem):
    """RotateHandleItem that creates RotateImageCommand on release."""

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        box: ImageItem = self.parentItem()  # type: ignore[assignment]
        final = box.rotation()
        if abs(final - self._start_rotation) > 0.01:
            from commands.rotate_image_command import RotateImageCommand
            from core.undo_stack import get_stack

            cmd = RotateImageCommand(
                box, self._start_rotation, final, box.scene(),
            )
            get_stack().push(cmd)
        event.accept()


# ======================================================================
# Options handle for ImageItem (Copy / Cut / Delete)
# ======================================================================

class ImageOptionsHandle(OptionsHandleItem):
    """OptionsHandleItem that uses image-appropriate commands."""

    def _execute_action(self, index: int) -> None:
        item: ImageItem = self.parentItem()  # type: ignore[assignment]
        if index == 0:
            self._do_copy_image(item)
        elif index == 1:
            self._do_cut_image(item)
        elif index == 2:
            self._do_delete_image(item)
        self.hide()

    def _do_copy_image(self, item: ImageItem) -> None:
        scene = item.scene()
        if scene is None:
            return
        scene._copy_items_to_clipboard([item])

    def _do_cut_image(self, item: ImageItem) -> None:
        scene = item.scene()
        if scene is None:
            return
        scene.cut_selected()

    def _do_delete_image(self, item: ImageItem) -> None:
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
