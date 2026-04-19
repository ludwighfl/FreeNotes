"""Rotation handle – circular handle below TextBoxItem for drag-to-rotate."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem


class RotateHandleItem(QGraphicsItem):
    """Circular handle at bottom-center with ↻ icon.

    Drag rotates the parent TextBoxItem around its center.
    """

    RADIUS: float = 10.0
    OFFSET_Y: float = 10.0  # gap below box bottom to handle center

    def __init__(self, parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self._dragging: bool = False
        self._hovered: bool = False
        self._start_angle: float = 0.0
        self._start_rotation: float = 0.0
        self._rotation_center: QPointF = QPointF()

        self.setZValue(25)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    # ==================================================================
    # Geometry
    # ==================================================================

    def boundingRect(self) -> QRectF:
        r = self.RADIUS
        # Must include connecting line which extends up to -(r + OFFSET_Y)
        top = -(r + self.OFFSET_Y + 2)
        bottom = r + 10  # 8px padding + 2
        left = -(r + 10) # 8px padding + 2
        right = r + 10   # 8px padding + 2
        return QRectF(left, top, right - left, bottom - top).adjusted(-4, -4, 4, 4)

    def shape(self) -> QPainterPath:
        """Expand hit area of the circle for easier clicking."""
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        r = self.RADIUS + 8.0  # 8px extra padding
        path.addEllipse(-r, -r, r * 2, r * 2)
        return path

    def update_position(self, box_rect: QRectF) -> None:
        """Reposition below bottom-center of *box_rect* (local coords)."""
        self.setPos(QPointF(
            box_rect.left() + box_rect.width() / 2.0,
            box_rect.bottom() + self.RADIUS + self.OFFSET_Y,
        ))

    # ==================================================================
    # Painting
    # ==================================================================

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.RADIUS

        # Connecting line from circle top to box bottom edge
        painter.setPen(QPen(QColor("#3B7BF5"), 1.5))
        # This item is positioned at (center_x, box_bottom + RADIUS + OFFSET_Y)
        # Line from circle top (-RADIUS) up to box bottom edge
        line_top = -(self.RADIUS + self.OFFSET_Y)  # relative to our center
        painter.drawLine(
            QPointF(0, -r),
            QPointF(0, line_top),
        )

        # Circle
        if self._dragging:
            fill = QColor("#3B7BF5")
            icon_color = QColor("#ffffff")
        elif self._hovered:
            fill = QColor("#5a9bf8")
            icon_color = QColor("#ffffff")
        else:
            fill = QColor("#ffffff")
            icon_color = QColor("#3B7BF5")

        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(QColor("#3B7BF5"), 1.5))
        painter.drawEllipse(QPointF(0, 0), r, r)

        # ↻ icon
        font = QFont()
        font.setPixelSize(max(int(r * 1.1), 1))
        painter.setFont(font)
        painter.setPen(QPen(icon_color))
        painter.drawText(
            QRectF(-r, -r, r * 2, r * 2),
            Qt.AlignmentFlag.AlignCenter,
            "↻",
        )

    # ==================================================================
    # Hover
    # ==================================================================

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        event.accept()

    # ==================================================================
    # Drag-to-rotate
    # ==================================================================

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        
        # Safely update transformOriginPoint without jumping
        new_origin = QPointF(box._rect.width() / 2.0, box._rect.height() / 2.0)
        if new_origin != box.transformOriginPoint():
            p1 = box.mapToScene(QPointF(0, 0))
            box.setTransformOriginPoint(new_origin)
            p2 = box.mapToScene(QPointF(0, 0))
            box.setPos(box.pos() + (p1 - p2))
            
        self._rotation_center = box.mapToScene(new_origin)
        self._start_angle = self._angle_to(event.scenePos())
        self._start_rotation = box.rotation()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        delta = self._angle_to(event.scenePos()) - self._start_angle
        new_rotation = self._start_rotation + delta
        
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            new_rotation = round(new_rotation / 45.0) * 45.0
            
        box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        box.setRotation(new_rotation)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        final = box.rotation()
        if abs(final - self._start_rotation) > 0.01:
            from commands.rotate_textbox_command import RotateTextBoxCommand
            from core.undo_stack import get_stack

            cmd = RotateTextBoxCommand(
                box, self._start_rotation, final, box.scene(),
            )
            get_stack().push(cmd)
        event.accept()

    # ==================================================================
    # Helpers
    # ==================================================================

    def _angle_to(self, scene_pos: QPointF) -> float:
        """Angle in degrees from rotation center to *scene_pos*."""
        dx = scene_pos.x() - self._rotation_center.x()
        dy = scene_pos.y() - self._rotation_center.y()
        return math.degrees(math.atan2(dy, dx))
