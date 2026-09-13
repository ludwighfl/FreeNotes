"""Shape item — QGraphicsItem for geometric shape annotations (6 types)."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QPainterPathStroker, QPen, QColor,
    QBrush, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
    QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent,
)

from core.shape_style import ShapeStyle, ShapeType
from items.handle_item import HandlePosition
from items.interactive_item import IRectResizable, ILinearItem


class ShapeItem(QGraphicsItem, IRectResizable, ILinearItem):
    """A geometric shape annotation supporting 6 shape types.

    Uses local coordinates: setPos(topLeft), _rect = QRectF(0, 0, w, h).
    Handle children provide resize, move, and rotate functionality.
    """

    MIN_SIZE: float = 8.0
    HIT_PADDING: float = 6.0
    HANDLE_POSITIONS: list[HandlePosition] = list(HandlePosition)

    def __init__(
        self,
        rect: QRectF,
        style: ShapeStyle,
        page_index: int = -1,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        # Store as local coords: pos = topLeft, _rect = (0, 0, w, h)
        self._rect: QRectF = QRectF(0, 0, rect.width(), rect.height())
        self._style: ShapeStyle = style.copy()
        self._page_index: int = page_index
        self._is_selected: bool = False
        self._is_selected_custom: bool = False
        self._line_dir: int = 0  # 0: TL->BR, 1: BR->TL, 2: TR->BL, 3: BL->TR
        self._cached_br: QRectF | None = None

        self.setPos(rect.topLeft())

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        # Handles are managed centrally by SelectionBoxItem

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def page_index(self) -> int:
        return self._page_index

    @property
    def style(self) -> ShapeStyle:
        return self._style

    def set_style(self, style: ShapeStyle) -> None:
        self.prepareGeometryChange()
        self._style = style.copy()
        self._cached_br = None
        self.update()

    def set_selected(self, selected: bool) -> None:
        self.prepareGeometryChange()
        self._is_selected = selected
        self._cached_br = None
        self.update()

    def set_selected_custom(self, selected: bool) -> None:
        """Show/hide selection frame (called by scene)."""
        self.prepareGeometryChange()
        self._is_selected = selected
        self._is_selected_custom = selected
        self._cached_br = None
        self.setZValue(10)
        self.update()

    def get_line_dir(self) -> int:
        return self._line_dir

    def set_line_dir(self, line_dir: int) -> None:
        self.prepareGeometryChange()
        self._line_dir = line_dir
        self._cached_br = None
        self.update()

    def _get_line_points(self) -> tuple[QPointF, QPointF]:
        r = self._rect
        if self._line_dir == 0:
            return r.topLeft(), r.bottomRight()
        elif self._line_dir == 1:
            return r.bottomRight(), r.topLeft()
        elif self._line_dir == 2:
            return r.topRight(), r.bottomLeft()
        else:
            return r.bottomLeft(), r.topRight()

    # ------------------------------------------------------------------
    # Rect accessors (scene coordinates, matching TextBoxItem interface)
    # ------------------------------------------------------------------

    def get_rect(self) -> QRectF:
        """Return the shape rect in scene coordinates (copy)."""
        return QRectF(
            self.pos().x(),
            self.pos().y(),
            self._rect.width(),
            self._rect.height(),
        )

    def set_rect(self, rect: QRectF) -> None:
        """Set the shape rect from scene coordinates."""
        self.prepareGeometryChange()
        w, h = rect.width(), rect.height()
        self.setPos(rect.topLeft())
        self._rect = QRectF(0, 0, w, h)
        self.setTransformOriginPoint(QPointF(w / 2.0, h / 2.0))
        self._cached_br = None
        self.update()

    def capture_state(self) -> dict:
        """Snapshot state for undo/redo."""
        is_linear = self._style.shape_type in (ShapeType.LINE, ShapeType.ARROW)
        state = {
            "pos": QPointF(self.pos()),
            "rect": self.get_rect(),
            "rotation": self.rotation(),
            "transform_origin": QPointF(self.transformOriginPoint()),
            "is_linear": is_linear,
        }
        if is_linear:
            state["line_dir"] = getattr(self, "_line_dir", 0)
        return state

    def restore_state(self, state: dict) -> None:
        """Restore state from snapshot."""
        self.prepareGeometryChange()
        if "line_dir" in state:
            self._line_dir = state["line_dir"]
        if "transform_origin" in state:
            self.setTransformOriginPoint(state["transform_origin"])
        if "rotation" in state:
            self.setRotation(state["rotation"])
        if "rect" in state:
            self.set_rect(state["rect"])
        self._cached_br = None
        self.update()

    def get_geometry_rect(self) -> QRectF:
        return self.get_rect()

    def set_geometry_rect(self, rect: QRectF) -> None:
        self.set_rect(rect)

    def is_linear(self) -> bool:
        """Only lines and arrows are truly linear."""
        return self._style.shape_type in (ShapeType.LINE, ShapeType.ARROW)

    def get_start_point(self) -> QPointF:
        p1, _ = self._get_line_points()
        return self.mapToScene(p1)

    def set_start_point(self, pt: QPointF) -> None:
        self._set_line_endpoints(pt, self.get_end_point())

    def get_end_point(self) -> QPointF:
        _, p2 = self._get_line_points()
        return self.mapToScene(p2)

    def set_end_point(self, pt: QPointF) -> None:
        self._set_line_endpoints(self.get_start_point(), pt)

    def _set_line_endpoints(self, p1: QPointF, p2: QPointF) -> None:
        """Set linear shape endpoints from scene coordinates."""
        sx, sy = p1.x(), p1.y()
        ex, ey = p2.x(), p2.y()
        new_scene_rect = QRectF(
            QPointF(min(sx, ex), min(sy, ey)),
            QPointF(max(sx, ex), max(sy, ey))
        )
        if ex >= sx and ey >= sy:
            ld = 0
        elif ex < sx and ey < sy:
            ld = 1
        elif ex < sx and ey >= sy:
            ld = 2
        else:
            ld = 3
        self._line_dir = ld
        self.set_rect(new_scene_rect)

    def get_rotation_angle(self) -> float:
        return self.rotation()

    def set_rotation_angle(self, angle: float) -> None:
        self.setRotation(angle)

    def get_transform_origin(self) -> QPointF:
        return self.transformOriginPoint()

    def set_transform_origin(self, origin: QPointF) -> None:
        self.setTransformOriginPoint(origin)

    def apply_scale(self, sx: float, sy: float, pivot: QPointF) -> None:
        """Scale shape geometry around a pivot point in scene space."""
        if self._style.shape_type in (ShapeType.LINE, ShapeType.ARROW):
            p1, p2 = self.get_start_point(), self.get_end_point()
            new_p1 = QPointF(pivot.x() + (p1.x() - pivot.x()) * sx, pivot.y() + (p1.y() - pivot.y()) * sy)
            new_p2 = QPointF(pivot.x() + (p2.x() - pivot.x()) * sx, pivot.y() + (p2.y() - pivot.y()) * sy)
            self._set_line_endpoints(new_p1, new_p2)
        else:
            old_w = self._rect.width()
            old_h = self._rect.height()
            new_w = max(self.MIN_SIZE, old_w * sx)
            new_h = max(self.MIN_SIZE, old_h * sy)

            origin_scene = self.mapToScene(self.transformOriginPoint())
            new_origin_scene = QPointF(
                pivot.x() + (origin_scene.x() - pivot.x()) * sx,
                pivot.y() + (origin_scene.y() - pivot.y()) * sy,
            )

            self.prepareGeometryChange()
            self._rect = QRectF(0, 0, new_w, new_h)
            new_origin = QPointF(new_w / 2.0, new_h / 2.0)
            self.setTransformOriginPoint(new_origin)
            self.setPos(new_origin_scene - new_origin)
            self._cached_br = None
            self.update()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        if self._cached_br is not None:
            return self._cached_br
        pad = self._style.stroke_width / 2.0 + self.HIT_PADDING
        if getattr(self, "_is_selected_custom", False):
            val = self._rect.adjusted(-pad - 50, -pad - 60, pad + 50, pad + 40)
        else:
            val = self._rect.adjusted(-pad, -pad, pad, pad)
        self._cached_br = val
        return val

    def shape(self) -> QPainterPath:
        """Precise hit-detection path depending on shape type."""
        path = QPainterPath()
        sw = self._style.stroke_width
        r = self._rect

        match self._style.shape_type:
            case ShapeType.LINE | ShapeType.ARROW:
                stroke = QPainterPathStroker()
                stroke.setWidth(sw + self.HIT_PADDING * 2)
                line_path = QPainterPath()
                p1, p2 = self._get_line_points()
                line_path.moveTo(p1)
                line_path.lineTo(p2)
                return stroke.createStroke(line_path)

            case ShapeType.ELLIPSE:
                path.addEllipse(r)

            case ShapeType.ROUNDED_RECT:
                path.addRoundedRect(
                    r,
                    self._style.corner_radius,
                    self._style.corner_radius,
                )

            case _:
                path.addRect(r)

        # If no fill: only the border is the hit area
        if self._style.fill_color.alpha() == 0:
            stroker = QPainterPathStroker()
            stroker.setWidth(sw + self.HIT_PADDING * 2)
            return stroker.createStroke(path)

        return path

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self._rect
        st = self._style

        hide_ui = getattr(self.scene(), "_is_rendering_thumbnail", False)

        # Pen
        pen = QPen(st.stroke_color, st.stroke_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if st.dash:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([6, 4])
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)

        # Brush
        if st.fill_color.alpha() > 0:
            painter.setBrush(QBrush(st.fill_color))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # Live selection preview glow — draw along the actual shape contour
        is_preview = getattr(self, "_is_preview_highlight", False)
        if is_preview:
            painter.save()
            glow_pen = QPen(QColor(59, 123, 245, 160), max(3.5, st.stroke_width + 4.0))
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            glow_fill = QBrush(QColor(59, 123, 245, 30))
            match st.shape_type:
                case ShapeType.RECT:
                    painter.setBrush(glow_fill)
                    painter.drawRect(r)
                case ShapeType.ROUNDED_RECT:
                    painter.setBrush(glow_fill)
                    painter.drawRoundedRect(r, st.corner_radius, st.corner_radius)
                case ShapeType.ELLIPSE:
                    painter.setBrush(glow_fill)
                    painter.drawEllipse(r)
                case ShapeType.LINE:
                    p1, p2 = self._get_line_points()
                    painter.drawLine(p1, p2)
                case ShapeType.ARROW:
                    p1, p2 = self._get_line_points()
                    painter.drawLine(p1, p2)
                case ShapeType.TRIANGLE:
                    top = QPointF(r.center().x(), r.top())
                    bot_l = QPointF(r.left(), r.bottom())
                    bot_r = QPointF(r.right(), r.bottom())
                    painter.setBrush(glow_fill)
                    painter.drawPolygon(QPolygonF([top, bot_l, bot_r]))
            painter.restore()
            # Restore the normal pen/brush after preview
            painter.setPen(pen)
            if st.fill_color.alpha() > 0:
                painter.setBrush(QBrush(st.fill_color))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)

        # Draw shape
        match st.shape_type:
            case ShapeType.RECT:
                painter.drawRect(r)

            case ShapeType.ROUNDED_RECT:
                painter.drawRoundedRect(
                    r, st.corner_radius, st.corner_radius)

            case ShapeType.ELLIPSE:
                painter.drawEllipse(r)

            case ShapeType.LINE:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                p1, p2 = self._get_line_points()
                painter.drawLine(p1, p2)

            case ShapeType.ARROW:
                self._paint_arrow(painter, r, st)

            case ShapeType.TRIANGLE:
                self._paint_triangle(painter, r)

        # Selection frame — only when not managed by SelectionBoxItem overlay
        if self._is_selected and not self._is_selected_custom and not hide_ui:
            self._paint_selection(painter)

        painter.restore()

    def _paint_arrow(
        self, painter: QPainter, r: QRectF, st: ShapeStyle
    ) -> None:
        """Draw line with arrowhead."""
        p1, p2 = self._get_line_points()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(p1, p2)

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 1.0:
            return

        ux, uy = dx / length, dy / length
        head_len = max(12.0, st.stroke_width * 4)
        head_width = max(6.0, st.stroke_width * 2.5)

        lx = -uy * head_width
        ly = ux * head_width
        base = QPointF(
            p2.x() - ux * head_len,
            p2.y() - uy * head_len,
        )
        left = QPointF(base.x() + lx, base.y() + ly)
        right = QPointF(base.x() - lx, base.y() - ly)

        arrow_head = QPolygonF([p2, left, right])
        painter.setBrush(QBrush(st.stroke_color))
        painter.drawPolygon(arrow_head)

    def _paint_triangle(self, painter: QPainter, r: QRectF) -> None:
        """Draw isoceles triangle inside rect."""
        top = QPointF(r.center().x(), r.top())
        bot_l = QPointF(r.left(), r.bottom())
        bot_r = QPointF(r.right(), r.bottom())
        triangle = QPolygonF([top, bot_l, bot_r])
        painter.drawPolygon(triangle)

    def _paint_selection(self, painter: QPainter) -> None:
        """Selection frames are managed centrally by SelectionBoxItem."""
        pass

    # ------------------------------------------------------------------
    # Hover / mouse
    # ------------------------------------------------------------------

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        from app.app_state import AppState
        if AppState().active_tool_name in {"selection", "hand", "shape"}:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        event.accept()

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        from app.app_state import AppState
        
        # If this is a linear shape, is selected, and we click its path, act as a drag handle
        if getattr(self, "_is_selected_custom", False) and self._style.shape_type in (ShapeType.LINE, ShapeType.ARROW):
            if event.button() == Qt.MouseButton.LeftButton:
                self._native_dragging = False
                self._click_scene_pos = event.scenePos()
                self._click_box_pos = QPointF(self.pos())
                event.accept()
                return
                
        if AppState().active_tool_name not in {"selection", "hand", "shape"}:
            event.ignore()
            return
        event.ignore()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if getattr(self, "_click_scene_pos", None) is not None:
            delta = event.scenePos() - self._click_scene_pos
            if not getattr(self, "_native_dragging", False):
                if abs(delta.x()) > 3.0 or abs(delta.y()) > 3.0:
                    self._native_dragging = True
            
            if self._native_dragging:
                self.setPos(self._click_box_pos + delta)
                if self.scene() is not None and hasattr(self.scene(), "_update_selection_overlay"):
                    self.scene()._update_selection_overlay()
            event.accept()
            return
            
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if getattr(self, "_click_scene_pos", None) is not None:
            if getattr(self, "_native_dragging", False):
                # Drag ended -> push undo command
                if self.pos() != self._click_box_pos:
                    from commands.transform_items_command import TransformItemsCommand
                    from core.undo_stack import get_stack
                    before = {self: {"pos": QPointF(self._click_box_pos), "rect": self.get_rect(), "rotation": self.rotation(), "transform_origin": QPointF(self.transformOriginPoint())}}
                    after = {self: self.capture_state()}
                    cmd = TransformItemsCommand(before, after, self.scene(), "Verschieben")
                    get_stack().push(cmd)
            else:
                # Just a click -> could show options or toggle selection
                pass
                
            self._native_dragging = False
            self._click_scene_pos = None
            self._click_box_pos = None
            event.accept()
            return
            
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Bounding box resize support (legacy, for BoundingBoxHandleManager)
    # ------------------------------------------------------------------

    def apply_bounding_box_resize(self, new_br: QRectF) -> None:
        """Resize shape to match new scene bounding box."""
        self.prepareGeometryChange()
        local_rect = self.mapFromScene(new_br).boundingRect()
        self._rect = local_rect
        self._cached_br = None
        self.update()

    def get_path_state(self) -> tuple:
        """Snapshot rect + position for undo."""
        return (QRectF(self._rect), QPointF(self.pos()))

    def set_path_state(self, path_or_rect, pos: QPointF) -> None:
        """Restore rect + position from undo snapshot."""
        self.prepareGeometryChange()
        self._rect = QRectF(path_or_rect)
        self.setPos(pos)
        self._cached_br = None
        self.update()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        r = self._rect
        tp = self.transformOriginPoint()
        return {
            "type": "shape",
            "version": 1,
            "rect": (self.pos().x(), self.pos().y(), r.width(), r.height()),
            "rotation": self.rotation(),
            "transform_origin": (tp.x(), tp.y()),
            "page_index": self._page_index,
            "pos": (self.pos().x(), self.pos().y()),
            "style": self._style.to_dict(),
            "line_dir": getattr(self, "_line_dir", 0),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ShapeItem:
        rx, ry, rw, rh = d["rect"]
        style = ShapeStyle.from_dict(d["style"])
        item = cls(
            rect=QRectF(rx, ry, rw, rh),
            style=style,
            page_index=d.get("page_index", -1),
        )
        item.setRotation(d.get("rotation", 0.0))
        if "transform_origin" in d:
            tx, ty = d["transform_origin"]
            item.setTransformOriginPoint(QPointF(tx, ty))
        if "line_dir" in d:
            item.set_line_dir(d["line_dir"])
        return item
