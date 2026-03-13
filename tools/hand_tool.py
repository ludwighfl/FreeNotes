"""Hand tool – pan the viewport by dragging, click-select annotations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QObject
from PySide6.QtWidgets import QGraphicsSceneMouseEvent, QGraphicsView

from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.page_scene import PageScene


class HandTool(BaseTool):
    """Pan tool: drag to scroll the viewport. Does not create any items.

    Uses the scene's views() to access the QGraphicsView and manipulate
    its scrollbars for delta-based panning.

    Also supports click-select: clicking on an annotation item selects it
    (Shift = toggle), clicking empty area clears the selection.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._last_pos: QPointF | None = None
        self._is_dragging: bool = False
        self._click_was_on_item: bool = False

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
        self._last_pos = None
        self._is_dragging = False
        self._click_was_on_item = False

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Start panning from the press position, or select an item."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()

        # Check for selectable item under cursor
        from tools.selection_tool import _get_selectable_types
        sel_types = _get_selectable_types()
        from items.selection_overlay_item import SelectionOverlayItem

        items_at = scene.items(QRectF(pos.x() - 3, pos.y() - 3, 6, 6))
        hit_item = next(
            (i for i in items_at
             if isinstance(i, sel_types)
             and not isinstance(i, SelectionOverlayItem)),
            None,
        )

        if hit_item:
            self._click_was_on_item = True
            shift = bool(event.modifiers()
                         & Qt.KeyboardModifier.ShiftModifier)
            if shift:
                if hit_item in scene._selected_items:
                    scene.remove_from_selection(hit_item)
                else:
                    scene.add_to_selection(hit_item)
            else:
                scene.set_selection([hit_item])
            return

        # Click on empty area → clear selection + start panning
        self._click_was_on_item = False
        if not bool(event.modifiers()
                    & Qt.KeyboardModifier.ShiftModifier):
            scene.clear_selection()

        self._last_pos = event.screenPos()
        self._is_dragging = True
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ClosedHandCursor)

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Pan the view by the mouse delta."""
        if not self._is_dragging or self._last_pos is None:
            return

        current_pos = event.screenPos()
        dx = current_pos.x() - self._last_pos.x()
        dy = current_pos.y() - self._last_pos.y()
        self._last_pos = current_pos

        views = scene.views()
        if views:
            view = views[0]
            h_bar = view.horizontalScrollBar()
            v_bar = view.verticalScrollBar()
            h_bar.setValue(h_bar.value() - int(dx))
            v_bar.setValue(v_bar.value() - int(dy))

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Stop panning, restore open hand cursor."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self._last_pos = None
            for view in scene.views():
                view.setCursor(Qt.CursorShape.OpenHandCursor)
        self._click_was_on_item = False
