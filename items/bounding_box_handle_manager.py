"""Bounding box handle manager for resizing StrokeItem / HighlightItem."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QObject
from PySide6.QtGui import QPen, QColor, QBrush, QPainterPath, QTransform
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
)

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class BoundingBoxHandle(QGraphicsEllipseItem):
    """Single resize handle drawn at a bounding-box position."""

    def __init__(self, pos_id: str, manager: BoundingBoxHandleManager) -> None:
        r = 5.0
        super().__init__(-r, -r, r * 2, r * 2)

        self.pos_id: str = pos_id
        self._manager: BoundingBoxHandleManager = manager
        self._dragging: bool = False

        self._apply_default_style()

        cursor_map = {
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
            "tc": Qt.CursorShape.SizeVerCursor,
            "bc": Qt.CursorShape.SizeVerCursor,
            "ml": Qt.CursorShape.SizeHorCursor,
            "mr": Qt.CursorShape.SizeHorCursor,
        }
        self.setCursor(cursor_map.get(pos_id, Qt.CursorShape.ArrowCursor))

        self.setZValue(1000)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def _apply_default_style(self) -> None:
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#3B7BF5"), 1.5))

    def hoverEnterEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setBrush(QBrush(QColor("#ddeeff")))
        self.update()
        event.accept()

    def hoverLeaveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._apply_default_style()
        self.update()
        event.accept()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._dragging = True
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._manager.on_handle_drag(self.pos_id, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._dragging:
            self._manager.on_handle_release(self.pos_id)
        self._dragging = False
        event.accept()

    def shape(self) -> QPainterPath:
        """Expand hit area for easier clicking."""
        path = QPainterPath()
        r = 5.0 + 8.0  # 8px extra padding
        path.addEllipse(-r, -r, r * 2, r * 2)
        return path

    def paint(self, painter, option, widget=None) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        super().paint(painter, option, widget)

    def boundingRect(self) -> QRectF:
        """Expand bounds to ensure the 1.5px pen and antialiasing don't leave ghosts."""
        return super().boundingRect().adjusted(-2, -2, 2, 2)


class BoundingBoxHandleManager(QObject):
    """Manages 8 resize handles for a single StrokeItem or HighlightItem."""

    POSITIONS = ["tl", "tc", "tr", "ml", "mr", "bl", "bc", "br"]

    def __init__(self, scene: PageScene) -> None:
        super().__init__()
        self._scene: PageScene = scene
        self._target_item: QGraphicsItem | None = None
        self._handles: list[BoundingBoxHandle] = []
        self._drag_start_rect: QRectF | None = None
        self._is_resizing: bool = False
        self._old_state: tuple | None = None

        for pos_id in self.POSITIONS:
            handle = BoundingBoxHandle(pos_id, manager=self)
            self._handles.append(handle)
            scene.addItem(handle)
            handle.setVisible(False)

    def attach_to(self, item: QGraphicsItem) -> None:
        """Bind handles to an item and show them."""
        self._ensure_handles()
        self._target_item = item
        self._reposition_handles()
        for h in self._handles:
            h.setVisible(True)

    def detach(self) -> None:
        """Hide handles and unbind."""
        self._target_item = None
        self._ensure_handles()
        for h in self._handles:
            h.setVisible(False)

    def reposition(self) -> None:
        """Public method to reposition handles (e.g. after item move)."""
        if self._target_item is not None:
            self._ensure_handles()
            self._reposition_handles()

    def _ensure_handles(self) -> None:
        """Recreate handles if C++ objects were deleted (e.g. by scene.clear())."""
        try:
            self._handles[0].isVisible()
        except RuntimeError:
            self._handles = []
            for pos_id in self.POSITIONS:
                handle = BoundingBoxHandle(pos_id, manager=self)
                self._handles.append(handle)
                self._scene.addItem(handle)
                handle.setVisible(False)

    def _reposition_handles(self) -> None:
        if not self._target_item:
            return
        br = self._target_item.mapToScene(
            self._target_item.boundingRect()
        ).boundingRect()

        pos_map = {
            "tl": QPointF(br.left(), br.top()),
            "tc": QPointF(br.center().x(), br.top()),
            "tr": QPointF(br.right(), br.top()),
            "ml": QPointF(br.left(), br.center().y()),
            "mr": QPointF(br.right(), br.center().y()),
            "bl": QPointF(br.left(), br.bottom()),
            "bc": QPointF(br.center().x(), br.bottom()),
            "br": QPointF(br.right(), br.bottom()),
        }
        for handle in self._handles:
            handle.setPos(pos_map[handle.pos_id])

    def on_handle_drag(self, pos_id: str, scene_pos: QPointF) -> None:
        """Called by handle during mouse move."""
        if not self._target_item:
            return

        if not self._is_resizing:
            self._is_resizing = True
            self._drag_start_rect = self._target_item.mapToScene(
                self._target_item.boundingRect()
            ).boundingRect()
            # Save state for undo
            self._old_state = self._target_item.get_path_state()

        current_br = self._target_item.mapToScene(
            self._target_item.boundingRect()
        ).boundingRect()

        new_br = QRectF(current_br)
        match pos_id:
            case "tl":
                new_br.setTopLeft(scene_pos)
            case "tc":
                new_br.setTop(scene_pos.y())
            case "tr":
                new_br.setTopRight(scene_pos)
            case "ml":
                new_br.setLeft(scene_pos.x())
            case "mr":
                new_br.setRight(scene_pos.x())
            case "bl":
                new_br.setBottomLeft(scene_pos)
            case "bc":
                new_br.setBottom(scene_pos.y())
            case "br":
                new_br.setBottomRight(scene_pos)

        new_br = new_br.normalized()
        if new_br.width() < 10 or new_br.height() < 10:
            return

        self._target_item.apply_bounding_box_resize(new_br)
        self._reposition_handles()

    def on_handle_release(self, pos_id: str) -> None:
        """Called by handle on mouse release — push undo command."""
        if not self._is_resizing:
            return
        self._is_resizing = False

        if not self._target_item or self._old_state is None:
            return

        new_state = self._target_item.get_path_state()

        # Check if anything actually changed
        old_path, old_pos = self._old_state
        new_path, new_pos = new_state
        if old_path == new_path and old_pos == new_pos:
            self._old_state = None
            return

        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.selection_overlay_item import SelectionOverlayItem
        from core import undo_stack

        if isinstance(self._target_item, StrokeItem):
            from commands.resize_stroke_command import ResizeStrokeCommand
            cmd = ResizeStrokeCommand(
                self._target_item, self._old_state, new_state, self._scene
            )
            undo_stack.push(cmd)
        elif isinstance(self._target_item, HighlightItem):
            from commands.resize_highlight_command import ResizeHighlightCommand
            cmd = ResizeHighlightCommand(
                self._target_item, self._old_state, new_state, self._scene
            )
            undo_stack.push(cmd)
        elif isinstance(self._target_item, SelectionOverlayItem):
            from commands.resize_items_command import ResizeItemsCommand
            cmd = ResizeItemsCommand(
                self._target_item, self._old_state, new_state, self._scene
            )
            undo_stack.push(cmd)

        self._old_state = None
