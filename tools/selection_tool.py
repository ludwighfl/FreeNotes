"""Selection tool – rect/lasso select and drag-move of selected items."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QSizeF, QObject
from PySide6.QtGui import QPen, QColor, QBrush, QPainterPath, QPainter
from PySide6.QtWidgets import (
    QGraphicsSceneMouseEvent,
    QGraphicsRectItem,
    QGraphicsPathItem,
)

from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


# Lazy-loaded tuple of selectable item types
_SELECTABLE_TYPES: tuple | None = None


def _get_selectable_types() -> tuple:
    """Return selectable item types – lazy import."""
    global _SELECTABLE_TYPES
    if _SELECTABLE_TYPES is None:
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem
        _SELECTABLE_TYPES = (StrokeItem, HighlightItem, TextBoxItem, ShapeItem, ImageItem)
    return _SELECTABLE_TYPES


class SelectionRectVisual(QGraphicsRectItem):
    """Custom rect item with rounded corners, double-stroke and glassmorphic fill."""
    def paint(self, painter: QPainter, option, widget=None) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Glassmorphic Fill
        fill_color = QColor(59, 123, 245, 25)
        painter.setBrush(QBrush(fill_color))

        # 2. Outer Soft Glow Stroke
        glow_pen = QPen(QColor(59, 123, 245, 45), 3.0)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glow_pen)
        painter.drawRoundedRect(rect, 6.0, 6.0)

        # 3. Inner Crisp Dashed Stroke
        dash_pen = QPen(QColor("#3B7BF5"), 1.2, Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([5, 4])
        dash_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        dash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(dash_pen)
        painter.drawRoundedRect(rect, 6.0, 6.0)

        painter.restore()


class SelectionLassoVisual(QGraphicsPathItem):
    """Custom path item with smooth curves, double-stroke and glassmorphic fill."""
    def paint(self, painter: QPainter, option, widget=None) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        path = self.path()
        if path.isEmpty():
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Glassmorphic Fill
        fill_color = QColor(59, 123, 245, 20)
        painter.setBrush(QBrush(fill_color))

        # 2. Outer Soft Glow Stroke
        glow_pen = QPen(QColor(59, 123, 245, 45), 3.5)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(glow_pen)
        painter.drawPath(path)

        # 3. Inner Crisp Dashed Stroke
        dash_pen = QPen(QColor("#3B7BF5"), 1.3, Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([5, 4])
        dash_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        dash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(dash_pen)
        painter.drawPath(path)

        painter.restore()


class SelectionTool(BaseTool):
    """Selection tool: rect/lasso select and drag-move.

    - Click on item: select (Shift = toggle).
    - Drag on empty area: rect-select or lasso-select (mode set via toolbar).
    - Drag on selected item: move all selected items.
    """



    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode: str = "idle"
        self._select_mode: str = "rect"  # "rect" or "lasso"
        self._drag_start: QPointF | None = None
        self._current_pos: QPointF | None = None
        self._lasso_path: list[QPointF] = []
        self._rubber_band_item: QGraphicsRectItem | None = None
        self._lasso_item: QGraphicsPathItem | None = None
        self._drag_item_positions: dict = {}
        self._live_preview_items: set = set()

    # ── Lifecycle ──────────────────────────────────────────────

    def activate(self, scene: PageScene) -> None:
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def deactivate(self, scene: PageScene) -> None:
        scene.clear_selection()
        self._cleanup_visuals(scene)
        self._mode = "idle"
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def set_mode(self, mode: str) -> None:
        """Set selection mode ('rect' or 'lasso')."""
        self._select_mode = mode

    # ── Press ──────────────────────────────────────────────────

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        # Right-click → context menu
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event, scene)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()
        modifiers = event.modifiers()
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        sel_types = _get_selectable_types()
        from items.selection_overlay_item import SelectionOverlayItem

        items_at = scene.items(QRectF(pos.x() - 5, pos.y() - 5, 10, 10))

        # Check if we clicked on a control handle. If so, let Qt's default dispatch handle it.
        from items.handle_item import ResizeHandleItem
        from items.rotate_handle_item import RotateHandleItem
        from items.options_handle_item import OptionsHandleItem
        from items.move_handle_item import MoveHandleItem

        if any(isinstance(i, (ResizeHandleItem, RotateHandleItem, OptionsHandleItem, MoveHandleItem)) for i in items_at):
            return

        # Find item under cursor (prioritizing non-textbox items)
        selectable_hits = [
            i for i in items_at
            if isinstance(i, sel_types)
            and not isinstance(i, SelectionOverlayItem)
        ]
        from items.text_box_item import TextBoxItem
        selectable_hits.sort(key=lambda i: 1 if isinstance(i, TextBoxItem) else 0)
        hit_item = selectable_hits[0] if selectable_hits else None

        # Click on already-selected item → start drag
        if hit_item and hit_item in scene._selected_items:
            self._mode = "dragging"
            self._drag_start = pos
            self._drag_item_positions = {
                item: item.pos()
                for item in scene._selected_items
            }
            self._drag_before_state = {
                item: item.capture_state()
                for item in scene._selected_items
                if hasattr(item, "capture_state")
            }
            return

        # Click on new item without Shift → select only this
        if hit_item and not shift:
            scene.set_selection([hit_item])
            self._mode = "dragging"
            self._drag_start = pos
            self._drag_item_positions = {hit_item: hit_item.pos()}
            self._drag_before_state = {
                item: item.capture_state()
                for item in scene._selected_items
                if hasattr(item, "capture_state")
            }
            return

        # Shift+click → toggle in/out of selection
        if hit_item and shift:
            if hit_item in scene._selected_items:
                scene.remove_from_selection(hit_item)
            else:
                scene.add_to_selection(hit_item)
            return

        # Click on empty area → clear + start area select
        if not shift:
            scene.clear_selection()

        self._drag_start = pos
        self._current_pos = pos

        if self._select_mode == "lasso":
            self._mode = "lasso_selecting"
            self._lasso_path = [pos]
            self._start_lasso_visual(scene, pos)
        else:
            self._mode = "rect_selecting"
            self._start_rect_visual(scene, pos)

    # ── Move ───────────────────────────────────────────────────

    def _update_live_preview(self, scene: PageScene, items_in_area: list) -> None:
        new_set = set(items_in_area)
        # Clear items no longer in drag area
        for item in (self._live_preview_items - new_set):
            if hasattr(item, "_is_preview_highlight"):
                item._is_preview_highlight = False
                item.update()

        # Add preview highlight to new items
        for item in (new_set - self._live_preview_items):
            item._is_preview_highlight = True
            item.update()

        self._live_preview_items = new_set

    def _clear_live_preview(self) -> None:
        for item in self._live_preview_items:
            if hasattr(item, "_is_preview_highlight"):
                item._is_preview_highlight = False
                item.update()
        self._live_preview_items.clear()

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        pos = event.scenePos()
        self._current_pos = pos

        if self._mode == "rect_selecting":
            self._update_rect_visual(pos, scene)
        elif self._mode == "lasso_selecting":
            self._lasso_path.append(pos)
            self._update_lasso_visual(scene)
        elif self._mode == "dragging":
            if self._drag_start is None:
                return
            delta = pos - self._drag_start
            for item, start_pos in self._drag_item_positions.items():
                item.setPos(start_pos + delta)
            scene._update_selection_overlay()

    # ── Release ────────────────────────────────────────────────

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        modifiers = event.modifiers()
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if self._mode == "rect_selecting":
            self._finish_rect_selection(scene, shift)
        elif self._mode == "lasso_selecting":
            self._finish_lasso_selection(scene, shift)
        elif self._mode == "dragging":
            self._finish_drag(scene)

        self._mode = "idle"
        self._drag_start = None
        self._cleanup_visuals(scene)

    def on_double_click(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        from items.text_box_item import TextBoxItem
        items_at = scene.items(event.scenePos())
        for item in items_at:
            if isinstance(item, TextBoxItem):
                scene.tool_switch_requested.emit("text")
                item.start_editing()
                item.mousePressEvent(event)
                item.mouseDoubleClickEvent(event)
                break

    # ── Rect visual ────────────────────────────────────────────

    def _start_rect_visual(self, scene: PageScene, pos: QPointF) -> None:
        self._rubber_band_item = SelectionRectVisual(
            QRectF(pos, QSizeF(0, 0)))
        pen = QPen(QColor("#3B7BF5"), 1.0, Qt.PenStyle.DashLine)
        self._rubber_band_item.setPen(pen)
        self._rubber_band_item.setBrush(
            QBrush(QColor(59, 123, 245, 30)))
        self._rubber_band_item.setZValue(1000)
        scene.addItem(self._rubber_band_item)

    def _update_rect_visual(self, pos: QPointF, scene: PageScene) -> None:
        if self._rubber_band_item and self._drag_start:
            rect = QRectF(self._drag_start, pos).normalized()
            self._rubber_band_item.setRect(rect)
            if rect.width() >= 3 or rect.height() >= 3:
                sel_types = _get_selectable_types()
                from items.selection_overlay_item import SelectionOverlayItem
                items_in_rect = [
                    i for i in scene.items(rect)
                    if isinstance(i, sel_types)
                    and not isinstance(i, SelectionOverlayItem)
                ]
                self._update_live_preview(scene, items_in_rect)
            else:
                self._clear_live_preview()

    def _finish_rect_selection(self, scene: PageScene, shift: bool) -> None:
        self._clear_live_preview()
        if not self._drag_start or not self._current_pos:
            return
        rect = QRectF(self._drag_start, self._current_pos).normalized()
        if rect.width() < 3 and rect.height() < 3:
            return  # too small, treat as click (already handled)

        sel_types = _get_selectable_types()
        from items.selection_overlay_item import SelectionOverlayItem
        items_in_rect = [
            i for i in scene.items(rect)
            if isinstance(i, sel_types)
            and not isinstance(i, SelectionOverlayItem)
        ]
        if shift:
            for item in items_in_rect:
                scene.add_to_selection(item)
        else:
            scene.set_selection(items_in_rect)

    # ── Lasso visual ───────────────────────────────────────────

    def _start_lasso_visual(self, scene: PageScene, pos: QPointF) -> None:
        path = QPainterPath(pos)
        self._lasso_item = SelectionLassoVisual(path)
        pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        self._lasso_item.setPen(pen)
        self._lasso_item.setBrush(
            QBrush(QColor(59, 123, 245, 20)))
        self._lasso_item.setZValue(1000)
        scene.addItem(self._lasso_item)

    def _update_lasso_visual(self, scene: PageScene) -> None:
        if not self._lasso_item or not self._lasso_path:
            return
        path = QPainterPath(self._lasso_path[0])
        for p in self._lasso_path[1:]:
            path.lineTo(p)
        self._lasso_item.setPath(path)

        if len(self._lasso_path) >= 3:
            closed_path = QPainterPath(self._lasso_path[0])
            for p in self._lasso_path[1:]:
                closed_path.lineTo(p)
            closed_path.closeSubpath()

            sel_types = _get_selectable_types()
            from items.selection_overlay_item import SelectionOverlayItem
            items_in_lasso = [
                i for i in scene.items(closed_path)
                if isinstance(i, sel_types)
                and not isinstance(i, SelectionOverlayItem)
            ]
            self._update_live_preview(scene, items_in_lasso)
        else:
            self._clear_live_preview()

    def _finish_lasso_selection(self, scene: PageScene, shift: bool) -> None:
        self._clear_live_preview()
        if len(self._lasso_path) < 3:
            return
        closed_path = QPainterPath(self._lasso_path[0])
        for p in self._lasso_path[1:]:
            closed_path.lineTo(p)
        closed_path.closeSubpath()

        sel_types = _get_selectable_types()
        from items.selection_overlay_item import SelectionOverlayItem
        items_in_lasso = [
            i for i in scene.items(closed_path)
            if isinstance(i, sel_types)
            and not isinstance(i, SelectionOverlayItem)
        ]
        if shift:
            for item in items_in_lasso:
                scene.add_to_selection(item)
        else:
            scene.set_selection(items_in_lasso)

    # ── Drag finish ────────────────────────────────────────────

    def _finish_drag(self, scene: PageScene) -> None:
        from commands.transform_items_command import TransformItemsCommand
        from core import undo_stack

        before = getattr(self, "_drag_before_state", {})
        after = {
            item: item.capture_state()
            for item in scene._selected_items
            if hasattr(item, "capture_state")
        }

        has_changed = False
        for item, b_state in before.items():
            if after.get(item) != b_state:
                has_changed = True
                break

        if has_changed:
            cmd = TransformItemsCommand(
                items_before=before,
                items_after=after,
                scene=scene,
                text="Verschieben",
            )
            undo_stack.push(cmd)

        self._drag_item_positions = {}
        self._drag_before_state = {}

    # ── Cleanup ────────────────────────────────────────────────

    def _cleanup_visuals(self, scene: PageScene) -> None:
        self._clear_live_preview()
        if self._rubber_band_item:
            scene.removeItem(self._rubber_band_item)
            self._rubber_band_item = None
        if self._lasso_item:
            scene.removeItem(self._lasso_item)
            self._lasso_item = None
        self._lasso_path = []

    # ── Context menu ───────────────────────────────────────────

    def _show_context_menu(
        self, event: QGraphicsSceneMouseEvent, scene: PageScene
    ) -> None:
        """Show unified right-click context menu."""
        from tools.tool_context_menu import build_tool_context_menu
        build_tool_context_menu(event, scene)
