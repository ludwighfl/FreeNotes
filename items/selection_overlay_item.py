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


from items.rotate_handle_item import RotateHandleItem
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

class SelectionRotateHandle(RotateHandleItem):
    """Rotate handle for multiple items via SelectionOverlayItem."""
    
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        overlay: SelectionOverlayItem = self.parentItem()  # type: ignore[assignment]
        self._rotation_center = overlay.mapToScene(overlay._bounding_rect.center())
        self._start_angle = self._angle_to(event.scenePos())
        self._last_angle = 0.0
        
        self._drag_old_state = overlay.get_path_state()
        
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        delta = self._angle_to(event.scenePos()) - self._start_angle
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = round(delta / 45.0) * 45.0
            
        step_delta = delta - self._last_angle
        self._last_angle = delta
        
        overlay: SelectionOverlayItem = self.parentItem()  # type: ignore[assignment]
        overlay.apply_group_rotation(step_delta)
        
        # SelectionOverlayItem resets bounds, we must reposition
        self.update_position(overlay._bounding_rect)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        
        overlay: SelectionOverlayItem = self.parentItem()  # type: ignore[assignment]
        new_state = overlay.get_path_state()
        
        if abs(self._last_angle) > 0.01:
            from commands.rotate_items_command import RotateItemsCommand
            from core.undo_stack import get_stack
            cmd = RotateItemsCommand(
                self._drag_old_state[1], new_state[1],
                self._drag_old_state[0], new_state[0],
                overlay.scene()
            )
            get_stack().push(cmd)
        event.accept()


class SelectionOverlayItem(QGraphicsItem):
    """Draws the combined bounding box when ≥2 items are selected.

    Managed by PageScene – one overlay per scene.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._bounding_rect: QRectF = QRectF()
        self._managed_items: list[QGraphicsItem] = []
        self._scene: QGraphicsScene | None = None
        
        self._rotate_handle = SelectionRotateHandle(parent=self)
        self._rotate_handle.setVisible(False)
        self._rotate_handle.setZValue(500)
        
        self.setZValue(499)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def update_from_items(
        self, items: list[QGraphicsItem], scene: QGraphicsScene
    ) -> None:
        """Recompute overlay from the current set of selected items."""
        self._managed_items = list(items)
        self._scene = scene
        
        if len(items) < 2:
            self.setVisible(False)
            self._rotate_handle.setVisible(False)
            return

        combined = QRectF()
        for item in self._managed_items:
            item_rect = item.mapToScene(
                item.boundingRect()
            ).boundingRect()
            combined = combined.united(item_rect)

        # Clamp bounds to scene bounds to prevent bugs outside the PDF layout
        if self._scene is not None:
            combined = combined.intersected(self._scene.sceneRect())

        self.prepareGeometryChange()
        self._bounding_rect = combined
        self.setPos(QPointF(0, 0))
        
        self._rotate_handle.update_position(self._bounding_rect)
        self._rotate_handle.setVisible(True)
        
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
        # Clip specifically to scene rect bounds visually to prevent weird overflows
        if self.scene() is not None:
            painter.setClipRect(self.scene().sceneRect())

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
            from items.shape_item import ShapeItem

            if isinstance(item, (StrokeItem, HighlightItem)):
                item_old_br = item.mapToScene(item.boundingRect()).boundingRect()
                top_left = transform.map(item_old_br.topLeft())
                bottom_right = transform.map(item_old_br.bottomRight())
                item_new_br = QRectF(top_left, bottom_right).normalized()
                item.apply_bounding_box_resize(item_new_br)
            elif isinstance(item, (TextBoxItem, ShapeItem)):
                item_old_br = item.get_rect()
                top_left = transform.map(item_old_br.topLeft())
                bottom_right = transform.map(item_old_br.bottomRight())
                item_new_br = QRectF(top_left, bottom_right).normalized()
                item.set_rect(item_new_br)

    def apply_group_rotation(self, delta_angle: float) -> None:
        """Orbit all managed items around the combined bounding box center by delta_angle in degrees."""
        if not self._managed_items:
            return

        pivot_scene = self.mapToScene(self._bounding_rect.center())
        
        from PySide6.QtGui import QTransform
        transform = QTransform()
        transform.translate(pivot_scene.x(), pivot_scene.y())
        transform.rotate(delta_angle)
        transform.translate(-pivot_scene.x(), -pivot_scene.y())
        
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem

        for item in self._managed_items:
            if isinstance(item, (StrokeItem, HighlightItem)):
                # Rotate the path in place around pivot
                path_scene = item.mapToScene(item._path)
                new_path_scene = transform.map(path_scene)
                item.prepareGeometryChange()
                item._path = item.mapFromScene(new_path_scene)
                item.update()
            elif isinstance(item, (TextBoxItem, ShapeItem, ImageItem)):
                # Orbit the item's transform origin
                to_scene = item.mapToScene(item.transformOriginPoint())
                target_to_scene = transform.map(to_scene)
                
                item.setRotation(item.rotation() + delta_angle)
                
                current_to_scene = item.mapToScene(item.transformOriginPoint())
                delta_pos = target_to_scene - current_to_scene
                item.setPos(item.pos() + delta_pos)

        self.prepareGeometryChange()
        
        # We need to recompute self._bounding_rect because items changed
        combined = QRectF()
        for item in self._managed_items:
            item_rect = item.mapToScene(item.boundingRect()).boundingRect()
            combined = combined.united(item_rect)
        
        # Clamp bounds to scene bounds
        if self._scene is not None:
            combined = combined.intersected(self._scene.sceneRect())
        self._bounding_rect = combined
        self.update()

    def get_path_state(self) -> tuple:
        """Snapshot the state of all managed items for undo."""
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem
        
        state = {}
        for item in self._managed_items:
            if isinstance(item, (StrokeItem, HighlightItem)):
                state[item] = item.get_path_state()
            elif isinstance(item, (ShapeItem, ImageItem, TextBoxItem)):
                state[item] = (
                    item.get_rect(), 
                    QPointF(item.pos()), 
                    item.rotation(), 
                    QPointF(item.transformOriginPoint())
                )
        return (QRectF(self._bounding_rect), state)

    def set_path_state(self, bounding_rect: QRectF, state: dict) -> None:
        """Restore all items from undo snapshot."""
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem

        for item, item_state in state.items():
            if isinstance(item, (StrokeItem, HighlightItem)):
                item.set_path_state(*item_state)
            elif isinstance(item, (ShapeItem, ImageItem, TextBoxItem)):
                item.set_rect(item_state[0])
                item.setPos(item_state[1])
                item.setRotation(item_state[2])
                item.setTransformOriginPoint(item_state[3])
        
        self.prepareGeometryChange()
        self._bounding_rect = QRectF(bounding_rect)
        self.update()
