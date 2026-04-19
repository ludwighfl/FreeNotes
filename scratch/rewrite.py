"""Selection handle manager – single entry point for all selection UI.

Manages resize, move, rotate, and options handles for any item type
(StrokeItem, HighlightItem, TextBoxItem, ShapeItem, ImageItem) as
well as multi-selection.  All handles are scene-level items (not
children of any annotation).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QObject
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsItem

from items.handle_item import HandlePosition
from items.selection_resize_handle import SelectionResizeHandle
from items.selection_move_handle import SelectionMoveHandle
from items.selection_rotate_handle import SelectionRotateHandle
from items.selection_options_handle import SelectionOptionsHandle

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


# Handle positions used by all non-linear items
_ALL_POSITIONS = list(HandlePosition)


class SelectionHandleManager(QObject):
    """Manages all selection handles for any item type and multi-selection.

    Created once per PageScene.  Call ``attach(items)`` when the selection
    changes and ``detach()`` when it's cleared.
    """

    def __init__(self, scene: PageScene) -> None:
        super().__init__()
        self._scene: PageScene = scene
        self._target_items: list[QGraphicsItem] = []

        # Current bounding rect (scene coords) used for handle positioning
        self._current_rect: QRectF = QRectF()

        # --- Create scene-level handles ---
        self._resize_handles: dict[HandlePosition, SelectionResizeHandle] = {}
        for pos in _ALL_POSITIONS:
            handle = SelectionResizeHandle(pos, manager=self)
            self._resize_handles[pos] = handle
            scene.addItem(handle)
            handle.setVisible(False)

        self._move_handle = SelectionMoveHandle(manager=self)
        scene.addItem(self._move_handle)
        self._move_handle.setVisible(False)

        self._rotate_handle = SelectionRotateHandle(manager=self)
        scene.addItem(self._rotate_handle)
        self._rotate_handle.setVisible(False)

        self._options_handle = SelectionOptionsHandle(manager=self)
        scene.addItem(self._options_handle)
        self._options_handle.setVisible(False)

        # --- Drag state ---
        self._drag_start_rect: QRectF | None = None
        self._drag_old_states: dict | None = None
        self._move_start_positions: list[QPointF] | None = None
        
        # --- Group Geometry ---
        self._group_rect = QRectF()
        self._group_transform = QTransform()
        self._group_rotation = 0.0

    # ==================================================================
    # Public API
    # ==================================================================

    def attach(self, items: list[QGraphicsItem]) -> None:
        """Show handles for the given item(s)."""
        self._ensure_handles()
        self._target_items = list(items)
        self._group_rotation = 0.0
        self._options_handle.hide()
        self._reposition()

    def detach(self) -> None:
        """Hide all handles and unbind."""
        self._target_items.clear()
        self._ensure_handles()
        for h in self._resize_handles.values():
            h.setVisible(False)
        self._move_handle.setVisible(False)
        self._rotate_handle.setVisible(False)
        self._options_handle.hide()

    def reposition(self) -> None:
        """Re-compute handle positions (call after item geometry changes)."""
        if self._target_items:
            self._reposition()


    # ==================================================================
    # Group Geometry Computation
    # ==================================================================

    def _compute_group_geometry(self) -> None:
        """Compute bounding rect, transform, and rotation for current selection."""
        if not self._target_items:
            self._group_rect = QRectF()
            self._group_transform = QTransform()
            self._group_rotation = 0.0
            return

        is_single = len(self._target_items) == 1
        
        if is_single:
            item = self._target_items[0]
            if hasattr(item, "get_visual_rect"):
                self._group_rect = item.get_visual_rect()
            else:
                self._group_rect = item.boundingRect()
                
            self._group_transform = item.sceneTransform()
            if hasattr(item, "rotation"):
                 self._group_rotation = item.rotation()
            else:
                 self._group_rotation = 0.0
        else:
            combined = QRectF()
            for item in self._target_items:
                if hasattr(item, "get_visual_rect"):
                    local_rect = item.get_visual_rect()
                else:
                    local_rect = item.boundingRect()
                scene_rect = item.sceneTransform().mapRect(local_rect)
                combined = combined.united(scene_rect)
            
            center = combined.center()
            self._group_rect = QRectF(-combined.width()/2, -combined.height()/2, combined.width(), combined.height())
            self._group_transform = QTransform().translate(center.x(), center.y())
            self._group_rotation = getattr(self, "_group_rotation", 0.0)

    # ==================================================================
    # Handle positioning
    # ==================================================================

    def _reposition(self) -> None:
        """Position all handles around the current target item(s)."""
        if not self._target_items:
            return

        self._compute_group_geometry()

        # Update overlay
        if hasattr(self._scene, "_update_selection_overlay_from_manager"):
            self._scene._update_selection_overlay_from_manager(self._group_rect, self._group_transform)
        elif hasattr(self._scene, "_selection_overlay"):
             self._scene._selection_overlay.update_from_manager(self._group_rect, self._group_transform, True)

        is_single = len(self._target_items) == 1
        item = self._target_items[0] if is_single else None

        is_linear = False
        if is_single:
            from items.shape_item import ShapeItem
            from core.shape_style import ShapeType
            if isinstance(item, ShapeItem) and item._style.shape_type in (
                ShapeType.LINE, ShapeType.ARROW
            ):
                is_linear = True

        if is_linear:
            p1, p2 = item._get_line_points()
            scene_p1 = item.mapToScene(p1)
            scene_p2 = item.mapToScene(p2)
            for pos, handle in self._resize_handles.items():
                if pos == HandlePosition.TOP_LEFT:
                    handle.setPos(scene_p1)
                    handle.set_is_endpoint(True)
                    handle.setVisible(True)
                elif pos == HandlePosition.BOT_RIGHT:
                    handle.setPos(scene_p2)
                    handle.set_is_endpoint(True)
                    handle.setVisible(True)
                else:
                    handle.setVisible(False)
        else:
            pad = self._get_padding()
            padded = self._group_rect.adjusted(-pad, -pad, pad, pad)
            pos_map = {
                HandlePosition.TOP_LEFT: padded.topLeft(),
                HandlePosition.TOP_RIGHT: padded.topRight(),
                HandlePosition.MID_LEFT: QPointF(padded.left(), padded.center().y()),
                HandlePosition.MID_RIGHT: QPointF(padded.right(), padded.center().y()),
                HandlePosition.BOT_LEFT: padded.bottomLeft(),
                HandlePosition.BOT_RIGHT: padded.bottomRight(),
            }
            for pos, handle in self._resize_handles.items():
                local_pos = pos_map[pos]
                handle.setPos(self._group_transform.map(local_pos))
                handle.setRotation(self._group_rotation)
                handle.set_is_endpoint(False)
                handle.setVisible(True)

        pad = self._get_padding()
        padded = self._group_rect.adjusted(-pad, -pad, pad, pad)
        
        move_handle_pos = QPointF(padded.center().x(), padded.top() - 25.0)
        self._move_handle.setPos(self._group_transform.map(move_handle_pos))
        self._move_handle.setRotation(self._group_rotation)
        self._move_handle.setVisible(not is_linear)

        rotate_handle_pos = QPointF(padded.center().x(), padded.bottom() + 25.0)
        self._rotate_handle.setPos(self._group_transform.map(rotate_handle_pos))
        self._rotate_handle.setRotation(self._group_rotation)
        self._rotate_handle.setVisible(not is_linear)

        if self._options_handle.isVisible():
            opt_handle_pos = QPointF(padded.center().x(), padded.top() - 65.0)
            self._options_handle.setPos(self._group_transform.map(opt_handle_pos))
            self._options_handle.setRotation(self._group_rotation)

    def _get_padding(self) -> float:
        """Get padding between item rect and handles."""
        if len(self._target_items) == 1:
            from items.shape_item import ShapeItem
            item = self._target_items[0]
            if isinstance(item, ShapeItem):
                return item._style.stroke_width / 2.0 + 3.0
            return 3.0
        return 4.0

    # ==================================================================
    # Resize
    # ==================================================================

    def on_resize_start(self, handle_pos: HandlePosition, scene_pos: QPointF) -> None:
        self._drag_start_rect = QRectF(self._group_rect)
        self._drag_start_transform = QTransform(self._group_transform)
        self._drag_old_states = self._snapshot_states()

    def on_resize_drag(self, handle_pos: HandlePosition, scene_pos: QPointF) -> None:
        """Called during resize handle drag."""
        if self._drag_start_rect is None:
            return

        if len(self._target_items) == 1:
            self._resize_single(handle_pos, scene_pos)
        else:
            self._resize_multi(handle_pos, scene_pos)

        self._reposition()

    def on_resize_release(self, handle_pos: HandlePosition) -> None:
        """Called when resize handle drag ends – push undo command."""
        if self._drag_old_states is None:
            return

        new_states = self._snapshot_states()

        # Check if anything changed
        changed = False
        for item in self._drag_old_states:
            if self._drag_old_states[item] != new_states.get(item):
                changed = True
                break

        if changed:
            from commands.generic_resize_command import GenericResizeCommand
            from core import undo_stack
            cmd = GenericResizeCommand(
                self._drag_old_states, new_states, self._scene)
            undo_stack.push(cmd)

        self._drag_start_rect = None
        self._drag_old_states = None

    def _resize_single(self, handle_pos: HandlePosition, scene_pos: QPointF) -> None:
        """Resize a single item."""
        item = self._target_items[0]
        start_rect = self._drag_start_rect

        # Compute delta in scene coords
        delta = scene_pos - self._handle_start_pos(handle_pos, start_rect)

        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem

        if isinstance(item, (TextBoxItem, ShapeItem, ImageItem)):
            # These items have their own apply_handle_drag with rotation support
            # Transform delta to the item's local frame if rotated
            if isinstance(item, ShapeItem) and item._style.shape_type in (1, 2):
                pass # Line/Arrow use straight delta
            else:
                rotation = self._group_rotation
                if abs(rotation) > 0.01:
                    rad = math.radians(-rotation)
                    cos_a = math.cos(rad)
                    sin_a = math.sin(rad)
                    local_dx = delta.x() * cos_a - delta.y() * sin_a
                    local_dy = delta.x() * sin_a + delta.y() * cos_a
                    delta = QPointF(local_dx, local_dy)

            kwargs = {}
            if hasattr(item, 'get_line_dir'):
                kwargs['start_line_dir'] = item.get_line_dir()

            item.apply_handle_drag(handle_pos, start_rect, delta, **kwargs)
        else:
            # Stroke / Highlight: use bounding box resize
            new_br = self._compute_new_br(handle_pos, scene_pos)
            if new_br.width() >= 10 and new_br.height() >= 10:
                item.apply_bounding_box_resize(new_br)

    def _resize_multi(self, handle_pos: HandlePosition, scene_pos: QPointF) -> None:
        """Resize multiple items proportionally."""
        old_br = self._drag_start_rect
        if old_br.width() < 0.01 or old_br.height() < 0.01:
            return

        new_br = self._compute_new_br(handle_pos, scene_pos)
        if new_br.width() < 10 or new_br.height() < 10:
            return

        # Shift: proportional
        from PySide6.QtGui import QGuiApplication
        shift = bool(QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        if shift:
            aspect = old_br.width() / old_br.height()
            w = new_br.width()
            h = new_br.height()
            if abs(w / aspect - h) > abs(h * aspect - w):
                h = w / aspect
            else:
                w = h * aspect
            # Anchor to the opposite corner of the handle
            anchor = self._get_anchor(handle_pos, old_br)
            new_br = self._rect_from_anchor(anchor, handle_pos, w, h)

        sx = new_br.width() / old_br.width()
        sy = new_br.height() / old_br.height()

        transform = QTransform()
        transform.translate(new_br.left(), new_br.top())
        transform.scale(sx, sy)
        transform.translate(-old_br.left(), -old_br.top())

        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem

        for item in self._target_items:
            if isinstance(item, (StrokeItem, HighlightItem)):
                item_old_br = item.mapToScene(item.boundingRect()).boundingRect()
                tl = transform.map(item_old_br.topLeft())
                br = transform.map(item_old_br.bottomRight())
                item_new_br = QRectF(tl, br).normalized()
                item.apply_bounding_box_resize(item_new_br)
            elif isinstance(item, (TextBoxItem, ShapeItem, ImageItem)):
                item_old_rect = item.get_rect()
                tl = transform.map(item_old_rect.topLeft())
                br = transform.map(item_old_rect.bottomRight())
                item_new_rect = QRectF(tl, br).normalized()
                item.set_rect(item_new_rect)

    # ==================================================================
    # Move
    # ==================================================================

    def on_move_start(self) -> None:
        """Called when move drag begins."""
        self._move_start_positions = [
            QPointF(item.pos()) for item in self._target_items
        ]

    def on_move_drag(self, delta: QPointF) -> None:
        """Called during move drag."""
        if self._move_start_positions is None:
            return
        for item, start_pos in zip(self._target_items, self._move_start_positions):
            item.setPos(start_pos + delta)
        self._reposition()

    def on_move_release(self) -> None:
        """Called when move drag ends – push undo command."""
        if self._move_start_positions is None:
            return
        new_positions = [QPointF(item.pos()) for item in self._target_items]

        # Check if anything actually moved
        moved = any(
            old != new
            for old, new in zip(self._move_start_positions, new_positions)
        )
        if moved:
            from commands.generic_move_command import GenericMoveCommand
            from core import undo_stack
            cmd = GenericMoveCommand(
                list(self._target_items),
                self._move_start_positions,
                new_positions,
                self._scene,
            )
            undo_stack.push(cmd)

        self._move_start_positions = None

    # ==================================================================
    # Rotate
    # ==================================================================

    def get_rotation_center(self) -> QPointF:
        return self._group_transform.map(QPointF(0,0))

    def on_rotate_start(self) -> None:
        self._drag_old_states = self._snapshot_states()

    def on_rotate_drag(self, delta_angle: float) -> None:
        if not self._target_items:
            return

        if len(self._target_items) == 1:
            self._rotate_single(delta_angle)
        else:
            self._rotate_multi(delta_angle)

        self._reposition()

    def on_rotate_release(self) -> None:
        if self._drag_old_states is None:
            return

        new_states = self._snapshot_states()
        changed = False
        for item in self._drag_old_states:
            if self._drag_old_states[item] != new_states.get(item):
                changed = True
                break

        if changed:
            from commands.rotate_items_command import RotateItemsCommand
            from core import undo_stack
            cmd = RotateItemsCommand(
                self._drag_old_states,
                new_states,
                QRectF(),
                QRectF(),
                self._scene,
            )
            undo_stack.push(cmd)

        self._drag_old_states = None

    def _rotate_single(self, delta_angle: float) -> None:
        item = self._target_items[0]

        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem

        if isinstance(item, (StrokeItem, HighlightItem)):
            br = item.mapToScene(item.get_visual_rect()).boundingRect()
            pivot = br.center()
            transform = QTransform()
            transform.translate(pivot.x(), pivot.y())
            transform.rotate(delta_angle)
            transform.translate(-pivot.x(), -pivot.y())

            path_scene = item.mapToScene(item._path)
            new_path_scene = transform.map(path_scene)
            item.prepareGeometryChange()
            item._path = item.mapFromScene(new_path_scene)
            item._cached_br = None
            item.update()
        elif isinstance(item, (TextBoxItem, ShapeItem, ImageItem)):
            center = QPointF(item._rect.width() / 2.0, item._rect.height() / 2.0)
            if center != item.transformOriginPoint():
                p1 = item.mapToScene(QPointF(0, 0))
                item.setTransformOriginPoint(center)
                p2 = item.mapToScene(QPointF(0, 0))
                item.setPos(item.pos() + (p1 - p2))
            item.setRotation(item.rotation() + delta_angle)

    def _rotate_multi(self, delta_angle: float) -> None:
        self._group_rotation += delta_angle
        pivot = self._group_transform.map(QPointF(0,0))

        # Update group transform rotation
        self._group_transform = QTransform().translate(pivot.x(), pivot.y()).rotate(self._group_rotation)

        transform = QTransform()
        transform.translate(pivot.x(), pivot.y())
        transform.rotate(delta_angle)
        transform.translate(-pivot.x(), -pivot.y())

        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem

        for item in self._target_items:
            if isinstance(item, (StrokeItem, HighlightItem)):
                path_scene = item.mapToScene(item._path)
                new_path_scene = transform.map(path_scene)
                item.prepareGeometryChange()
                item._path = item.mapFromScene(new_path_scene)
                item._cached_br = None
                item.update()
            elif isinstance(item, (TextBoxItem, ShapeItem, ImageItem)):
                to_scene = item.mapToScene(item.transformOriginPoint())
                target = transform.map(to_scene)
                item.setRotation(item.rotation() + delta_angle)
                current = item.mapToScene(item.transformOriginPoint())
                item.setPos(item.pos() + (target - current))

    # ==================================================================
    # Copy / Cut / Delete
    # ==================================================================

    def toggle_options(self) -> None:
        """Toggle the options handle visibility."""
        if self._options_handle.isVisible():
            self._options_handle.hide()
        else:
            pad = self._get_padding()
            padded = self._current_rect.adjusted(-pad, -pad, pad, pad)
            self._options_handle.update_position(padded)
            self._options_handle.show()

    def do_copy(self) -> None:
        self._scene._copy_items_to_clipboard(list(self._target_items))

    def do_cut(self) -> None:
        self._scene.cut_selected()

    def do_delete(self) -> None:
        from commands.delete_items_command import DeleteItemsCommand
        from core.undo_stack import get_stack

        items = list(self._target_items)
        self._scene.clear_selection()

        for item in items:
            if hasattr(item, "stop_editing"):
                item.stop_editing()
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            if hasattr(self._scene, "remove_item_from_registry"):
                self._scene.remove_item_from_registry(item)

        cmd = DeleteItemsCommand(items, self._scene)
        get_stack().push(cmd)

    # ==================================================================
    # State snapshots (for undo)
    # ==================================================================

    def _snapshot_states(self) -> dict:
        """Snapshot the state of all target items."""
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.text_box_item import TextBoxItem
        from items.shape_item import ShapeItem
        from items.image_item import ImageItem

        state = {}
        for item in self._target_items:
            if isinstance(item, (StrokeItem, HighlightItem)):
                state[item] = item.get_path_state()
            elif isinstance(item, (ShapeItem, ImageItem, TextBoxItem)):
                state[item] = (
                    QRectF(item.get_rect()),
                    QPointF(item.pos()),
                    item.rotation(),
                    QPointF(item.transformOriginPoint()),
                )
        return state

    # ==================================================================
    # Helpers
    # ==================================================================

    def _handle_start_pos(
        self, handle_pos: HandlePosition, rect: QRectF
    ) -> QPointF:
        pad = self._get_padding()
        padded = rect.adjusted(-pad, -pad, pad, pad)
        match handle_pos:
            case HandlePosition.TOP_LEFT:
                local = padded.topLeft()
            case HandlePosition.TOP_RIGHT:
                local = padded.topRight()
            case HandlePosition.MID_LEFT:
                local = QPointF(padded.left(), padded.center().y())
            case HandlePosition.MID_RIGHT:
                local = QPointF(padded.right(), padded.center().y())
            case HandlePosition.BOT_LEFT:
                local = padded.bottomLeft()
            case HandlePosition.BOT_RIGHT:
                local = padded.bottomRight()
        return self._drag_start_transform.map(local)

    def _compute_new_br(
        self, handle_pos: HandlePosition, scene_pos: QPointF
    ) -> QRectF:
        """Compute the new bounding rect from a resize handle position."""
        new_br = QRectF(self._drag_start_rect)
        match handle_pos:
            case HandlePosition.TOP_LEFT:
                new_br.setTopLeft(scene_pos)
            case HandlePosition.TOP_RIGHT:
                new_br.setTopRight(scene_pos)
            case HandlePosition.MID_LEFT:
                new_br.setLeft(scene_pos.x())
            case HandlePosition.MID_RIGHT:
                new_br.setRight(scene_pos.x())
            case HandlePosition.BOT_LEFT:
                new_br.setBottomLeft(scene_pos)
            case HandlePosition.BOT_RIGHT:
                new_br.setBottomRight(scene_pos)
        return new_br.normalized()

    def _get_anchor(self, handle_pos: HandlePosition, rect: QRectF) -> QPointF:
        """Get the anchor (opposite corner) for proportional resize."""
        match handle_pos:
            case HandlePosition.TOP_LEFT:
                return rect.bottomRight()
            case HandlePosition.TOP_RIGHT:
                return rect.bottomLeft()
            case HandlePosition.BOT_LEFT:
                return rect.topRight()
            case HandlePosition.BOT_RIGHT:
                return rect.topLeft()
            case _:
                return rect.center()

    def _rect_from_anchor(
        self, anchor: QPointF, handle_pos: HandlePosition,
        w: float, h: float,
    ) -> QRectF:
        """Construct a QRectF from an anchor point and dimensions."""
        match handle_pos:
            case HandlePosition.TOP_LEFT:
                return QRectF(anchor.x() - w, anchor.y() - h, w, h)
            case HandlePosition.TOP_RIGHT:
                return QRectF(anchor.x(), anchor.y() - h, w, h)
            case HandlePosition.BOT_LEFT:
                return QRectF(anchor.x() - w, anchor.y(), w, h)
            case HandlePosition.BOT_RIGHT:
                return QRectF(anchor.x(), anchor.y(), w, h)
            case _:
                return QRectF(anchor.x() - w / 2, anchor.y() - h / 2, w, h)

    def _ensure_handles(self) -> None:
        """Recreate handles if C++ objects were deleted (e.g. by scene.clear())."""
        try:
            self._move_handle.isVisible()
        except RuntimeError:
            # Recreate all handles
            self._resize_handles = {}
            for pos in _ALL_POSITIONS:
                handle = SelectionResizeHandle(pos, manager=self)
                self._resize_handles[pos] = handle
                self._scene.addItem(handle)
                handle.setVisible(False)

            self._move_handle = SelectionMoveHandle(manager=self)
            self._scene.addItem(self._move_handle)
            self._move_handle.setVisible(False)

            self._rotate_handle = SelectionRotateHandle(manager=self)
            self._scene.addItem(self._rotate_handle)
            self._rotate_handle.setVisible(False)

            self._options_handle = SelectionOptionsHandle(manager=self)
            self._scene.addItem(self._options_handle)
            self._options_handle.setVisible(False)
