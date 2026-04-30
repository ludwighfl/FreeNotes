"""Pen tool – draws smooth strokes on the PDF canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QObject, QRectF
from PySide6.QtGui import QPainterPath, QPainter
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from tools.base_tool import BaseTool
from items.stroke_item import StrokeItem
from core.tool_style import ToolStyle

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class PenTool(BaseTool):
    """Pen tool: draws smooth, antialiased strokes on PDF pages.

    During drawing, a StrokeItem is updated in real-time with a growing
    QPainterPath. On release, the path is smoothed using Chaikin's
    corner-cutting algorithm for natural-looking curves.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_path: QPainterPath | None = None
        self._current_item: StrokeItem | None = None
        self._points: list[QPointF] = []
        self._last_completed_item: StrokeItem | None = None
        self._last_drawn_pos: QPointF | None = None
        self._current_page_index: int = -1

    @property
    def last_completed_item(self) -> StrokeItem | None:
        """The most recently completed StrokeItem (set after on_release)."""
        return self._last_completed_item

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    def activate(self, scene: PageScene) -> None:
        """Set cross cursor on all views."""
        for view in scene.views():
            view.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self, scene: PageScene) -> None:
        """Restore cursor and finalize any in-progress stroke."""
        if self._current_item is not None:
            self._finalize_stroke(scene)
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Start a new stroke at the press position."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()

        # Only draw on pages
        page_index = scene.get_page_index_at(pos)
        if page_index < 0:
            return

        # Skip if clicking on a TextBox
        rect = QRectF(pos.x() - 2, pos.y() - 2, 4, 4)
        for box in scene.get_textboxes_for_page(page_index):
            if box.sceneBoundingRect().intersects(rect):
                return

        # Start new path
        self._points = [pos]
        self._current_path = QPainterPath()
        self._current_path.moveTo(pos)
        self._last_drawn_pos = pos
        self._current_page_index = page_index

        # Do not create StrokeItem yet to avoid BSP tree lags.
        # It will be rendered via draw_active_stroke in PageScene.drawForeground.

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Extend the current stroke to the mouse position."""
        if self._current_path is None:
            return

        pos = event.scenePos()
        self._points.append(pos)
        
        # Track old bounds to calculate update rect
        old_rect = self._current_path.boundingRect()
        self._current_path.lineTo(pos)
        new_rect = self._current_path.boundingRect()

        # Throttle visual updates
        if self._last_drawn_pos is not None:
            dx = abs(pos.x() - self._last_drawn_pos.x())
            dy = abs(pos.y() - self._last_drawn_pos.y())
            if dx + dy < 2.0:
                return
        self._last_drawn_pos = pos
        
        # Force a targeted scene redraw to paint the overlay path
        w = self.style.width
        update_rect = old_rect.united(new_rect).adjusted(-w, -w, w, w)
        scene.update(update_rect)

    def draw_active_stroke(self, painter: QPainter, rect: QRectF) -> None:
        """Called by PageScene.drawForeground to render the active path."""
        if self._current_path is not None and not self._current_path.isEmpty():
            from PySide6.QtGui import QPen
            
            pen = QPen(self.style.color)
            pen.setWidthF(self.style.width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            
            painter.save()
            painter.setOpacity(self.style.opacity)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawPath(self._current_path)
            painter.restore()

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Finalize the stroke with path smoothing."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._current_path is None:
            return

        self._finalize_stroke(scene)

    def _finalize_stroke(self, scene: PageScene) -> None:
        """Apply smoothing and create the final StrokeItem."""
        if self._current_path is not None and len(self._points) >= 2:
            smoothed = self._smooth_path(self._points)
            
            style = ToolStyle(
                color=self.style.color,
                width=self.style.width,
                opacity=self.style.opacity,
                tool_type="pen",
            )
            item = StrokeItem(smoothed, style, self._current_page_index)
            scene.addItem(item)
            scene.add_stroke_item(item, self._current_page_index)
            self._last_completed_item = item
            
            # Clear the overlay path by requesting a final update of its bounds
            w = self.style.width
            scene.update(self._current_path.boundingRect().adjusted(-w, -w, w, w))

        self._current_path = None
        self._points.clear()
        self.tool_action_completed.emit()

    @staticmethod
    def _smooth_path(points: list[QPointF]) -> QPainterPath:
        """Smooth a list of points using Chaikin's corner-cutting algorithm.

        Applies two iterations of Chaikin subdivision for natural curves,
        then builds a QPainterPath using cubic Bézier segments.

        Args:
            points: Raw input points from mouse events.

        Returns:
            A smooth QPainterPath.
        """
        if len(points) < 2:
            path = QPainterPath()
            if points:
                path.moveTo(points[0])
            return path

        # Skip smoothing for short strokes (< 4 points)
        if len(points) < 4:
            path = QPainterPath()
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            return path

        # Chaikin subdivision – 2 iterations
        subdivided = list(points)
        for _ in range(2):
            new_points: list[QPointF] = [subdivided[0]]
            for i in range(len(subdivided) - 1):
                p0 = subdivided[i]
                p1 = subdivided[i + 1]
                q = QPointF(0.75 * p0.x() + 0.25 * p1.x(),
                            0.75 * p0.y() + 0.25 * p1.y())
                r = QPointF(0.25 * p0.x() + 0.75 * p1.x(),
                            0.25 * p0.y() + 0.75 * p1.y())
                new_points.append(q)
                new_points.append(r)
            new_points.append(subdivided[-1])
            subdivided = new_points

        # Build smooth path using cubic Bézier
        path = QPainterPath()
        path.moveTo(subdivided[0])

        if len(subdivided) < 3:
            for pt in subdivided[1:]:
                path.lineTo(pt)
            return path

        # Use cubic Bézier with control points from neighboring midpoints
        for i in range(1, len(subdivided) - 1, 2):
            if i + 1 < len(subdivided):
                path.quadTo(subdivided[i], subdivided[i + 1])
            else:
                path.lineTo(subdivided[i])

        # Connect to last point if not already there
        if subdivided:
            path.lineTo(subdivided[-1])

        return path
