"""Hand tool – pan the viewport by dragging, click-select annotations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QObject
from PySide6.QtWidgets import QGraphicsSceneMouseEvent, QGraphicsView

from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class HandTool(BaseTool):
    """Pan tool: drag to scroll the viewport. Does not create any items.

    Uses the scene's views() to access the QGraphicsView and manipulate
    its scrollbars for delta-based panning.

    Also supports click-select: clicking on an annotation item selects it
    (Shift = toggle), clicking empty area clears the selection.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode: str = "idle"  # idle, panning, dragging
        self._last_screen_pos: QPointF | None = None
        self._drag_start_scene_pos: QPointF | None = None
        self._drag_item_positions: dict = {}

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.OpenHandCursor

    def activate(self, scene: PageScene) -> None:
        """Set open hand cursor on all views."""
        for view in scene.views():
            view.setCursor(Qt.CursorShape.OpenHandCursor)

    def deactivate(self, scene: PageScene) -> None:
        """Restore arrow cursor on all views."""
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)
        self._mode = "idle"
        self._last_screen_pos = None

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Start panning from empty space, or select/drag an item."""
        if event.button() == Qt.MouseButton.RightButton:
            from tools.tool_context_menu import build_tool_context_menu
            build_tool_context_menu(event, scene)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()

        # Check for selectable item under cursor
        from tools.selection_tool import _get_selectable_types
        sel_types = _get_selectable_types()
        from items.selection_overlay_item import SelectionOverlayItem

        items_at = scene.items(QRectF(pos.x() - 3, pos.y() - 3, 6, 6))
        
        # Check if we clicked on a control handle. If so, let Qt's default dispatch handle it.
        from items.bounding_box_handle_manager import BoundingBoxHandle
        from items.handle_item import ResizeHandleItem
        from items.rotate_handle_item import RotateHandleItem
        from items.options_handle_item import OptionsHandleItem
        from items.move_handle_item import MoveHandleItem

        if any(isinstance(i, (BoundingBoxHandle, ResizeHandleItem, RotateHandleItem, OptionsHandleItem, MoveHandleItem)) for i in items_at):
            return

        hit_item = next(
            (i for i in items_at
             if isinstance(i, sel_types)
             and not isinstance(i, SelectionOverlayItem)),
            None,
        )

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if hit_item:
            if hit_item in scene._selected_items:
                if shift:
                    scene.remove_from_selection(hit_item)
                    return
            else:
                if shift:
                    scene.add_to_selection(hit_item)
                else:
                    scene.set_selection([hit_item])
            
            # Clicked on a selected item -> Start dragging items
            self._mode = "dragging"
            self._drag_start_scene_pos = pos
            self._drag_item_positions = {
                item: item.pos()
                for item in scene._selected_items
            }
            return

        # Click on empty area → clear selection + start panning
        if not shift:
            scene.clear_selection()

        self._mode = "panning"
        self._last_screen_pos = event.screenPos()
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ClosedHandCursor)

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Pan the view or drag items by the mouse delta."""
        if self._mode == "panning" and self._last_screen_pos is not None:
            current_pos = event.screenPos()
            dx = current_pos.x() - self._last_screen_pos.x()
            dy = current_pos.y() - self._last_screen_pos.y()
            self._last_screen_pos = current_pos

            views = scene.views()
            if views:
                view = views[0]
                h_bar = view.horizontalScrollBar()
                v_bar = view.verticalScrollBar()
                h_bar.setValue(h_bar.value() - int(dx))
                v_bar.setValue(v_bar.value() - int(dy))
                
        elif self._mode == "dragging" and self._drag_start_scene_pos is not None:
            delta = event.scenePos() - self._drag_start_scene_pos
            for item, start_pos in self._drag_item_positions.items():
                item.setPos(start_pos + delta)
            scene._update_selection_overlay()

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Stop panning or finalize item drag."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._mode == "panning":
            self._mode = "idle"
            self._last_screen_pos = None
            for view in scene.views():
                view.setCursor(Qt.CursorShape.OpenHandCursor)
                
        elif self._mode == "dragging":
            # Finish drag with undo command
            from commands.move_items_command import MoveItemsCommand
            from core import undo_stack
            
            moves = {}
            for item, start_pos in self._drag_item_positions.items():
                if item.pos() != start_pos:
                    moves[item] = (start_pos, QPointF(item.pos()))
            if moves:
                cmd = MoveItemsCommand(moves, scene)
                undo_stack.push(cmd)
            
            self._mode = "idle"
            self._drag_start_scene_pos = None
            self._drag_item_positions = {}

    def on_double_click(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        from items.text_box_item import TextBoxItem
        items_at = scene.items(event.scenePos())
        for item in items_at:
            if isinstance(item, TextBoxItem):
                scene.tool_switch_requested.emit("text")
                item.mousePressEvent(event)
                item.mouseDoubleClickEvent(event)
                break
