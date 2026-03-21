"""Search highlight overlay – transparent rectangle over found text."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem


class SearchHighlightItem(QGraphicsRectItem):
    """Yellow/orange transparent rectangle marking a search hit on the PDF."""

    def __init__(
        self, rect: QRectF, is_current: bool = False
    ) -> None:
        super().__init__(rect)
        self.setZValue(8)  # Above PDF (0), below strokes (10)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.set_current(is_current)

    def set_current(self, is_current: bool) -> None:
        """Toggle between active (orange) and normal (yellow) highlight."""
        if is_current:
            self.setBrush(QBrush(QColor(255, 140, 0, 150)))
            self.setPen(QPen(QColor(255, 100, 0), 1.5))
        else:
            self.setBrush(QBrush(QColor(255, 235, 59, 80)))
            self.setPen(QPen(QColor(200, 180, 0), 0.5))
        self.update()
