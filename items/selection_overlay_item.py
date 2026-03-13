"""Selection overlay – draws a combined bounding box for multi-selection."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QStyleOptionGraphicsItem,
    QWidget,
)


class SelectionOverlayItem(QGraphicsItem):
    """Draws the combined bounding box when ≥2 items are selected.

    Managed by PageScene – one overlay per scene.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._bounding_rect: QRectF = QRectF()
        self._managed_items: list[QGraphicsItem] = []
        self._scene: QGraphicsScene | None = None
        self.setZValue(499)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def update_from_items(
        self, items: set[QGraphicsItem], scene: QGraphicsScene
    ) -> None:
        """Recompute overlay from the current set of selected items."""
        self._managed_items = list(items)
        self._scene = scene
        
        if len(items) < 2:
            self.setVisible(False)
            return

        combined = QRectF()
        for item in items:
            item_rect = item.mapToScene(
                item.boundingRect()
            ).boundingRect()
            combined = combined.united(item_rect)

        self.prepareGeometryChange()
        self._bounding_rect = combined
        self.setPos(QPointF(0, 0))
        self.setVisible(True)
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounding_rect.adjusted(-4, -4, 4, 4)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        if self._bounding_rect.isNull():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        sel_pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
        sel_pen.setDashPattern([6, 4])
        painter.setPen(sel_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(1.0)
        painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))

    def apply_bounding_box_resize(self, new_br: QRectF) -> None:
        """Scale all managed items so the combined bounding box matches *new_br*."""
        old_br = self.mapToScene(self.boundingRect()).boundingRect()
        if old_br.width() < 0.01 or old_br.height() < 0.01:
            return

        sx = new_br.width() / old_br.width()
        sy = new_br.height() / old_br.height()

        from PySide6.QtGui import QTransform
        transform = QTransform()
        transform.translate(new_br.left(), new_br.top())
        transform.scale(sx, sy)
        transform.translate(-old_br.left(), -old_br.top())

        for item in self._managed_items:
            # Map item's bounding rect or pos to compute new position/scale
            from items.stroke_item import StrokeItem
            from items.highlight_item import HighlightItem
            from items.text_box_item import TextBoxItem

            if isinstance(item, (StrokeItem, HighlightItem)):
                item_old_br = item.mapToScene(item.boundingRect()).boundingRect()
                top_left = transform.map(item_old_br.topLeft())
                bottom_right = transform.map(item_old_br.bottomRight())
                item_new_br = QRectF(top_left, bottom_right).normalized()
                item.apply_bounding_box_resize(item_new_br)
            elif isinstance(item, TextBoxItem):
                item_old_br = item.get_rect()
                top_left = transform.map(item_old_br.topLeft())
                bottom_right = transform.map(item_old_br.bottomRight())
                item_new_br = QRectF(top_left, bottom_right).normalized()
                item.set_rect(item_new_br)

        self.prepareGeometryChange()
        
        # We need to recompute self._bounding_rect because items changed
        combined = QRectF()
        for item in self._managed_items:
            item_rect = item.mapToScene(item.boundingRect()).boundingRect()
            combined = combined.united(item_rect)
        self._bounding_rect = combined
        self.update()

    def get_path_state(self) -> tuple:
        """Snapshot the state of all managed items for undo."""
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        
        state = {}
        for item in self._managed_items:
            if isinstance(item, (StrokeItem, HighlightItem)):
                state[item] = item.get_path_state()
            elif isinstance(item, TextBoxItem):
                state[item] = item.get_rect()
        return (self._bounding_rect, state)

    def set_path_state(self, bounding_rect: QRectF, state: dict) -> None:
        """Restore all items from undo snapshot."""
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem

        for item, item_state in state.items():
            if isinstance(item, (StrokeItem, HighlightItem)):
                item.set_path_state(item_state[0], item_state[1])
            elif isinstance(item, TextBoxItem):
                item.set_rect(item_state)
        
        self.prepareGeometryChange()
        self._bounding_rect = bounding_rect
        self.update()
