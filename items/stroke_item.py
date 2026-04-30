"""Stroke item – a QGraphicsItem representing a single pen/highlighter stroke."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen, QColor, QBrush
from PySide6.QtWidgets import (
    QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
    QGraphicsSceneHoverEvent,
)
from PySide6.QtCore import Qt

from core.tool_style import ToolStyle


class StrokeItem(QGraphicsItem):
    """A single drawn stroke rendered as a QPainterPath.

    The stroke is always drawn above PDF pages (ZValue=10) and uses
    round caps/joins for smooth visual appearance. The page_index
    attribute tracks which PDF page this stroke belongs to.
    """

    def __init__(
        self,
        path: QPainterPath,
        style: ToolStyle,
        page_index: int = -1,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._path: QPainterPath = path
        self._style: ToolStyle = style
        self._page_index: int = page_index
        self._outline_mode: bool = False  # True after pixel-erase
        self._is_selected: bool = False
        self._cached_br: QRectF | None = None

        # Always above PDF pages
        self.setZValue(10)
        self.setAcceptHoverEvents(True)

        # Not selectable/movable via Qt's built-in system
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def update_path(self, path: QPainterPath) -> None:
        """Update the stroke path (called during live drawing).

        Args:
            path: The new/updated QPainterPath.
        """
        self.prepareGeometryChange()
        self._path = path
        self._cached_br = None
        self.update()

    def boundingRect(self) -> QRectF:
        """Return bounding rect with padding for pen width."""
        if self._cached_br is not None:
            return self._cached_br
        if self._path.isEmpty():
            return QRectF()
        if self._outline_mode:
            # Outline mode: path IS the filled shape, small margin suffices
            self._cached_br = self._path.boundingRect().adjusted(-2, -2, 2, 2)
        else:
            padding = self._style.width / 2.0 + 4.0
            self._cached_br = self._path.boundingRect().adjusted(-padding, -padding, padding, padding)
        return self._cached_br

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the stroke path with antialiasing and round caps/joins."""
        if self._path.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._style.opacity)

        if self._outline_mode:
            # After pixel-erase: path IS the filled outline, just fill it
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._style.color))
            painter.drawPath(self._path)
        else:
            # Normal stroke rendering
            pen = QPen(self._style.color, self._style.width, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.strokePath(self._path, pen)

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

    @property
    def page_index(self) -> int:
        return self._page_index

    @property
    def style(self) -> ToolStyle:
        """The drawing style of this stroke."""
        return self._style

    @property
    def path(self) -> QPainterPath:
        """The current path of this stroke."""
        return self._path

    def ensure_outline_mode(self) -> None:
        """Convert to outline mode if not already.

        After this call, _path is the filled outline shape and
        _outline_mode is True. Called by the eraser BEFORE storing
        the 'original' path, so undo always restores an outline
        (avoiding thin↔outline visual mismatches).
        """
        if not self._outline_mode:
            stroker = QPainterPathStroker()
            stroker.setWidth(self._style.width)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            outline = stroker.createStroke(self._path).simplified()
            self.prepareGeometryChange()
            self._path = outline
            self._outline_mode = True
            self._cached_br = None
            self.update()

    def subtract_path(self, eraser_ellipse: QPainterPath) -> bool:
        """Subtract an eraser shape from this stroke's path.

        The caller must call ensure_outline_mode() first if they want
        to capture the pre-subtraction outline for undo.

        Args:
            eraser_ellipse: QPainterPath in **scene** coordinates to subtract.

        Returns:
            True if the stroke still has visible content after subtraction.
            False if the resulting path is empty (item should be removed).
        """
        # Ensure we're in outline mode (idempotent)
        if not self._outline_mode:
            self.ensure_outline_mode()

        # Map eraser from scene coords to item-local coords
        local_eraser = self.mapFromScene(eraser_ellipse) if self.scene() else eraser_ellipse

        new_path = self._path.subtracted(local_eraser).simplified()
        if new_path.isEmpty() or new_path.boundingRect().width() < 1:
            return False
        self.prepareGeometryChange()
        self._path = new_path
        self._cached_br = None
        self.update()
        return True

    def restore_path(self, path: QPainterPath, outline_mode: bool) -> None:
        """Restore a path and outline mode state (for undo/redo).

        Makes a deep copy so the item never shares a QPainterPath
        object with the undo command.
        """
        self.prepareGeometryChange()
        self._outline_mode = outline_mode
        copy = QPainterPath()
        copy.addPath(path)
        self._path = copy
        self._cached_br = None
        self.update()

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

        # Map path to scene, scale, map back
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
        from core.freenotes_store import FreenotesStore
        return {
            "type": "stroke",
            "points": points,
            "path_b64": FreenotesStore.serialize_path(self._path),
            "color": self._style.color.name(),
            "width": self._style.width,
            "page_index": self._page_index,
            "pos": (self.pos().x(), self.pos().y()),
            "outline_mode": self._outline_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StrokeItem:
        from core.freenotes_store import FreenotesStore
        if "path_b64" in d:
            path = FreenotesStore.deserialize_path(d["path_b64"])
        else:
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
        item = cls(path=path, style=style, page_index=d.get("page_index", -1))
        item._outline_mode = d.get("outline_mode", False)
        if "pos" in d:
            item.setPos(QPointF(*d["pos"]))
        return item

