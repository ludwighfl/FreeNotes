"""Pen tool – draws smooth strokes on the PDF canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QObject, QRectF
from PySide6.QtGui import QPainterPath
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

        # Skip if clicking on a TextBox
        from items import TextBoxItem
        items_at = scene.items(QRectF(pos.x() - 2, pos.y() - 2, 4, 4))
        if any(isinstance(i, TextBoxItem) for i in items_at):
            return

        # Only draw on pages
        page_index = scene.get_page_index_at(pos)
        if page_index < 0:
            return

        # Start new path
        self._points = [pos]
        self._current_path = QPainterPath()
        self._current_path.moveTo(pos)

        # Create stroke item with current style
        style = ToolStyle(
            color=self.style.color,
            width=self.style.width,
            opacity=self.style.opacity,
            tool_type="pen",
        )
        self._current_item = StrokeItem(self._current_path, style, page_index)
        scene.addItem(self._current_item)

        # Track in scene
        scene.add_stroke_item(self._current_item, page_index)

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Extend the current stroke to the mouse position."""
        if self._current_path is None or self._current_item is None:
            return

        pos = event.scenePos()
        self._points.append(pos)
        self._current_path.lineTo(pos)
        self._current_item.update_path(self._current_path)

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Finalize the stroke with path smoothing."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._current_item is None:
            return

        self._finalize_stroke(scene)

    def _finalize_stroke(self, scene: PageScene) -> None:
        """Apply smoothing and clean up internal state."""
        if self._current_item is not None and len(self._points) >= 2:
            smoothed = self._smooth_path(self._points)
            self._current_item.update_path(smoothed)

        self._last_completed_item = self._current_item
        self._current_path = None
        self._current_item = None
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
