"""Highlighter tool – draws Y-locked semitransparent strokes over PDF text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QObject, QRectF
from PySide6.QtGui import QPainterPath, QPainter
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from app.app_state import AppState
from core.tool_style import ToolStyle
from items.highlight_item import HighlightItem
from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class HighlighterTool(BaseTool):
    """Highlighter tool: draws horizontal, semitransparent path strokes.

    Y-coordinate is locked on press – only X changes during drag.
    Strokes use RoundCap/RoundJoin and fixed 0.35 opacity.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fixed_y: float | None = None
        self._current_path: QPainterPath | None = None
        self._last_drawn_x: float | None = None
        self._current_page_index: int = -1
        self._last_completed_item: HighlightItem | None = None
        self._active_style: ToolStyle | None = None

    @property
    def last_completed_item(self) -> HighlightItem | None:
        """The most recently completed HighlightItem (set after on_release)."""
        return self._last_completed_item

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    def activate(self, scene: PageScene) -> None:
        for view in scene.views():
            view.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self, scene: PageScene) -> None:
        self._fixed_y = None
        self._current_path = None
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()

        page_index = scene.get_page_index_at(pos)
        if page_index < 0:
            return

        # Skip if clicking on a TextBox
        from PySide6.QtCore import QRectF as _QRF
        rect = _QRF(pos.x() - 2, pos.y() - 2, 4, 4)
        for box in scene.get_textboxes_for_page(page_index):
            if box.sceneBoundingRect().intersects(rect):
                return

        app_style = AppState().tool_style
        self._active_style = ToolStyle(
            color=app_style.color,
            width=app_style.width,
            opacity=0.35,
            tool_type="highlighter",
        )
        
        self._fixed_y = pos.y()
        self._current_path = QPainterPath()
        self._current_path.moveTo(pos.x(), self._fixed_y)
        self._last_drawn_x = pos.x()
        self._current_page_index = page_index

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if self._fixed_y is None or self._current_path is None:
            return
            
        pos = event.scenePos()
        
        # Throttle visual updates
        if self._last_drawn_x is not None:
            if abs(pos.x() - self._last_drawn_x) < 2.0:
                return
        self._last_drawn_x = pos.x()
        
        old_rect = self._current_path.boundingRect()
        self._current_path.lineTo(pos.x(), self._fixed_y)
        new_rect = self._current_path.boundingRect()
        
        # Force a targeted scene redraw to paint the overlay path
        w = self._active_style.width if self._active_style else 16.0
        update_rect = old_rect.united(new_rect).adjusted(-w, -w, w, w)
        scene.update(update_rect)

    def draw_active_stroke(self, painter: QPainter, rect: QRectF) -> None:
        """Called by PageScene.drawForeground to render the active highlight."""
        if self._current_path is not None and not self._current_path.isEmpty() and self._active_style:
            from PySide6.QtGui import QPen, QColor
            
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Darken)
            
            c = QColor(self._active_style.color)
            opacity = self._active_style.opacity
            r = 1.0 - opacity * (1.0 - c.redF())
            g = 1.0 - opacity * (1.0 - c.greenF())
            b = 1.0 - opacity * (1.0 - c.blueF())
            solid_color = QColor.fromRgbF(r, g, b, 1.0)
            
            pen = QPen(solid_color)
            pen.setWidthF(self._active_style.width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._current_path)
            painter.restore()

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._fixed_y is None or self._current_path is None:
            return
            
        # Create and add the actual item once on release
        if self._active_style:
            item = HighlightItem(self._active_style, self._current_page_index)
            item.set_path(self._current_path)
            scene.addItem(item)
            scene.add_highlight_item(item, self._current_page_index)
            
            self._last_completed_item = item
            
            # Clear the overlay path by requesting a final update of its bounds
            w = self._active_style.width
            scene.update(self._current_path.boundingRect().adjusted(-w, -w, w, w))
            
        self._fixed_y = None
        self._current_path = None
        self._last_drawn_x = None
        self.tool_action_completed.emit()
