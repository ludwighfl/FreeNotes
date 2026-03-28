"""Move handle – pill-shaped drag handle above TextBoxItem."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
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


class MoveHandleItem(QGraphicsItem):
    """Pill-shaped handle at top-center with III grip icon.

    Drag moves the parent TextBoxItem.
    Click (without drag) calls show_options_popup() on parent.
    """

    WIDTH: float = 36.0
    HEIGHT: float = 20.0
    RADIUS: float = 10.0
    DRAG_THRESHOLD: float = 3.0

    def __init__(self, parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self._dragging: bool = False
        self._hovered: bool = False
        self._click_only: bool = False
        self._drag_start_scene_pos: QPointF | None = None
        self._drag_start_box_pos: QPointF | None = None

        self.setZValue(25)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    # ==================================================================
    # Geometry
    # ==================================================================

    def boundingRect(self) -> QRectF:
        return QRectF(
            -self.WIDTH / 2, -self.HEIGHT / 2, self.WIDTH, self.HEIGHT,
        ).adjusted(-4, -4, 4, 4)

    def update_position(self, box_rect: QRectF) -> None:
        """Reposition centered on the top edge of *box_rect* (local coords)."""
        self.setPos(QPointF(
            box_rect.left() + box_rect.width() / 2.0,
            box_rect.top(),
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

        # Pill background
        if self._hovered or self._dragging:
            fill = QColor("#5a9bf8")
        else:
            fill = QColor("#3B7BF5")

        painter.setBrush(QBrush(fill))
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(
            -self.WIDTH / 2, -self.HEIGHT / 2, self.WIDTH, self.HEIGHT,
        )
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # III grip icon (three horizontal lines)
        painter.setPen(QPen(
            QColor("#ffffff"), 1.5,
            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
        ))
        line_w = self.WIDTH * 0.45
        for y_off in (-3.5, 0.0, 3.5):
            painter.drawLine(
                QPointF(-line_w / 2, y_off),
                QPointF(line_w / 2, y_off),
            )

    # ==================================================================
    # Hover
    # ==================================================================

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.update()
        event.accept()

    # ==================================================================
    # Drag-to-move
    # ==================================================================

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            # Right-click → options popup immediately
            box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
            if hasattr(box, 'show_options_popup'):
                box.show_options_popup()
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = False
        self._click_only = True
        self._drag_start_scene_pos = event.scenePos()
        box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        self._drag_start_box_pos = QPointF(box.pos())
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag_start_scene_pos is None:
            return
        delta = event.scenePos() - self._drag_start_scene_pos

        # Drag threshold
        if not self._dragging:
            if abs(delta.x()) > self.DRAG_THRESHOLD or abs(delta.y()) > self.DRAG_THRESHOLD:
                self._dragging = True
                self._click_only = False

        if self._dragging and self._drag_start_box_pos is not None:
            box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
            box.setPos(self._drag_start_box_pos + delta)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        if self._click_only and not self._dragging:
            # Click without drag → options popup
            box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
            if hasattr(box, "show_options_popup"):
                box.show_options_popup()

        elif self._dragging and self._drag_start_box_pos is not None:
            # Drag ended → undo command
            box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
            if box.pos() != self._drag_start_box_pos:
                from commands.move_textbox_command import MoveTextBoxCommand
                from core.undo_stack import get_stack

                cmd = MoveTextBoxCommand(
                    box, self._drag_start_box_pos, box.pos(), box.scene(),
                )
                get_stack().push(cmd)

        self._dragging = False
        self._click_only = False
        self._drag_start_scene_pos = None
        self._drag_start_box_pos = None
        event.accept()
