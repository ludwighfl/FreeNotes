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


class ShapeItem(QGraphicsItem):
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

        # --- Handles (created as children) ---
        from items.shape_handles import (
            ShapeResizeHandle, ShapeMoveHandle,
            ShapeRotateHandle, ShapeOptionsHandle,
        )

        self._handles: dict[HandlePosition, ShapeResizeHandle] = {}
        for pos in HandlePosition:
            handle = ShapeResizeHandle(pos, parent=self)
            self._handles[pos] = handle

        self._move_handle = ShapeMoveHandle(parent=self)
        self._rotate_handle = ShapeRotateHandle(parent=self)
        self._options_handle = ShapeOptionsHandle(parent=self)

        self._update_handle_positions()
        self._set_handles_visible(False)

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
        """Show/hide handles + selection frame (called by scene)."""
        self.prepareGeometryChange()
        self._is_selected = selected
        self._is_selected_custom = selected
        self._cached_br = None
        self._set_handles_visible(selected)
        if selected:
            self._update_handle_positions()
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
        self.setPos(rect.topLeft())
        self._rect = QRectF(0, 0, rect.width(), rect.height())
        self._cached_br = None
        self._update_handle_positions()
        self.update()

    # ------------------------------------------------------------------
    # Handle management
    # ------------------------------------------------------------------

    def _update_handle_positions(self) -> None:
        r = self._rect
        
        is_linear = self._style.shape_type in (ShapeType.LINE, ShapeType.ARROW)
        
        if is_linear:
            p1, p2 = self._get_line_points()
            # For linear, use TL and BR as the generic endpoints arbitrarily
            positions = {
                HandlePosition.TOP_LEFT: p1,
                HandlePosition.BOT_RIGHT: p2,
            }
        else:
            # Offset handles outward to sit on the dashed selection border
            pad = self._style.stroke_width / 2.0 + 3.0
            positions = {
                HandlePosition.TOP_LEFT: QPointF(r.left() - pad, r.top() - pad),
                HandlePosition.TOP_RIGHT: QPointF(r.right() + pad, r.top() - pad),
                HandlePosition.MID_LEFT: QPointF(r.left() - pad, r.center().y()),
                HandlePosition.MID_RIGHT: QPointF(r.right() + pad, r.center().y()),
                HandlePosition.BOT_LEFT: QPointF(r.left() - pad, r.bottom() + pad),
                HandlePosition.BOT_RIGHT: QPointF(r.right() + pad, r.bottom() + pad),
            }
            
        for pos, point in positions.items():
            if pos in self._handles:
                self._handles[pos].setPos(point)
                self._handles[pos].set_is_endpoint(is_linear)
                
        if hasattr(self, '_move_handle'):
            if not is_linear:
                pad = self._style.stroke_width / 2.0 + 3.0
                padded = self._rect.adjusted(-pad, -pad, pad, pad)
                self._move_handle.update_position(padded)
            else:
                self._move_handle.update_position(self._rect)
        if hasattr(self, '_rotate_handle'):
            if not is_linear:
                pad = self._style.stroke_width / 2.0 + 3.0
                padded = self._rect.adjusted(-pad, -pad, pad, pad)
                self._rotate_handle.update_position(padded)
            else:
                self._rotate_handle.update_position(self._rect)
        if hasattr(self, '_options_handle') and self._options_handle.isVisible():
            if not is_linear:
                pad = self._style.stroke_width / 2.0 + 3.0
                padded = self._rect.adjusted(-pad, -pad, pad, pad)
                self._options_handle.update_position(padded)
            else:
                self._options_handle.update_position(self._rect)

    def _set_handles_visible(self, visible: bool) -> None:
        is_linear = self._style.shape_type in (ShapeType.LINE, ShapeType.ARROW)
        
        for pos, handle in self._handles.items():
            if is_linear and pos not in (HandlePosition.TOP_LEFT, HandlePosition.BOT_RIGHT):
                handle.setVisible(False)
            else:
                handle.setVisible(visible)
                
        # Move/Rotate are hidden entirely for linear items for cleaner UI
        if hasattr(self, '_move_handle'):
            self._move_handle.setVisible(visible and not is_linear)
        if hasattr(self, '_rotate_handle'):
            self._rotate_handle.setVisible(visible and not is_linear)
        if hasattr(self, '_options_handle') and not visible:
            self._options_handle.hide()

    # ------------------------------------------------------------------
    # Resize via handles (duck-typed interface for ResizeHandleItem)
    # ------------------------------------------------------------------

    def apply_handle_drag(
        self,
        handle_pos: HandlePosition,
        start_rect: QRectF,
        delta: QPointF,
        start_line_dir: int = 0,
    ) -> None:
        """Apply a handle drag to resize/reposition the shape.

        start_rect is in scene coordinates (from get_rect()).
        """
        self.prepareGeometryChange()
        self._cached_br = None
        new_rect = QRectF(start_rect)

        match handle_pos:
            case HandlePosition.TOP_LEFT:
                new_rect.setTopLeft(start_rect.topLeft() + delta)
            case HandlePosition.TOP_RIGHT:
                new_rect.setTopRight(start_rect.topRight() + delta)
            case HandlePosition.MID_LEFT:
                new_rect.setLeft(start_rect.left() + delta.x())
            case HandlePosition.MID_RIGHT:
                new_rect.setRight(start_rect.right() + delta.x())
            case HandlePosition.BOT_LEFT:
                new_rect.setBottomLeft(start_rect.bottomLeft() + delta)
            case HandlePosition.BOT_RIGHT:
                new_rect.setBottomRight(start_rect.bottomRight() + delta)

        # Enforce minimum size (except lines/arrows which can be 1D)
        if self._style.shape_type not in (ShapeType.LINE, ShapeType.ARROW):
            new_rect = new_rect.normalized()
            if new_rect.width() < self.MIN_SIZE:
                new_rect.setWidth(self.MIN_SIZE)
            if new_rect.height() < self.MIN_SIZE:
                new_rect.setHeight(self.MIN_SIZE)
                
            self.set_rect(new_rect)
        else:
            # Linear constraint update based on endpoints
            # Find ORIGINAL scene endpoints from the start of the drag
            if start_line_dir == 0:
                p1, p2 = start_rect.topLeft(), start_rect.bottomRight()
            elif start_line_dir == 1:
                p1, p2 = start_rect.bottomRight(), start_rect.topLeft()
            elif start_line_dir == 2:
                p1, p2 = start_rect.topRight(), start_rect.bottomLeft()
            else:
                p1, p2 = start_rect.bottomLeft(), start_rect.topRight()
                
            # Find which points moved
            if handle_pos == HandlePosition.TOP_LEFT:
                p1 = p1 + delta
            elif handle_pos == HandlePosition.BOT_RIGHT:
                p2 = p2 + delta
                
            # Find new extents
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

    # ------------------------------------------------------------------
    # Options popup
    # ------------------------------------------------------------------

    def show_options_popup(self) -> None:
        """Toggle the inline options bar (Copy / Cut / Delete)."""
        if self._options_handle.isVisible():
            self._options_handle.hide()
        else:
            self._options_handle.update_position(self._rect)
            self._options_handle.show()

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

        # Selection frame (dashed blue border)
        if (self._is_selected or self._is_selected_custom) and not hide_ui:
            self._paint_selection(painter)

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
        """Blue dashed selection frame or line path."""
        painter.save()
        
        is_linear = self._style.shape_type in (ShapeType.LINE, ShapeType.ARROW)
        
        if is_linear:
            pen = QPen(QColor("#3B7BF5"), self._style.stroke_width + 4.0, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setOpacity(0.3)
            p1, p2 = self._get_line_points()
            painter.drawLine(p1, p2)
        else:
            pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
            pen.setDashPattern([6, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setOpacity(1.0)
            pad = self._style.stroke_width / 2.0 + 3.0
            painter.drawRect(self._rect.adjusted(-pad, -pad, pad, pad))
            
        painter.restore()

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
            event.accept()
            return
            
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if getattr(self, "_click_scene_pos", None) is not None:
            if getattr(self, "_native_dragging", False):
                # Drag ended -> push undo command
                if self.pos() != self._click_box_pos:
                    from commands.move_shape_command import MoveShapeCommand
                    from core.undo_stack import get_stack
                    cmd = MoveShapeCommand(
                        self, self._click_box_pos, self.pos(), self.scene(),
                    )
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
