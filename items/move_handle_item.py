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

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(
            -self.WIDTH / 2, -self.HEIGHT / 2, self.WIDTH, self.HEIGHT,
        )

        # 1. Soft drop shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 45)))
        painter.drawRoundedRect(rect.translated(0, 1.5), self.RADIUS, self.RADIUS)

        # 2. Pill background & subtle top highlight
        if self._dragging:
            fill = QColor("#1D4ED8")
            border_pen = QPen(QColor(255, 255, 255, 100), 1.0)
        elif self._hovered:
            fill = QColor("#2563EB")
            border_pen = QPen(QColor(255, 255, 255, 90), 1.0)
        else:
            fill = QColor("#3B7BF5")
            border_pen = QPen(QColor(255, 255, 255, 50), 1.0)

        painter.setBrush(QBrush(fill))
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # 3. Modern 6-dot grip icon
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(Qt.PenStyle.NoPen)
        dot_r = 1.3
        for x_off in (-6.0, 0.0, 6.0):
            for y_off in (-2.5, 2.5):
                painter.drawEllipse(QPointF(x_off, y_off), dot_r, dot_r)

        painter.restore()

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
                from commands.transform_items_command import TransformItemsCommand
                from core.undo_stack import get_stack

                before = {box: {"pos": QPointF(self._drag_start_box_pos), "rect": box.get_rect(), "rotation": box.rotation(), "transform_origin": QPointF(box.transformOriginPoint())}}
                after = {box: box.capture_state()}
                cmd = TransformItemsCommand(before, after, box.scene(), "Verschieben")
                get_stack().push(cmd)

        self._dragging = False
        self._click_only = False
        self._drag_start_scene_pos = None
        self._drag_start_box_pos = None
        event.accept()
