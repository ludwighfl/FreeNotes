"""Selection box item – unified overlay for single and multi-item selection."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QBrush,
    QPainterPath,
    QPainterPathStroker,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from items.handle_item import HandlePosition
from items.interactive_item import (
    IInteractiveItem,
    IRectResizable,
    ILinearItem,
)
from items.selection_handles import (
    get_rotation_cursor,
    SelectionResizeHandle,
    SelectionRotateHandle,
    SelectionMoveHandle,
    SelectionOptionsHandle,
)
from items.selection_transform_mixin import SelectionTransformMixin

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene

# Handle positions used in standard (non-linear) mode — 6 handles, no TC/BC.
_STANDARD_HANDLE_POSITIONS = {
    HandlePosition.TOP_LEFT,
    HandlePosition.TOP_RIGHT,
    HandlePosition.MID_LEFT,
    HandlePosition.MID_RIGHT,
    HandlePosition.BOT_LEFT,
    HandlePosition.BOT_RIGHT,
}


class SelectionBoxItem(SelectionTransformMixin, QGraphicsItem):
    """Unified overlay providing selection frames, handles, and undo transaction management."""

    MIN_SIZE: float = 16.0
    PADDING: float = 4.0

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._bounding_rect: QRectF = QRectF()
        self._managed_items: list[IInteractiveItem] = []
        self._scene: QGraphicsScene | None = None
        self._is_linear_mode: bool = False
        self._is_single_rect_mode: bool = False
        self._drag_before_state: dict[QGraphicsItem, dict] = {}
        # Overlay transform at drag start, for restore-and-reapply.
        self._drag_start_overlay_pos: QPointF = QPointF()
        self._drag_start_overlay_rotation: float = 0.0
        self._drag_start_overlay_origin: QPointF = QPointF()

        # Child handles
        self._handles: dict[HandlePosition, SelectionResizeHandle] = {}
        for pos in list(HandlePosition):
            h = SelectionResizeHandle(pos, parent=self)
            h.setVisible(False)
            self._handles[pos] = h

        self._rotate_handle = SelectionRotateHandle(parent=self)
        self._rotate_handle.setVisible(False)

        self._move_handle = SelectionMoveHandle(parent=self)
        self._move_handle.setVisible(False)

        self._options_handle = SelectionOptionsHandle(parent=self)
        self._options_handle.setVisible(False)

        self.setZValue(499)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

        self._is_corner_rotating: bool = False
        self._rotation_center: QPointF = QPointF()
        self._start_angle: float = 0.0

        self._is_box_moving: bool = False
        self._drag_start_scene_pos: QPointF | None = None

    def attach(self, items: list[QGraphicsItem], scene: QGraphicsScene) -> None:
        """Attach overlay to one or more selectable items."""
        self._managed_items = [i for i in items if isinstance(i, IInteractiveItem)]
        self._scene = scene

        # Always reset overlay transform to identity before attaching
        self.setRotation(0)
        self.setTransformOriginPoint(QPointF(0, 0))

        is_single = len(self._managed_items) == 1
        single_item = self._managed_items[0] if is_single else None

        # Linear mode: single line/arrow
        if is_single and isinstance(single_item, ILinearItem) and single_item.is_linear():
            self._attach_linear(single_item)
            return

        # Single item mode: mirror item transform for proper rotation
        if is_single and isinstance(single_item, IInteractiveItem):
            self._attach_single_item(single_item)
            return

        # Multi-selection mode
        self._attach_multi()

    def _attach_linear(self, item: ILinearItem) -> None:
        """Attach in linear (2-endpoint) mode for lines/arrows."""
        self._is_linear_mode = True
        self._is_single_rect_mode = False

        p1 = item.get_start_point()
        p2 = item.get_end_point()
        combined = QRectF(
            QPointF(min(p1.x(), p2.x()), min(p1.y(), p2.y())),
            QPointF(max(p1.x(), p2.x()), max(p1.y(), p2.y())),
        )
        self.prepareGeometryChange()
        self._bounding_rect = combined
        self.setPos(QPointF(0, 0))

        for pos, h in self._handles.items():
            if pos in (HandlePosition.TOP_LEFT, HandlePosition.BOT_RIGHT):
                h.set_is_endpoint(True)
                h.setVisible(True)
                h.setPos(p1 if pos == HandlePosition.TOP_LEFT else p2)
            else:
                h.setVisible(False)

        self._rotate_handle.setVisible(False)
        self._move_handle.setVisible(False)
        self._options_handle.setVisible(False)

        self.setVisible(True)
        self.update()

    def _attach_single_item(self, item: IInteractiveItem) -> None:
        """Attach to any single item, mirroring its transform centered."""
        self._is_linear_mode = False
        self._is_single_rect_mode = True

        if isinstance(item, QGraphicsItem):
            if isinstance(item, IRectResizable):
                geo_rect = item.get_geometry_rect()
                w, h = geo_rect.width(), geo_rect.height()
                local_rect = QRectF(0, 0, w, h)
                center_origin = QPointF(w / 2.0, h / 2.0)
            else:
                local_rect = item.boundingRect()
                center_origin = local_rect.center()

            # Ensure item transform origin is at center of local bounding rect
            if hasattr(item, "set_transform_origin") and item.get_transform_origin() != center_origin:
                item.set_transform_origin(center_origin)
            elif hasattr(item, "setTransformOriginPoint") and item.transformOriginPoint() != center_origin:
                item.setTransformOriginPoint(center_origin)

            rot = item.get_rotation_angle() if hasattr(item, "get_rotation_angle") else item.rotation()

            self.setTransformOriginPoint(center_origin)
            self.setRotation(rot)
            self.setPos(item.pos())

            self.prepareGeometryChange()
            self._bounding_rect = local_rect
            self._position_standard_handles(local_rect)
            self.setVisible(True)
            self.update()

    def _attach_multi(self) -> None:
        """Attach AABB overlay for multi-selection."""
        self._is_linear_mode = False
        self._is_single_rect_mode = False

        self.setRotation(0)
        self.setTransformOriginPoint(QPointF(0, 0))

        combined = QRectF()
        for item in self._managed_items:
            if isinstance(item, QGraphicsItem):
                if isinstance(item, IRectResizable):
                    geo = item.get_geometry_rect()
                    local_r = QRectF(0, 0, geo.width(), geo.height())
                    scene_poly = item.mapToScene(local_r)
                    combined = combined.united(scene_poly.boundingRect())
                else:
                    item_rect = item.mapToScene(item.boundingRect()).boundingRect()
                    combined = combined.united(item_rect)

        if self._scene is not None:
            combined = combined.intersected(self._scene.sceneRect())

        self.prepareGeometryChange()
        self._bounding_rect = combined
        self.setPos(QPointF(0, 0))
        self._position_standard_handles(combined)
        self.setVisible(True)
        self.update()

    def _position_standard_handles(self, r: QRectF) -> None:
        """Position 6 resize handles (no TOP_CENTER / BOT_CENTER)."""
        padded = r.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)
        positions = {
            HandlePosition.TOP_LEFT: QPointF(padded.left(), padded.top()),
            HandlePosition.TOP_RIGHT: QPointF(padded.right(), padded.top()),
            HandlePosition.MID_LEFT: QPointF(padded.left(), padded.center().y()),
            HandlePosition.MID_RIGHT: QPointF(padded.right(), padded.center().y()),
            HandlePosition.BOT_LEFT: QPointF(padded.left(), padded.bottom()),
            HandlePosition.BOT_RIGHT: QPointF(padded.right(), padded.bottom()),
        }

        for pos, h in self._handles.items():
            if pos in positions:
                h.set_is_endpoint(False)
                h.setPos(positions[pos])
                h.update_cursor()
                h.setVisible(True)
            else:
                h.setVisible(False)

        self._rotate_handle.setVisible(False)
        self._move_handle.setVisible(False)
        self._options_handle.setVisible(False)

    def update_from_items(
        self, items: list[QGraphicsItem], scene: QGraphicsScene
    ) -> None:
        """Alias for backward compatibility with SceneSelectionMixin."""
        self.attach(items, scene)

    def _set_all_handles_visible(self, visible: bool) -> None:
        for h in self._handles.values():
            h.setVisible(visible)
        self._rotate_handle.setVisible(False)
        self._move_handle.setVisible(False)
        self._options_handle.setVisible(False)

    def _corner_positions(self) -> dict[str, QPointF]:
        padded = self._bounding_rect.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)
        return {
            "tl": padded.topLeft(),
            "tr": padded.topRight(),
            "bl": padded.bottomLeft(),
            "br": padded.bottomRight(),
        }

    def get_rotation_corner(self, scene_pos: QPointF) -> str | None:
        """Return the corner key ('tl', 'tr', 'bl', 'br') if scene_pos is in its rotation zone."""
        if self._is_linear_mode or not self._managed_items or len(self._managed_items) != 1 or self._bounding_rect.isNull():
            return None
        local_pos = self.mapFromScene(scene_pos)
        for key, corner_pt in self._corner_positions().items():
            dx = local_pos.x() - corner_pt.x()
            dy = local_pos.y() - corner_pt.y()
            dist = math.hypot(dx, dy)
            if 6.0 <= dist <= 26.0:
                return key
        return None

    def is_in_rotation_zone(self, scene_pos: QPointF) -> bool:
        """Check if scene_pos is in any corner rotation zone."""
        return self.get_rotation_corner(scene_pos) is not None

    def _is_any_item_editing(self) -> bool:
        """Return True if any managed item is currently being edited."""
        for item in self._managed_items:
            if getattr(item, "_is_editing", False):
                return True
        return False

    def is_in_move_zone(self, scene_pos: QPointF) -> bool:
        """Check if scene_pos is in the move zone."""
        if not self._managed_items or self._bounding_rect.isNull():
            return False

        # If in corner rotation zone, rotation takes precedence
        if self.is_in_rotation_zone(scene_pos):
            return False

        # If on any visible resize handle, resize takes precedence
        for h in self._handles.values():
            if h.isVisible() and h.sceneBoundingRect().contains(scene_pos):
                return False

        local_pos = self.mapFromScene(scene_pos)

        # 1. Linear mode (lines / arrows)
        if self._is_linear_mode:
            if len(self._managed_items) == 1 and isinstance(self._managed_items[0], ILinearItem):
                item = self._managed_items[0]
                p1 = self.mapFromScene(item.get_start_point())
                p2 = self.mapFromScene(item.get_end_point())
                line_vec = p2 - p1
                length = math.hypot(line_vec.x(), line_vec.y())
                if length < 1.0:
                    return False
                t = max(0.0, min(1.0, ((local_pos.x() - p1.x()) * line_vec.x() + (local_pos.y() - p1.y()) * line_vec.y()) / (length * length)))
                proj = p1 + line_vec * t
                dist = math.hypot(local_pos.x() - proj.x(), local_pos.y() - proj.y())
                return dist <= 12.0
            return False

        # 2. Standard box mode
        box_rect = self._bounding_rect.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)

        if self._is_any_item_editing():
            # In text edit mode: only the border frame (14px thickness) is the move zone,
            # leaving the interior free for text cursor & selection.
            outer_rect = box_rect.adjusted(-7.0, -7.0, 7.0, 7.0)
            inner_rect = box_rect.adjusted(7.0, 7.0, -7.0, -7.0)
            if inner_rect.width() > 0 and inner_rect.height() > 0:
                return outer_rect.contains(local_pos) and not inner_rect.contains(local_pos)
            return outer_rect.contains(local_pos)

        # When not in text edit mode: the entire selection box (interior + border) is draggable to move
        return box_rect.adjusted(7.0, 7.0, 7.0, 7.0).contains(local_pos)

    def boundingRect(self) -> QRectF:
        pad = self.PADDING + 28.0
        return self._bounding_rect.adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self._bounding_rect.isNull() or not self._managed_items:
            return path

        # 1. Linear mode
        if self._is_linear_mode:
            if len(self._managed_items) == 1 and isinstance(self._managed_items[0], ILinearItem):
                item = self._managed_items[0]
                p1 = self.mapFromScene(item.get_start_point())
                p2 = self.mapFromScene(item.get_end_point())
                line_path = QPainterPath()
                line_path.moveTo(p1)
                line_path.lineTo(p2)
                stroker = QPainterPathStroker()
                stroker.setWidth(14.0)
                return stroker.createStroke(line_path)
            return super().shape()

        # 2. Corner rotation zones (only active for single item selection)
        if len(self._managed_items) == 1:
            for corner_pt in self._corner_positions().values():
                path.addEllipse(corner_pt, 26.0, 26.0)

        # 3. Border stroke or filled rect
        box_rect = self._bounding_rect.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)
        if self._is_any_item_editing():
            stroker = QPainterPathStroker()
            stroker.setWidth(14.0)
            rect_path = QPainterPath()
            rect_path.addRect(box_rect)
            path.addPath(stroker.createStroke(rect_path))
        else:
            path.addRect(box_rect.adjusted(-4.0, -4.0, 4.0, 4.0))

        return path

    def _angle_to(self, scene_pos: QPointF) -> float:
        dx = scene_pos.x() - self._rotation_center.x()
        dy = scene_pos.y() - self._rotation_center.y()
        return math.degrees(math.atan2(dy, dx))

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        pos = event.scenePos()
        if self.is_in_rotation_zone(pos):
            self.setCursor(get_rotation_cursor())
        elif self.is_in_move_zone(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        pos = event.scenePos()

        # 1. Corner rotation
        if self.is_in_rotation_zone(pos):
            self._is_corner_rotating = True
            self._ensure_transform_origin_at_center()
            center = self._bounding_rect.center()
            self._rotation_center = self.mapToScene(center)
            self._start_angle = self._angle_to(pos)
            self._on_handle_press()
            self.setCursor(get_rotation_cursor())
            event.accept()
            return

        # 2. Drag-move
        if self.is_in_move_zone(pos):
            self._is_box_moving = True
            self._drag_start_scene_pos = pos
            self._on_handle_press()
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
            return

        event.ignore()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._is_corner_rotating:
            delta_angle = self._angle_to(event.scenePos()) - self._start_angle
            raw_target_angle = self._drag_start_overlay_rotation + delta_angle

            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                target_angle = round(raw_target_angle / 45.0) * 45.0
                total_angle = target_angle - self._drag_start_overlay_rotation
            else:
                total_angle = delta_angle

            self._apply_rotation_from_start(total_angle)
            self.update()
            event.accept()
            return

        if getattr(self, "_is_box_moving", False):
            if self._drag_start_scene_pos is not None:
                delta = event.scenePos() - self._drag_start_scene_pos
                self._drag_start_scene_pos = event.scenePos()
                self.apply_group_move(delta)
                self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._is_corner_rotating:
            self._is_corner_rotating = False
            self.update()
            self._on_handle_release("Rotieren")
            event.accept()
            return

        if getattr(self, "_is_box_moving", False):
            self._is_box_moving = False
            self._drag_start_scene_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            self._on_handle_release("Verschieben")
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if len(self._managed_items) == 1 and hasattr(self._managed_items[0], "start_editing"):
            self._managed_items[0].start_editing()
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        if getattr(self.scene(), "_is_rendering_thumbnail", False):
            return
        if self._bounding_rect.isNull() or not self._managed_items:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._is_linear_mode:
            pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
            pen.setDashPattern([5, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if len(self._managed_items) == 1 and isinstance(self._managed_items[0], ILinearItem):
                p1 = self._managed_items[0].get_start_point()
                p2 = self._managed_items[0].get_end_point()
                painter.drawLine(p1, p2)
        else:
            sel_pen = QPen(QColor("#3B7BF5"), 1.2, Qt.PenStyle.SolidLine)
            painter.setPen(sel_pen)
            painter.setBrush(QBrush(QColor(59, 123, 245, 10)))
            painter.setOpacity(1.0)
            box_rect = self._bounding_rect.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)
            painter.drawRect(box_rect)

    # ==================================================================
    # Options Actions (Copy / Cut / Delete)
    # ==================================================================

    def delete_selected(self) -> None:
        """Delete all managed items via DeleteItemsCommand."""
        scene = self.scene()
        if not scene or not self._managed_items:
            return
        from commands.delete_items_command import DeleteItemsCommand
        from core.undo_stack import get_stack

        raw_items = [i for i in self._managed_items if isinstance(i, QGraphicsItem)]
        cmd = DeleteItemsCommand(raw_items, scene)
        get_stack().push(cmd)
        self.setVisible(False)

    def copy_selected(self) -> None:
        """Copy managed items to clipboard."""
        scene = self.scene()
        if scene and hasattr(scene, "copy_items"):
            raw_items = [i for i in self._managed_items if isinstance(i, QGraphicsItem)]
            scene.copy_items(raw_items)

    def cut_selected(self) -> None:
        """Cut managed items to clipboard."""
        scene = self.scene()
        if scene and hasattr(scene, "cut_items"):
            raw_items = [i for i in self._managed_items if isinstance(i, QGraphicsItem)]
            scene.cut_items(raw_items)

    def get_path_state(self) -> tuple:
        """Legacy compatibility method for old code paths."""
        state = {
            item: item.capture_state()
            for item in self._managed_items
        }
        return (QRectF(self._bounding_rect), state)

    def set_path_state(self, bounding_rect: QRectF, state: dict) -> None:
        """Legacy compatibility method for old code paths."""
        for item, item_state in state.items():
            item.restore_state(item_state)
        self.prepareGeometryChange()
        self._bounding_rect = QRectF(bounding_rect)
        self.update()


# Alias for backward compatibility during refactoring
SelectionOverlayItem = SelectionBoxItem
