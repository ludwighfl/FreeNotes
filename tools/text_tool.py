"""Text tool – creates and selects TextBoxItems for inline editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from app.app_state import AppState
from items.text_box_item import TextBoxItem
from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class TextTool(BaseTool):
    """Tool for creating and editing TextBoxItems.

    Click on existing TextBox: start editing.
    Click on empty area: create new TextBox with minimal size.
    No drag-to-create — box auto-resizes as you type.
    """

    def __init__(self) -> None:
        super().__init__()
        self._current_box: TextBoxItem | None = None
        self._last_completed_item: TextBoxItem | None = None

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.IBeamCursor

    def activate(self, scene: PageScene) -> None:
        views = scene.views()
        if views:
            views[0].setCursor(Qt.CursorShape.IBeamCursor)

    def deactivate(self, scene: PageScene) -> None:
        # Close active box cleanly
        if self._current_box is not None:
            self._current_box.stop_editing()
            self._current_box.set_selected_custom(False)
            self._current_box = None
        # Close any other open boxes
        scene.deselect_all_textboxes()
        # Clear item-level cursors on ALL TextBoxItems in the scene
        # (item cursors override the view cursor when hovering)
        for item in scene.items():
            if isinstance(item, TextBoxItem):
                if item.hasCursor():
                    item.unsetCursor()
        # Reset view cursor
        views = scene.views()
        if views:
            views[0].viewport().unsetCursor()
            views[0].unsetCursor()

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()

        # CASE 1: Click on existing TextBox (or its child handles) → start editing
        items_at = scene.items(QRectF(pos.x() - 2, pos.y() - 2, 4, 4))

        # If the topmost item is a handle, let the scene deliver the event
        # to the handle directly — do NOT intercept.
        from items.handle_item import ResizeHandleItem
        from items.move_handle_item import MoveHandleItem
        from items.rotate_handle_item import RotateHandleItem
        from items.options_handle_item import OptionsHandleItem
        for item in items_at:
            if isinstance(item, (ResizeHandleItem, MoveHandleItem, RotateHandleItem, OptionsHandleItem)):
                # Still track the parent box as current
                parent = item.parentItem()
                if isinstance(parent, TextBoxItem):
                    if self._current_box is not None and self._current_box is not parent:
                        self._current_box.set_selected_custom(False)
                    self._current_box = parent
                return  # let super().mousePressEvent deliver to handle

        existing_box: TextBoxItem | None = None
        for item in items_at:
            # Direct hit on TextBoxItem
            if isinstance(item, TextBoxItem):
                existing_box = item
                break
            # Hit on a child (non-handle) → find parent TextBoxItem
            parent = item.parentItem()
            while parent is not None:
                if isinstance(parent, TextBoxItem):
                    existing_box = parent
                    break
                parent = parent.parentItem()
            if existing_box is not None:
                break

        if existing_box is not None:
            if self._current_box is not None and self._current_box is not existing_box:
                self._current_box.set_selected_custom(False)
            self._current_box = existing_box
            existing_box.start_editing()
            return

        # CASE 2: Click on empty area → create new minimal-size box
        page_idx = scene.get_page_index_at(pos)
        if page_idx == -1:
            return

        if self._current_box is not None:
            self._current_box.set_selected_custom(False)
            self._current_box = None

        style = AppState().tool_style
        # Minimal initial rect: width 200, height 0 → auto-computed by TextBoxItem
        initial_rect = QRectF(pos.x(), pos.y(), 200.0, 0.0)
        box = TextBoxItem(rect=initial_rect, style=style, page_index=page_idx)
        scene.addItem(box)
        scene.add_item_to_registry(box)

        self._last_completed_item = box
        self.tool_action_completed.emit()

        box.start_editing()
        self._current_box = box

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        pass

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        pass

    @property
    def last_completed_item(self) -> TextBoxItem | None:
        return self._last_completed_item
