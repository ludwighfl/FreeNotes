"""Highlight item – a path-based QGraphicsItem for horizontal marker strokes."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QPainterPath, QPainterPathStroker, QColor, QBrush
from PySide6.QtWidgets import (
    QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
    QGraphicsSceneHoverEvent,
)

from core.tool_style import ToolStyle


class HighlightItem(QGraphicsItem):
    """A single highlighter stroke rendered as a horizontal QPainterPath.

    The Y-coordinate is locked to the position of the initial click.
    All subsequent mouse movements only affect the X-axis, producing
    a perfectly horizontal marker stroke with rounded ends.

    Rendered at ZValue=5 (above PDF pages, below pen strokes).
    """

    DEFAULT_OPACITY: float = 0.35
    DEFAULT_WIDTH: float = 16.0

    def __init__(
        self,
        style: ToolStyle,
        page_index: int = -1,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._style: ToolStyle = style
        self._page_index: int = page_index
        self._path: QPainterPath = QPainterPath()
        self._fixed_y: float | None = None
        self._outline_mode: bool = False  # True after pixel-erase
        self._is_selected: bool = False
        self._cached_br: QRectF | None = None

        self.setZValue(5)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    # ------------------------------------------------------------------
    # Stroke lifecycle
    # ------------------------------------------------------------------

    def start(self, pos: QPointF) -> None:
        """Begin a stroke – freeze Y to the click position.

        Args:
            pos: Initial click position in scene coordinates.
        """
        self._fixed_y = pos.y()
        fixed_pos = QPointF(pos.x(), self._fixed_y)
        self._path = QPainterPath()
        self._path.moveTo(fixed_pos)
        self.prepareGeometryChange()
        self._cached_br = None
        self.update()

    def extend(self, pos: QPointF) -> None:
        """Extend the stroke horizontally – Y stays locked.

        Args:
            pos: Current mouse position (only X is used).
        """
        if self._fixed_y is None:
            return
        fixed_pos = QPointF(pos.x(), self._fixed_y)
        self._path.lineTo(fixed_pos)
        self.prepareGeometryChange()
        self._cached_br = None
        self.update()

    def finish(self) -> None:
        """Finish the stroke – release the Y lock."""
        self._fixed_y = None
        self._cached_br = None

    # ------------------------------------------------------------------
    # QGraphicsItem interface
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        if self._cached_br is not None:
            return self._cached_br
        if self._path.isEmpty():
            return QRectF(0, 0, 0, 0)
        if self._outline_mode:
            self._cached_br = self._path.boundingRect().adjusted(-2, -2, 2, 2)
        else:
            padding = self._style.width / 2.0 + 4.0
            self._cached_br = self._path.boundingRect().adjusted(
                -padding, -padding, padding, padding
            )
        return self._cached_br

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        if self._path.isEmpty():
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Use Darken mode so overlapping highlighter strokes do not add their opacity
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Darken)

        # Simulate opacity by blending the color with white into an opaque pastel color
        c = QColor(self._style.color)
        opacity = self.DEFAULT_OPACITY
        r = 1.0 - opacity * (1.0 - c.redF())
        g = 1.0 - opacity * (1.0 - c.greenF())
        b = 1.0 - opacity * (1.0 - c.blueF())
        solid_color = QColor.fromRgbF(r, g, b, 1.0)

        if self._outline_mode:
            # After pixel-erase: path IS the filled outline, just fill it
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(solid_color))
            painter.drawPath(self._path)
        else:
            # Normal stroke rendering
            pen = QPen()
            pen.setColor(solid_color)
            pen.setWidthF(self._style.width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._path)
            
        painter.restore()

        # Selection frame
        hide_ui = getattr(self.scene(), "_is_rendering_thumbnail", False)
        if self._is_selected and not hide_ui:
            painter.save()
            sel_pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
            sel_pen.setDashPattern([6, 4])
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setOpacity(1.0)
            painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))
            painter.restore()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def page_index(self) -> int:
        return self._page_index

    @property
    def style(self) -> ToolStyle:
        return self._style

    @property
    def path(self) -> QPainterPath:
        return self._path

    def set_path(self, path: QPainterPath) -> None:
        """Replace the path (for undo/redo or deserialization)."""
        self.prepareGeometryChange()
        self._path = path
        self._cached_br = None
        self.update()

    def restore_original_path(self, path: QPainterPath) -> None:
        """Restore the original path and exit outline mode.

        Makes a deep copy so the item and the undo command never share
        the same QPainterPath object.
        """
        self.prepareGeometryChange()
        self._outline_mode = False
        copy = QPainterPath()
        copy.addPath(path)
        self._path = copy
        self._cached_br = None
        self.update()

    def subtract_path(self, eraser_ellipse: QPainterPath) -> bool:
        """Erase part of this highlighter stroke using X-range clipping.

        Instead of geometric subtraction (which would bite into the width),
        this only shortens or splits the stroke horizontally. The width
        and rounded caps are always preserved.

        Args:
            eraser_ellipse: QPainterPath (eraser shape) to subtract.

        Returns:
            True if the stroke still has visible content.
            False if the stroke was fully erased (item should be removed).
        """
        if self._path.isEmpty():
            return False

        # Get the highlight's horizontal extent
        h_rect = self._path.boundingRect()
        h_left = h_rect.left()
        h_right = h_rect.right()

        # Get the eraser's horizontal extent
        e_rect = eraser_ellipse.boundingRect()
        e_left = e_rect.left()
        e_right = e_rect.right()

        # No horizontal overlap → nothing to erase
        if e_left >= h_right or e_right <= h_left:
            return True

        # Determine the Y center of the highlight (fixed Y)
        h_y = h_rect.center().y()

        # Check if eraser actually overlaps vertically with the stroke
        half_w = self._style.width / 2.0
        if e_rect.bottom() < h_y - half_w or e_rect.top() > h_y + half_w:
            return True  # No vertical overlap

        # Calculate remaining X segments
        segments: list[tuple[float, float]] = []

        # Left segment: from h_left to min(e_left, h_right)
        if e_left > h_left:
            segments.append((h_left, min(e_left, h_right)))

        # Right segment: from max(e_right, h_left) to h_right
        if e_right < h_right:
            segments.append((max(e_right, h_left), h_right))

        # Filter out tiny segments
        min_len = 2.0
        segments = [(l, r) for l, r in segments if (r - l) > min_len]

        if not segments:
            return False  # Fully erased

        # Rebuild path from first segment (item keeps the first one)
        new_path = QPainterPath()
        x_start, x_end = segments[0]
        new_path.moveTo(QPointF(x_start, h_y))
        new_path.lineTo(QPointF(x_end, h_y))

        self.prepareGeometryChange()
        self._path = new_path
        self._outline_mode = False  # Stay in normal stroke mode
        self._cached_br = None
        self.update()

        # Store extra segments for the eraser tool to create new items
        self._extra_segments = segments[1:]

        return True

    def pop_extra_segments(self) -> list[tuple[float, float]]:
        """Return and clear any extra segments created by a split erase.

        Each tuple is (x_start, x_end) at the highlight's fixed Y.
        The eraser tool should create new HighlightItems for these.
        """
        segs = getattr(self, "_extra_segments", [])
        self._extra_segments = []
        return segs

    # ------------------------------------------------------------------
    # Selection support
    # ------------------------------------------------------------------

    def set_selected(self, selected: bool) -> None:
        """Toggle selection visual frame."""
        self._is_selected = selected
        self.update()

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        from app.app_state import AppState
        if AppState().active_tool_name in {"selection", "hand"}:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        event.accept()

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()

    # ------------------------------------------------------------------
    # Bounding box resize support
    # ------------------------------------------------------------------

    def apply_bounding_box_resize(self, new_br: QRectF) -> None:
        """Scale the path so its scene bounding box matches *new_br*."""
        from PySide6.QtGui import QTransform

        old_br = self.mapToScene(self.boundingRect()).boundingRect()
        if old_br.width() < 0.01 or old_br.height() < 0.01:
            return

        sx = new_br.width() / old_br.width()
        sy = new_br.height() / old_br.height()

        path_scene = self.mapToScene(self._path)

        transform = QTransform()
        transform.translate(new_br.left(), new_br.top())
        transform.scale(sx, sy)
        transform.translate(-old_br.left(), -old_br.top())

        new_path_scene = transform.map(path_scene)
        new_path_local = self.mapFromScene(new_path_scene)

        self.prepareGeometryChange()
        self._path = new_path_local
        self._cached_br = None
        self.update()

    def get_path_state(self) -> tuple:
        """Snapshot path + position for undo."""
        return (QPainterPath(self._path), QPointF(self.pos()))

    def set_path_state(self, path: QPainterPath, pos: QPointF) -> None:
        """Restore path + position from undo snapshot."""
        self.prepareGeometryChange()
        self._path = path
        self.setPos(pos)
        self._cached_br = None
        self.update()

    # ------------------------------------------------------------------
    # Serialization (for clone_page_annotations)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        points = []
        for i in range(self._path.elementCount()):
            el = self._path.elementAt(i)
            points.append((el.x, el.y))
        return {
            "type": "highlight",
            "points": points,
            "color": self._style.color.name(),
            "width": self._style.width,
            "page_index": self._page_index,
            "pos": (self.pos().x(), self.pos().y()),
        }

    @classmethod
    def from_dict(cls, d: dict) -> HighlightItem:
        path = QPainterPath()
        pts = d.get("points", [])
        if pts:
            path.moveTo(pts[0][0], pts[0][1])
            for px, py in pts[1:]:
                path.lineTo(px, py)
        style = ToolStyle(
            color=QColor(d["color"]),
            width=d["width"],
        )
        item = cls(style=style, page_index=d.get("page_index", -1))
        item._path = path
        if "pos" in d:
            item.setPos(QPointF(*d["pos"]))
        return item

