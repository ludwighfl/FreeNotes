"""Options handle – inline Copy / Cut / Delete bar for TextBoxItem."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem


# ---------------------------------------------------------------------------
# Icon drawing helpers (Lucide-style, drawn via QPainter)
# ---------------------------------------------------------------------------

_ICON_COLOR = QColor("#3B7BF5")
_ICON_DELETE_COLOR = QColor("#ef4444")
_ICON_PEN_WIDTH = 1.6


def _draw_copy_icon(painter: QPainter, cx: float, cy: float) -> None:
    """Lucide 'copy' icon centred at (cx, cy), 14×14."""
    s = 7.0  # half-size
    pen = QPen(_ICON_COLOR, _ICON_PEN_WIDTH)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Front rect
    painter.drawRoundedRect(QRectF(cx - s + 3, cy - s + 3, 10, 10), 1.5, 1.5)
    # Back path (L-shape)
    path = QPainterPath()
    path.moveTo(cx - s + 7, cy - s)
    path.lineTo(cx - s + 2, cy - s)
    path.quadTo(cx - s, cy - s, cx - s, cy - s + 2)
    path.lineTo(cx - s, cy - s + 7)
    painter.drawPath(path)


def _draw_scissors_icon(painter: QPainter, cx: float, cy: float) -> None:
    """Lucide 'scissors' icon centred at (cx, cy), 14×14."""
    s = 6.5
    pen = QPen(_ICON_COLOR, _ICON_PEN_WIDTH)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Two circles
    r = 2.2
    painter.drawEllipse(QPointF(cx - s + 2.5, cy - s + 2.5), r, r)
    painter.drawEllipse(QPointF(cx - s + 2.5, cy + s - 2.5), r, r)
    # Cross lines
    painter.drawLine(QPointF(cx + s - 1, cy - s + 1),
                     QPointF(cx - s + 4.2, cy + s - 4.2))
    painter.drawLine(QPointF(cx - s + 4.2, cy - s + 4.2),
                     QPointF(cx + s - 1, cy + s - 1))


def _draw_trash_icon(painter: QPainter, cx: float, cy: float) -> None:
    """Lucide 'trash-2' icon centred at (cx, cy), 14×14."""
    s = 6.0
    pen = QPen(_ICON_DELETE_COLOR, _ICON_PEN_WIDTH)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Top line
    painter.drawLine(QPointF(cx - s, cy - s + 2),
                     QPointF(cx + s, cy - s + 2))
    # Lid handle
    painter.drawLine(QPointF(cx - 2, cy - s),
                     QPointF(cx + 2, cy - s))
    # Body
    path = QPainterPath()
    path.moveTo(cx - s + 1.5, cy - s + 2)
    path.lineTo(cx - s + 2.0, cy + s)
    path.lineTo(cx + s - 2.0, cy + s)
    path.lineTo(cx + s - 1.5, cy - s + 2)
    painter.drawPath(path)
    # Inner lines
    painter.drawLine(QPointF(cx - 1.5, cy - s + 5),
                     QPointF(cx - 1.5, cy + s - 2))
    painter.drawLine(QPointF(cx + 1.5, cy - s + 5),
                     QPointF(cx + 1.5, cy + s - 2))


class OptionsHandleItem(QGraphicsItem):
    """Inline options bar: Copy | Cut | Delete.

    Rendered as a white rounded rect with blue border, matching the
    handle design.  Appears on right-click of the move handle.
    """

    BTN_SIZE: float = 26.0
    BAR_HEIGHT: float = 30.0
    SEP_GAP: float = 4.0
    CORNER_RADIUS: float = 6.0
    OFFSET_Y: float = 4.0  # gap above move handle

    def __init__(self, parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self._hovered_index: int = -1  # 0=copy, 1=cut, 2=delete

        self.setZValue(30)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        self.hide()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _bar_width(self) -> float:
        return self.BTN_SIZE * 3 + self.SEP_GAP + 8  # 3 buttons + sep + padding

    def boundingRect(self) -> QRectF:
        w = self._bar_width()
        h = self.BAR_HEIGHT
        # Bar is drawn from y=0 upward (negative y) since positioned above
        return QRectF(-w / 2 - 2, -h - 2, w + 4, h + 4).adjusted(-4, -4, 4, 4)

    def _btn_rect(self, index: int) -> QRectF:
        """Return rect for button at index (0=copy, 1=cut, 2=delete)."""
        w = self._bar_width()
        h = self.BAR_HEIGHT
        x0 = -w / 2 + 4
        if index < 2:
            bx = x0 + index * self.BTN_SIZE
        else:
            bx = x0 + 2 * self.BTN_SIZE + self.SEP_GAP
        return QRectF(bx, -h + (h - self.BTN_SIZE) / 2,
                      self.BTN_SIZE, self.BTN_SIZE)

    def update_position(self, box_rect: QRectF) -> None:
        """Reposition directly above the move handle at top-center."""
        from items.move_handle_item import MoveHandleItem
        cx = box_rect.left() + box_rect.width() / 2.0
        # Move handle sits at box top, pill extends upward by half its height
        move_top = box_rect.top() - MoveHandleItem.HEIGHT / 2.0
        self.setPos(QPointF(cx, move_top - self.OFFSET_Y))

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self._bar_width()
        h = self.BAR_HEIGHT

        bar_rect = QRectF(-w / 2, -h, w, h)

        # White fill + blue border
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#3B7BF5"), 1.5))
        painter.drawRoundedRect(bar_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # Separator line before delete
        sep_x = -w / 2 + 4 + 2 * self.BTN_SIZE + self.SEP_GAP / 2
        painter.setPen(QPen(QColor("#d0d0d0"), 1.0))
        painter.drawLine(QPointF(sep_x, -h + 5), QPointF(sep_x, -5))

        # Hover highlight
        if self._hovered_index >= 0:
            hr = self._btn_rect(self._hovered_index)
            if self._hovered_index == 2:
                painter.setBrush(QBrush(QColor(239, 68, 68, 30)))
            else:
                painter.setBrush(QBrush(QColor(59, 123, 245, 30)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(hr, 4, 4)

        # Icons
        for i, draw_fn in enumerate([_draw_copy_icon, _draw_scissors_icon, _draw_trash_icon]):
            r = self._btn_rect(i)
            draw_fn(painter, r.center().x(), r.center().y())

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------

    def hoverMoveEvent(self, event) -> None:
        pos = event.pos()
        old = self._hovered_index
        self._hovered_index = -1
        for i in range(3):
            if self._btn_rect(i).contains(pos):
                self._hovered_index = i
                break
        if self._hovered_index != old:
            if self._hovered_index >= 0:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self._hovered_index = -1
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        event.accept()

    # ------------------------------------------------------------------
    # Click
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        pos = event.pos()
        for i in range(3):
            if self._btn_rect(i).contains(pos):
                self._execute_action(i)
                event.accept()
                return
        event.accept()

    def _execute_action(self, index: int) -> None:
        box: TextBoxItem = self.parentItem()  # type: ignore[assignment]
        if index == 0:
            self._do_copy(box)
        elif index == 1:
            self._do_cut(box)
        elif index == 2:
            self._do_delete(box)
        self.hide()

    def _do_copy(self, box: TextBoxItem) -> None:
        from app.app_state import AppState
        AppState().clipboard_box = box.clone()

    def _do_cut(self, box: TextBoxItem) -> None:
        from app.app_state import AppState
        from commands.cut_textbox_command import CutTextBoxCommand
        from core.undo_stack import get_stack

        AppState().clipboard_box = box.clone()
        scene = box.scene()
        if scene is None:
            return
        cmd = CutTextBoxCommand(box, scene)
        get_stack().push(cmd)

    def _do_delete(self, box: TextBoxItem) -> None:
        from commands.remove_textbox_command import RemoveTextBoxCommand
        from core.undo_stack import get_stack

        scene = box.scene()
        if scene is None:
            return
        # Pre-remove (RemoveTextBoxCommand skips first redo)
        box.stop_editing()
        if box.scene() is scene:
            scene.removeItem(box)
        scene.remove_item_from_registry(box)
        cmd = RemoveTextBoxCommand([box], scene)
        get_stack().push(cmd)
