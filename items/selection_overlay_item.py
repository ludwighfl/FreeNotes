"""Selection box item – unified overlay for single and multi-item selection."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from items.handle_item import ResizeHandleItem, HandlePosition
from items.rotate_handle_item import RotateHandleItem
from items.move_handle_item import MoveHandleItem
from items.options_handle_item import OptionsHandleItem
from items.interactive_item import (
    IInteractiveItem,
    IRectResizable,
    ILinearItem,
    IPathScalable,
)
from commands.transform_items_command import TransformItemsCommand

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


class SelectionResizeHandle(ResizeHandleItem):
    """Resize/Endpoint handle for SelectionBoxItem."""

    def __init__(self, position: HandlePosition, parent: QGraphicsItem) -> None:
        super().__init__(position, parent)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        self._drag_start_pos = event.scenePos()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        self._drag_start_rect = QRectF(overlay._bounding_rect)
        overlay._on_handle_press()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging or self._drag_start_pos is None or self._drag_start_rect is None:
            return
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        overlay._on_resize_handle_drag(
            self._position, self._drag_start_rect,
            self._drag_start_pos, event.scenePos(), shift,
        )
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_release("Skalieren")
        event.accept()


class SelectionRotateHandle(RotateHandleItem):
    """Rotate handle for SelectionBoxItem."""

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]

        center = overlay._bounding_rect.center()
        overlay._ensure_transform_origin_at_center()

        self._rotation_center = overlay.mapToScene(center)
        self._start_angle = self._angle_to(event.scenePos())
        self._last_angle = 0.0
        overlay._on_handle_press()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        delta_angle = self._angle_to(event.scenePos()) - self._start_angle
        raw_target_angle = overlay._drag_start_overlay_rotation + delta_angle

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            target_angle = round(raw_target_angle / 45.0) * 45.0
            total_angle = target_angle - overlay._drag_start_overlay_rotation
        else:
            total_angle = delta_angle

        overlay._apply_rotation_from_start(total_angle)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_release("Rotieren")
        event.accept()


class SelectionMoveHandle(MoveHandleItem):
    """Move handle pill for SelectionBoxItem."""

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        self._drag_start_scene_pos = event.scenePos()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_press()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging or self._drag_start_scene_pos is None:
            return
        delta = event.scenePos() - self._drag_start_scene_pos
        self._drag_start_scene_pos = event.scenePos()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay.apply_group_move(delta)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_release("Verschieben")
        event.accept()


class SelectionOptionsHandle(OptionsHandleItem):
    """Options handle bar for SelectionBoxItem."""

    def _execute_action(self, index: int) -> None:
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        if overlay is None:
            return
        if index == 0:
            overlay.copy_selected()
        elif index == 1:
            overlay.cut_selected()
        elif index == 2:
            overlay.delete_selected()


class SelectionBoxItem(QGraphicsItem):
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
        if hasattr(self, "_options_handle"):
            self._options_handle.update_position(self._bounding_rect)

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
                h.setVisible(True)
            else:
                h.setVisible(False)

        is_single = len(self._managed_items) == 1
        if is_single:
            self._rotate_handle.update_position(padded)
            self._rotate_handle.setVisible(True)
        else:
            self._rotate_handle.setVisible(False)
        self._move_handle.update_position(padded)
        self._move_handle.setVisible(True)
        if hasattr(self, "_options_handle"):
            self._options_handle.update_position(padded)

    def update_from_items(
        self, items: list[QGraphicsItem], scene: QGraphicsScene
    ) -> None:
        """Alias for backward compatibility with SceneSelectionMixin."""
        self.attach(items, scene)

    def _set_all_handles_visible(self, visible: bool) -> None:
        for h in self._handles.values():
            h.setVisible(visible)
        self._rotate_handle.setVisible(visible)
        self._move_handle.setVisible(visible)
        self._options_handle.setVisible(visible)

    def boundingRect(self) -> QRectF:
        pad = self.PADDING + 10.0
        return self._bounding_rect.adjusted(-pad, -pad, pad, pad)

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
            pen = QPen(QColor("#3B7BF5"), 2.0, Qt.PenStyle.DashLine)
            pen.setDashPattern([6, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if len(self._managed_items) == 1 and isinstance(self._managed_items[0], ILinearItem):
                p1 = self._managed_items[0].get_start_point()
                p2 = self._managed_items[0].get_end_point()
                painter.drawLine(p1, p2)
        else:
            sel_pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
            sel_pen.setDashPattern([6, 4])
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setOpacity(1.0)
            box_rect = self._bounding_rect.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)
            painter.drawRect(box_rect)

    # ==================================================================
    # Handle Drag & Undo Management
    # ==================================================================

    def _on_handle_press(self) -> None:
        """Capture item states and overlay transform at start of handle drag."""
        self._drag_before_state = {
            item: item.capture_state()
            for item in self._managed_items
            if isinstance(item, IInteractiveItem)
        }
        # Save overlay transform for restore-and-reapply
        self._drag_start_overlay_pos = QPointF(self.pos())
        self._drag_start_overlay_rotation = self.rotation()
        self._drag_start_overlay_origin = QPointF(self.transformOriginPoint())

    def _restore_to_start(self) -> None:
        """Restore all items and overlay to their drag-start state."""
        for item, state in self._drag_before_state.items():
            if hasattr(item, "restore_state"):
                item.restore_state(state)
        self.setPos(self._drag_start_overlay_pos)
        self.setRotation(self._drag_start_overlay_rotation)
        self.setTransformOriginPoint(self._drag_start_overlay_origin)

    def _on_handle_release(self, action_name: str) -> None:
        """Capture item states at end of handle drag and push TransformItemsCommand."""
        if not self._drag_before_state:
            return

        after_state = {
            item: item.capture_state()
            for item in self._managed_items
            if isinstance(item, IInteractiveItem)
        }

        has_changed = False
        for item, b_state in self._drag_before_state.items():
            a_state = after_state.get(item)
            if a_state != b_state:
                has_changed = True
                break

        if has_changed and self.scene() is not None:
            from core.undo_stack import get_stack
            cmd = TransformItemsCommand(
                items_before=self._drag_before_state,
                items_after=after_state,
                scene=self.scene(),
                text=action_name,
            )
            get_stack().push(cmd)

        self._drag_before_state = {}

    def _on_resize_handle_drag(
        self,
        handle_pos: HandlePosition,
        start_rect: QRectF,
        scene_start: QPointF,
        scene_current: QPointF,
        shift: bool,
    ) -> None:
        """Handle dragging of resize / endpoint handles."""
        # 1. Restore everything to start state
        self._restore_to_start()

        # 2. Linear mode endpoint drag
        if self._is_linear_mode and len(self._managed_items) == 1 and isinstance(self._managed_items[0], ILinearItem):
            self._apply_linear_drag(handle_pos, scene_start, scene_current)
            return

        # 3. Compute delta in overlay-local coordinates
        local_delta = self.mapFromScene(scene_current) - self.mapFromScene(scene_start)

        # 4. Compute new local rect
        new_rect = QRectF(start_rect)
        match handle_pos:
            case HandlePosition.TOP_LEFT:
                new_rect.setTopLeft(start_rect.topLeft() + local_delta)
            case HandlePosition.TOP_CENTER:
                new_rect.setTop(start_rect.top() + local_delta.y())
            case HandlePosition.TOP_RIGHT:
                new_rect.setTopRight(start_rect.topRight() + local_delta)
            case HandlePosition.MID_LEFT:
                new_rect.setLeft(start_rect.left() + local_delta.x())
            case HandlePosition.MID_RIGHT:
                new_rect.setRight(start_rect.right() + local_delta.x())
            case HandlePosition.BOT_LEFT:
                new_rect.setBottomLeft(start_rect.bottomLeft() + local_delta)
            case HandlePosition.BOT_CENTER:
                new_rect.setBottom(start_rect.bottom() + local_delta.y())
            case HandlePosition.BOT_RIGHT:
                new_rect.setBottomRight(start_rect.bottomRight() + local_delta)

        # Force aspect ratio for multi-selection, shift key, or text box corner drag
        is_corner = handle_pos in (
            HandlePosition.TOP_LEFT, HandlePosition.TOP_RIGHT,
            HandlePosition.BOT_LEFT, HandlePosition.BOT_RIGHT,
        )
        has_font_scale = (
            self._is_single_rect_mode and len(self._managed_items) == 1 and hasattr(self._managed_items[0], "apply_font_scale")
        )
        force_aspect = shift or len(self._managed_items) > 1 or (has_font_scale and is_corner)

        if force_aspect and handle_pos in (
            HandlePosition.TOP_LEFT, HandlePosition.TOP_RIGHT,
            HandlePosition.BOT_LEFT, HandlePosition.BOT_RIGHT,
            HandlePosition.MID_LEFT, HandlePosition.MID_RIGHT,
        ):
            orig_w = max(self.MIN_SIZE, start_rect.width())
            orig_h = max(self.MIN_SIZE, start_rect.height())
            aspect = orig_w / orig_h
            w = max(self.MIN_SIZE, new_rect.width())
            h = max(self.MIN_SIZE, new_rect.height())

            if handle_pos in (HandlePosition.MID_LEFT, HandlePosition.MID_RIGHT):
                h = w / aspect
                cy = start_rect.center().y()
                new_rect.setTop(cy - h / 2.0)
                new_rect.setBottom(cy + h / 2.0)
            else:
                if abs(w - orig_w) > abs(h - orig_h):
                    h = w / aspect
                else:
                    w = h * aspect

                if handle_pos == HandlePosition.TOP_LEFT:
                    new_rect.setTopLeft(QPointF(start_rect.right() - w, start_rect.bottom() - h))
                elif handle_pos == HandlePosition.TOP_RIGHT:
                    new_rect.setTopRight(QPointF(start_rect.left() + w, start_rect.bottom() - h))
                elif handle_pos == HandlePosition.BOT_LEFT:
                    new_rect.setBottomLeft(QPointF(start_rect.right() - w, start_rect.top() + h))
                elif handle_pos == HandlePosition.BOT_RIGHT:
                    new_rect.setBottomRight(QPointF(start_rect.left() + w, start_rect.top() + h))

        new_rect = new_rect.normalized()
        if new_rect.width() < self.MIN_SIZE:
            new_rect.setWidth(self.MIN_SIZE)
        if new_rect.height() < self.MIN_SIZE:
            new_rect.setHeight(self.MIN_SIZE)

        # 5. Apply to items
        if self._is_single_rect_mode and len(self._managed_items) == 1:
            self._apply_single_rect_resize(handle_pos, start_rect, new_rect)
        else:
            self._apply_multi_resize(handle_pos, start_rect, new_rect)

    def _apply_linear_drag(self, handle_pos: HandlePosition, scene_start: QPointF, scene_current: QPointF) -> None:
        """Apply linear endpoint drag using start state + scene delta."""
        linear_item = self._managed_items[0]
        if not isinstance(linear_item, ILinearItem):
            return
        scene_delta = scene_current - scene_start
        if handle_pos == HandlePosition.TOP_LEFT:
            linear_item.set_start_point(linear_item.get_start_point() + scene_delta)
        elif handle_pos == HandlePosition.BOT_RIGHT:
            linear_item.set_end_point(linear_item.get_end_point() + scene_delta)
        self._attach_linear(linear_item)

    def _apply_single_rect_resize(
        self, handle_pos: HandlePosition, start_rect: QRectF, new_rect: QRectF
    ) -> None:
        """Resize a single item without drift."""
        item = self._managed_items[0]
        if isinstance(item, IRectResizable):
            # Scale font size for text box when dragging corner handles
            if (
                handle_pos in (
                    HandlePosition.TOP_LEFT, HandlePosition.TOP_RIGHT,
                    HandlePosition.BOT_LEFT, HandlePosition.BOT_RIGHT,
                )
                and hasattr(item, "apply_font_scale")
                and start_rect.height() > 0.01
            ):
                scale_factor = new_rect.height() / start_rect.height()
                item.apply_font_scale(scale_factor)
                if hasattr(item, "PADDING"):
                    start_text_w = max(1.0, start_rect.width() - item.PADDING * 2)
                    new_text_w = max(1.0, start_text_w * scale_factor + 3.0)
                    new_rect.setWidth(new_text_w + item.PADDING * 2)

            target_scene_tl = item.mapToScene(QPointF(new_rect.left(), new_rect.top()))
            w = max(self.MIN_SIZE, new_rect.width())
            h = max(self.MIN_SIZE, new_rect.height())

            item.set_transform_origin(QPointF(0, 0))
            item.setPos(target_scene_tl)
            item.set_geometry_rect(QRectF(target_scene_tl.x(), target_scene_tl.y(), w, h))

            center_origin = QPointF(w / 2.0, h / 2.0)
            p1 = item.mapToScene(QPointF(0, 0))
            item.set_transform_origin(center_origin)
            p2 = item.mapToScene(QPointF(0, 0))
            item.setPos(item.pos() + (p1 - p2))

            self._attach_single_item(item)
        elif isinstance(item, IInteractiveItem):
            if self._bounding_rect.width() > 0.01 and self._bounding_rect.height() > 0.01:
                sx = new_rect.width() / self._bounding_rect.width()
                sy = new_rect.height() / self._bounding_rect.height()
                pivot = self._bounding_rect.center()
                item.apply_scale(sx, sy, pivot)
            self._attach_single_item(item)

    def _apply_multi_resize(self, handle_pos: HandlePosition, start_rect: QRectF, new_rect: QRectF) -> None:
        """Resize multiple items via scale from start_rect to new_rect."""
        if start_rect.width() < 0.01 or start_rect.height() < 0.01:
            return

        sx = new_rect.width() / start_rect.width()
        sy = new_rect.height() / start_rect.height()
        pivot = self._get_resize_pivot(handle_pos, start_rect)

        for item in self._managed_items:
            item.apply_scale(sx, sy, pivot)

        # Update overlay bounding box from actual item bounding rects
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

        self.prepareGeometryChange()
        self._bounding_rect = combined if not combined.isNull() else new_rect
        self._position_standard_handles(self._bounding_rect)
        self.update()

    @staticmethod
    def _get_resize_pivot(handle_pos: HandlePosition, rect: QRectF) -> QPointF:
        """Return the fixed anchor point (opposite corner/edge) for a resize drag."""
        match handle_pos:
            case HandlePosition.TOP_LEFT:
                return rect.bottomRight()
            case HandlePosition.TOP_RIGHT:
                return rect.bottomLeft()
            case HandlePosition.BOT_LEFT:
                return rect.topRight()
            case HandlePosition.BOT_RIGHT:
                return rect.topLeft()
            case HandlePosition.MID_LEFT:
                return QPointF(rect.right(), rect.center().y())
            case HandlePosition.MID_RIGHT:
                return QPointF(rect.left(), rect.center().y())
            case HandlePosition.TOP_CENTER:
                return QPointF(rect.center().x(), rect.bottom())
            case HandlePosition.BOT_CENTER:
                return QPointF(rect.center().x(), rect.top())
        return rect.center()

    # ==================================================================
    # Transformations
    # ==================================================================

    def _ensure_transform_origin_at_center(self) -> None:
        """Ensure overlay and single items have transform origin at center."""
        center = self._bounding_rect.center()
        if center != self.transformOriginPoint():
            old_scene = self.mapToScene(QPointF(0, 0))
            self.setTransformOriginPoint(center)
            new_scene = self.mapToScene(QPointF(0, 0))
            self.setPos(self.pos() + (old_scene - new_scene))

        if self._is_single_rect_mode and len(self._managed_items) == 1:
            item = self._managed_items[0]
            if isinstance(item, QGraphicsItem):
                if isinstance(item, IRectResizable):
                    item_center = QPointF(
                        item.get_geometry_rect().width() / 2.0,
                        item.get_geometry_rect().height() / 2.0,
                    )
                else:
                    item_center = item.boundingRect().center()

                if hasattr(item, "set_transform_origin") and item.get_transform_origin() != item_center:
                    old_s = item.mapToScene(QPointF(0, 0))
                    item.set_transform_origin(item_center)
                    new_s = item.mapToScene(QPointF(0, 0))
                    item.setPos(item.pos() + (old_s - new_s))

    def _apply_rotation_from_start(self, total_angle: float) -> None:
        """Apply rotation using restore-and-reapply with total angle from start."""
        if not self._managed_items:
            return

        self._restore_to_start()
        self._ensure_transform_origin_at_center()

        if len(self._managed_items) == 1:
            item = self._managed_items[0]
            start_state = self._drag_before_state.get(item)
            start_rot = start_state.get("rotation", item.get_rotation_angle() if hasattr(item, "get_rotation_angle") else item.rotation()) if start_state else (item.get_rotation_angle() if hasattr(item, "get_rotation_angle") else item.rotation())
            if hasattr(item, "set_rotation_angle"):
                item.set_rotation_angle(start_rot + total_angle)
            else:
                item.setRotation(start_rot + total_angle)
            self.setRotation(self._drag_start_overlay_rotation + total_angle)
        else:
            pivot_scene = self._bounding_rect.center()
            transform = QTransform()
            transform.translate(pivot_scene.x(), pivot_scene.y())
            transform.rotate(total_angle)
            transform.translate(-pivot_scene.x(), -pivot_scene.y())

            for item in self._managed_items:
                if isinstance(item, QGraphicsItem):
                    start_state = self._drag_before_state.get(item)
                    start_rot = start_state.get("rotation", item.get_rotation_angle() if hasattr(item, "get_rotation_angle") else item.rotation()) if start_state else (item.get_rotation_angle() if hasattr(item, "get_rotation_angle") else item.rotation())
                    if hasattr(item, "set_rotation_angle"):
                        item.set_rotation_angle(start_rot + total_angle)
                    else:
                        item.setRotation(start_rot + total_angle)

                    origin_scene = item.mapToScene(item.get_transform_origin() if hasattr(item, "get_transform_origin") else item.transformOriginPoint())
                    target_scene = transform.map(origin_scene)
                    delta_pos = target_scene - origin_scene
                    item.setPos(item.pos() + delta_pos)

            # Rotate multi-selection overlay around its center
            self.setTransformOriginPoint(pivot_scene)
            self.setRotation(self._drag_start_overlay_rotation + total_angle)

        padded = self._bounding_rect.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)
        self._rotate_handle.update_position(padded)
        self.update()

    def apply_group_rotation(self, delta_angle: float) -> None:
        """Rotate managed items by delta_angle (incremental). Legacy API."""
        if not self._managed_items:
            return
        if len(self._managed_items) == 1:
            item = self._managed_items[0]
            if hasattr(item, "set_rotation_angle"):
                item.set_rotation_angle(item.get_rotation_angle() + delta_angle)
            else:
                item.setRotation(item.rotation() + delta_angle)
        else:
            pivot_scene = self._bounding_rect.center()
            transform = QTransform()
            transform.translate(pivot_scene.x(), pivot_scene.y())
            transform.rotate(delta_angle)
            transform.translate(-pivot_scene.x(), -pivot_scene.y())

            for item in self._managed_items:
                if isinstance(item, QGraphicsItem):
                    rot = item.get_rotation_angle() if hasattr(item, "get_rotation_angle") else item.rotation()
                    if hasattr(item, "set_rotation_angle"):
                        item.set_rotation_angle(rot + delta_angle)
                    else:
                        item.setRotation(rot + delta_angle)
                    origin_scene = item.mapToScene(item.get_transform_origin() if hasattr(item, "get_transform_origin") else item.transformOriginPoint())
                    target_scene = transform.map(origin_scene)
                    item.setPos(item.pos() + (target_scene - origin_scene))

        self.attach(list(self._managed_items), self.scene())

    def apply_group_move(self, delta: QPointF) -> None:
        """Move all managed items by delta."""
        for item in self._managed_items:
            if isinstance(item, QGraphicsItem):
                item.setPos(item.pos() + delta)
        self.attach(list(self._managed_items), self.scene())

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
