"""Eraser cursor item – visual circle that follows the mouse in eraser mode."""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget


class EraserCursorItem(QGraphicsItem):
    """Visual eraser circle rendered in the QGraphicsScene.

    Follows the mouse via update_position(). Does NOT intercept any
    mouse events – all clicks pass through to items beneath it.
    ZValue=50 ensures it renders above all annotation items.
    """

    DEFAULT_RADIUS: float = 15.0
    MIN_RADIUS: float = 5.0
    MAX_RADIUS: float = 60.0

    def __init__(
        self,
        radius: float = DEFAULT_RADIUS,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._radius: float = radius

        self.setZValue(50)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self) -> QRectF:
        r = self._radius + 2.0
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Outer white ring
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), self._radius, self._radius)

        # Inner dark ring for contrast
        inner_pen = QPen(QColor(0, 0, 0, 128), 0.8)
        painter.setPen(inner_pen)
        painter.drawEllipse(QPointF(0, 0), self._radius - 1.0, self._radius - 1.0)

    @property
    def radius(self) -> float:
        return self._radius

    @radius.setter
    def radius(self, value: float) -> None:
        value = max(self.MIN_RADIUS, min(self.MAX_RADIUS, value))
        self.prepareGeometryChange()
        self._radius = value
        self.update()

    def update_position(self, scene_pos: QPointF) -> None:
        """Move the cursor circle to the given scene position."""
        self.setPos(scene_pos)
