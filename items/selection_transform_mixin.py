"""Mixin for SelectionBoxItem managing transformation math and undo/redo transactions."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsItem

from items.handle_item import HandlePosition
from items.interactive_item import (
    IInteractiveItem,
    IRectResizable,
    ILinearItem,
)
from commands.transform_items_command import TransformItemsCommand

if TYPE_CHECKING:
    from items.selection_overlay_item import SelectionBoxItem


class SelectionTransformMixin:
    """Handles mathematical resizing, rotation, translation, and transactional undo commands."""

    # ==================================================================
    # Handle Drag & Undo Management
    # ==================================================================

    def _on_handle_press(self: SelectionBoxItem) -> None:
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

    def _restore_to_start(self: SelectionBoxItem) -> None:
        """Restore all items and overlay to their drag-start state."""
        for item, state in self._drag_before_state.items():
            if hasattr(item, "restore_state"):
                item.restore_state(state)
        self.setPos(self._drag_start_overlay_pos)
        self.setRotation(self._drag_start_overlay_rotation)
        self.setTransformOriginPoint(self._drag_start_overlay_origin)
        for h in self._handles.values():
            if hasattr(h, "update_cursor"):
                h.update_cursor()

    def _on_handle_release(self: SelectionBoxItem, action_name: str) -> None:
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
        if self.scene() is not None and self._managed_items:
            self.attach(self._managed_items, self.scene())

    def _on_resize_handle_drag(
        self: SelectionBoxItem,
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
            self._apply_linear_drag(handle_pos, scene_start, scene_current, shift)
            return

        # 3. Determine minimum allowable width & height
        min_w = self.MIN_SIZE
        min_h = self.MIN_SIZE
        if self._is_single_rect_mode and len(self._managed_items) == 1:
            single = self._managed_items[0]
            if hasattr(single, "get_min_width"):
                min_w = single.get_min_width()
            elif hasattr(single, "MIN_WIDTH"):
                min_w = single.MIN_WIDTH
            if hasattr(single, "MIN_HEIGHT"):
                min_h = single.MIN_HEIGHT

        # 4. Compute delta in overlay-local coordinates
        local_delta = self.mapFromScene(scene_current) - self.mapFromScene(scene_start)

        # 5. Compute clamped new local rect so handles can NEVER cross or meet opposite edges
        new_rect = QRectF(start_rect)
        match handle_pos:
            case HandlePosition.TOP_LEFT:
                new_left = min(start_rect.left() + local_delta.x(), start_rect.right() - min_w)
                new_top = min(start_rect.top() + local_delta.y(), start_rect.bottom() - min_h)
                new_rect = QRectF(QPointF(new_left, new_top), start_rect.bottomRight())
            case HandlePosition.TOP_CENTER:
                new_top = min(start_rect.top() + local_delta.y(), start_rect.bottom() - min_h)
                new_rect = QRectF(start_rect.left(), new_top, start_rect.width(), start_rect.bottom() - new_top)
            case HandlePosition.TOP_RIGHT:
                new_right = max(start_rect.right() + local_delta.x(), start_rect.left() + min_w)
                new_top = min(start_rect.top() + local_delta.y(), start_rect.bottom() - min_h)
                new_rect = QRectF(QPointF(start_rect.left(), new_top), QPointF(new_right, start_rect.bottom()))
            case HandlePosition.MID_LEFT:
                new_left = min(start_rect.left() + local_delta.x(), start_rect.right() - min_w)
                new_rect = QRectF(new_left, start_rect.top(), start_rect.right() - new_left, start_rect.height())
            case HandlePosition.MID_RIGHT:
                new_right = max(start_rect.right() + local_delta.x(), start_rect.left() + min_w)
                new_rect = QRectF(start_rect.left(), start_rect.top(), new_right - start_rect.left(), start_rect.height())
            case HandlePosition.BOT_LEFT:
                new_left = min(start_rect.left() + local_delta.x(), start_rect.right() - min_w)
                new_bottom = max(start_rect.bottom() + local_delta.y(), start_rect.top() + min_h)
                new_rect = QRectF(QPointF(new_left, start_rect.top()), QPointF(start_rect.right(), new_bottom))
            case HandlePosition.BOT_CENTER:
                new_bottom = max(start_rect.bottom() + local_delta.y(), start_rect.top() + min_h)
                new_rect = QRectF(start_rect.left(), start_rect.top(), start_rect.width(), new_bottom - start_rect.top())
            case HandlePosition.BOT_RIGHT:
                new_right = max(start_rect.right() + local_delta.x(), start_rect.left() + min_w)
                new_bottom = max(start_rect.bottom() + local_delta.y(), start_rect.top() + min_h)
                new_rect = QRectF(start_rect.topLeft(), QPointF(new_right, new_bottom))

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
            orig_w = max(min_w, start_rect.width())
            orig_h = max(min_h, start_rect.height())

            if handle_pos in (HandlePosition.MID_LEFT, HandlePosition.MID_RIGHT):
                scale = 1.0 + (local_delta.x() / orig_w if handle_pos == HandlePosition.MID_RIGHT else -local_delta.x() / orig_w)
                scale = max(min_w / orig_w, min_h / orig_h, scale)
                w = orig_w * scale
                h = orig_h * scale
                cy = start_rect.center().y()
                if handle_pos == HandlePosition.MID_LEFT:
                    new_rect = QRectF(start_rect.right() - w, cy - h / 2.0, w, h)
                else:
                    new_rect = QRectF(start_rect.left(), cy - h / 2.0, w, h)
            else:
                # Smooth diagonal projection: project cursor movement onto aspect ratio vector
                ux = -1.0 if handle_pos in (HandlePosition.TOP_LEFT, HandlePosition.BOT_LEFT) else 1.0
                uy = -1.0 if handle_pos in (HandlePosition.TOP_LEFT, HandlePosition.TOP_RIGHT) else 1.0

                diag_len_sq = orig_w * orig_w + orig_h * orig_h
                k = (local_delta.x() * ux * orig_w + local_delta.y() * uy * orig_h) / max(0.001, diag_len_sq)
                scale = max(min_w / orig_w, min_h / orig_h, 1.0 + k)

                w = orig_w * scale
                h = orig_h * scale

                if handle_pos == HandlePosition.TOP_LEFT:
                    new_rect = QRectF(start_rect.right() - w, start_rect.bottom() - h, w, h)
                elif handle_pos == HandlePosition.TOP_RIGHT:
                    new_rect = QRectF(start_rect.left(), start_rect.bottom() - h, w, h)
                elif handle_pos == HandlePosition.BOT_LEFT:
                    new_rect = QRectF(start_rect.right() - w, start_rect.top(), w, h)
                elif handle_pos == HandlePosition.BOT_RIGHT:
                    new_rect = QRectF(start_rect.left(), start_rect.top(), w, h)

        # 6. Apply to items
        if self._is_single_rect_mode and len(self._managed_items) == 1:
            self._apply_single_rect_resize(handle_pos, start_rect, new_rect)
        else:
            self._apply_multi_resize(handle_pos, start_rect, new_rect)

    def _apply_linear_drag(
        self: SelectionBoxItem,
        handle_pos: HandlePosition,
        scene_start: QPointF,
        scene_current: QPointF,
        shift: bool = False,
    ) -> None:
        """Apply linear endpoint drag allowing full 360-degree rotation and 45-deg shift snapping."""
        linear_item = self._managed_items[0]
        if not isinstance(linear_item, ILinearItem):
            return
        scene_delta = scene_current - scene_start

        if handle_pos == HandlePosition.TOP_LEFT:
            p2 = linear_item.get_end_point()
            target_p1 = linear_item.get_start_point() + scene_delta
            if shift:
                dx = target_p1.x() - p2.x()
                dy = target_p1.y() - p2.y()
                length = math.hypot(dx, dy)
                if length > 0.001:
                    angle = math.degrees(math.atan2(dy, dx))
                    snapped = round(angle / 45.0) * 45.0
                    rad = math.radians(snapped)
                    target_p1 = QPointF(p2.x() + math.cos(rad) * length, p2.y() + math.sin(rad) * length)
            linear_item.set_start_point(target_p1)
        elif handle_pos == HandlePosition.BOT_RIGHT:
            p1 = linear_item.get_start_point()
            target_p2 = linear_item.get_end_point() + scene_delta
            if shift:
                dx = target_p2.x() - p1.x()
                dy = target_p2.y() - p1.y()
                length = math.hypot(dx, dy)
                if length > 0.001:
                    angle = math.degrees(math.atan2(dy, dx))
                    snapped = round(angle / 45.0) * 45.0
                    rad = math.radians(snapped)
                    target_p2 = QPointF(p1.x() + math.cos(rad) * length, p1.y() + math.sin(rad) * length)
            linear_item.set_end_point(target_p2)
        self._attach_linear(linear_item)

    def _apply_single_rect_resize(
        self: SelectionBoxItem,
        handle_pos: HandlePosition,
        start_rect: QRectF,
        new_rect: QRectF,
    ) -> None:
        """Resize a single item without drift."""
        item = self._managed_items[0]
        if isinstance(item, IRectResizable):
            min_w = self.MIN_SIZE
            min_h = self.MIN_SIZE
            if hasattr(item, "get_min_width"):
                min_w = item.get_min_width()
            elif hasattr(item, "MIN_WIDTH"):
                min_w = item.MIN_WIDTH
            if hasattr(item, "MIN_HEIGHT"):
                min_h = item.MIN_HEIGHT

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

            target_scene_tl = item.mapToScene(QPointF(new_rect.left(), new_rect.top()))
            w = max(min_w, new_rect.width())
            if handle_pos in (HandlePosition.MID_LEFT, HandlePosition.MID_RIGHT) and hasattr(item, "apply_font_scale"):
                h = 0.0
            else:
                h = max(min_h, new_rect.height())

            item.set_transform_origin(QPointF(0, 0))
            item.setPos(target_scene_tl)
            item.set_geometry_rect(QRectF(target_scene_tl.x(), target_scene_tl.y(), w, h))

            actual_geo = item.get_geometry_rect()
            actual_w = actual_geo.width()
            actual_h = actual_geo.height()

            center_origin = QPointF(actual_w / 2.0, actual_h / 2.0)
            p1 = item.mapToScene(QPointF(0, 0))
            item.set_transform_origin(center_origin)
            p2 = item.mapToScene(QPointF(0, 0))
            item.setPos(item.pos() + (p1 - p2))

            self.prepareGeometryChange()
            self._bounding_rect = QRectF(0, 0, actual_w, actual_h)
            self.setTransformOriginPoint(center_origin)
            self.setPos(item.pos())
            self._position_standard_handles(self._bounding_rect)
            self.update()
        elif isinstance(item, IInteractiveItem):
            if start_rect.width() > 0.01 and start_rect.height() > 0.01:
                sx = new_rect.width() / start_rect.width()
                sy = new_rect.height() / start_rect.height()
                pivot = self._get_resize_pivot(handle_pos, start_rect)
                pivot_scene = self.mapToScene(pivot)
                item.apply_scale(sx, sy, pivot_scene)

            self.prepareGeometryChange()
            self._bounding_rect = new_rect
            self._position_standard_handles(self._bounding_rect)
            self.update()

    def _apply_multi_resize(
        self: SelectionBoxItem,
        handle_pos: HandlePosition,
        start_rect: QRectF,
        new_rect: QRectF,
    ) -> None:
        """Resize multiple items via scale from start_rect to new_rect with fixed pivot."""
        if start_rect.width() < 0.01 or start_rect.height() < 0.01:
            return

        sx = new_rect.width() / start_rect.width()
        sy = new_rect.height() / start_rect.height()
        pivot = self._get_resize_pivot(handle_pos, start_rect)
        pivot_scene = self.mapToScene(pivot)

        for item in self._managed_items:
            item.apply_scale(sx, sy, pivot_scene)

        self.prepareGeometryChange()
        self._bounding_rect = new_rect
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

    def _ensure_transform_origin_at_center(self: SelectionBoxItem) -> None:
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

    def _apply_rotation_from_start(self: SelectionBoxItem, total_angle: float) -> None:
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

        for h in self._handles.values():
            if hasattr(h, "update_cursor"):
                h.update_cursor()

        padded = self._bounding_rect.adjusted(-self.PADDING, -self.PADDING, self.PADDING, self.PADDING)
        self._rotate_handle.update_position(padded)
        self.update()

    def apply_group_rotation(self: SelectionBoxItem, delta_angle: float) -> None:
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

    def apply_group_move(self: SelectionBoxItem, delta: QPointF) -> None:
        """Move all managed items by delta."""
        for item in self._managed_items:
            if isinstance(item, QGraphicsItem):
                item.setPos(item.pos() + delta)
        self.attach(list(self._managed_items), self.scene())
