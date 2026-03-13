"""Resize handle items – circular handles for TextBoxItem corners and edges."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPen, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
)

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem


class HandlePosition(Enum):
    """Positions for resize handles (6 total, no top/bottom center)."""
    TOP_LEFT = "tl"
    TOP_RIGHT = "tr"
    MID_LEFT = "ml"
    MID_RIGHT = "mr"
    BOT_LEFT = "bl"
    BOT_RIGHT = "br"


# Positions that are corners (small hollow circles)
_CORNER_POSITIONS = {
    HandlePosition.TOP_LEFT,
    HandlePosition.TOP_RIGHT,
    HandlePosition.BOT_LEFT,
    HandlePosition.BOT_RIGHT,
}

# Resize cursor per position
_CURSOR_MAP = {
    HandlePosition.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
    HandlePosition.BOT_RIGHT: Qt.CursorShape.SizeFDiagCursor,
    HandlePosition.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
    HandlePosition.BOT_LEFT: Qt.CursorShape.SizeBDiagCursor,
    HandlePosition.MID_LEFT: Qt.CursorShape.SizeHorCursor,
    HandlePosition.MID_RIGHT: Qt.CursorShape.SizeHorCursor,
}


class ResizeHandleItem(QGraphicsEllipseItem):
    """Circular resize handle – small hollow white circle with blue border."""

    RADIUS: float = 5.0

    def __init__(self, position: HandlePosition, parent: QGraphicsItem) -> None:
        self._position = position
        
        # Endpoint flag for lines/arrows
        self._is_endpoint: bool = False
        
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent)

        self._dragging: bool = False
        self._drag_start_pos: QPointF | None = None
        self._drag_start_rect: QRectF | None = None
        self._hovered: bool = False

        # Appearance – hollow white circle with blue border
        self._apply_default_style()

        # Flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setZValue(20)
        self.setCursor(_CURSOR_MAP.get(position, Qt.CursorShape.ArrowCursor))

    def set_is_endpoint(self, is_endpoint: bool) -> None:
        """Toggle styling + cursor for line endpoints vs box corners."""
        if self._is_endpoint == is_endpoint:
            return
            
        self._is_endpoint = is_endpoint
        
        if is_endpoint:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Slightly larger rendering padding
            r = self.RADIUS + 1.5
            self.setRect(-r, -r, r * 2, r * 2)
        else:
            self.setCursor(_CURSOR_MAP.get(self._position, Qt.CursorShape.ArrowCursor))
            r = self.RADIUS
            self.setRect(-r, -r, r * 2, r * 2)
            
        self._apply_default_style()
        self.update()

    # ==================================================================
    # Style helpers
    # ==================================================================

    def _apply_default_style(self) -> None:
        if self._is_endpoint:
            self.setBrush(QBrush(QColor("#ffffff")))
            self.setPen(QPen(QColor("#3B7BF5"), 2.0))
        else:
            self.setBrush(QBrush(QColor("#ffffff")))
            self.setPen(QPen(QColor("#3B7BF5"), 1.5))

    # ==================================================================
    # Hover
    # ==================================================================

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.setBrush(QBrush(QColor("#ddeeff")))
        self.update()
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_default_style()
        self.update()
        event.accept()

    # ==================================================================
    # Drag-to-resize
    # ==================================================================

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        self._drag_start_pos = event.scenePos()
        parent: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        self._drag_start_rect = parent.get_rect()
        if hasattr(parent, 'get_line_dir'):
            self._drag_start_line_dir = parent.get_line_dir()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging or self._drag_start_pos is None:
            return
        scene_delta = event.scenePos() - self._drag_start_pos
        # Transform delta into the parent's (possibly rotated) local frame
        parent: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        rotation = parent.rotation()
        if abs(rotation) > 0.01:
            import math
            rad = math.radians(-rotation)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            local_dx = scene_delta.x() * cos_a - scene_delta.y() * sin_a
            local_dy = scene_delta.x() * sin_a + scene_delta.y() * cos_a
            delta = QPointF(local_dx, local_dy)
        else:
            delta = scene_delta
            
        kwargs = {}
        if hasattr(self, "_drag_start_line_dir"):
            kwargs["start_line_dir"] = self._drag_start_line_dir
            
        parent.apply_handle_drag(self._position, self._drag_start_rect, delta, **kwargs)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        parent: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        final_rect = parent.get_rect()
        if self._drag_start_rect is not None and final_rect != self._drag_start_rect:
            from commands.resize_textbox_command import ResizeTextBoxCommand
            from core.undo_stack import get_stack

            cmd = ResizeTextBoxCommand(
                parent, self._drag_start_rect, final_rect, parent.scene(),
            )
            get_stack().push(cmd)

        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_rect = None
        event.accept()

    def boundingRect(self) -> QRectF:
        """Expand bounds to ensure the 1.5px pen and antialiasing don't leave ghosts."""
        return super().boundingRect().adjusted(-2, -2, 2, 2)

    def shape(self) -> QPainterPath:
        """Expand hit area for easier clicking."""
        path = QPainterPath()
        r = self.RADIUS + 8.0  # 8px extra padding
        path.addEllipse(-r, -r, r * 2, r * 2)
        return path

    def paint(self, painter, option, widget=None) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        super().paint(painter, option, widget)

    # ==================================================================
    # Property
    # ==================================================================

    @property
    def position(self) -> HandlePosition:
        return self._position
