"""Shape tool – draw geometric shapes by click-and-drag."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QSizeF, QObject
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class ShapeTool(BaseTool):
    """Tool for creating geometric shapes by dragging on the canvas."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._drawing: bool = False
        self._start_pos: QPointF | None = None
        self._preview_item = None  # ShapeItem

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    def activate(self, scene: PageScene) -> None:
        for view in scene.views():
            view.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self, scene: PageScene) -> None:
        if self._preview_item is not None:
            try:
                scene.removeItem(self._preview_item)
            except RuntimeError:
                pass
            self._preview_item = None
        self._drawing = False
        self._start_pos = None
        scene.clear_selection()
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()

        # Check if click on existing ShapeItem → select it
        from items.shape_item import ShapeItem
        from items.selection_overlay_item import SelectionOverlayItem
        items_at = scene.items(QRectF(pos.x() - 3, pos.y() - 3, 6, 6))
        
        # Check if we clicked on a control handle. If so, let Qt's default dispatch handle it.
        from items.bounding_box_handle_manager import BoundingBoxHandle
        from items.handle_item import ResizeHandleItem
        from items.rotate_handle_item import RotateHandleItem
        from items.options_handle_item import OptionsHandleItem
        from items.move_handle_item import MoveHandleItem

        if any(isinstance(i, (BoundingBoxHandle, ResizeHandleItem, RotateHandleItem, OptionsHandleItem, MoveHandleItem)) for i in items_at):
            return

        hit = next(
            (i for i in items_at
             if isinstance(i, ShapeItem)
             and not isinstance(i, SelectionOverlayItem)),
            None,
        )
        if hit:
            scene.set_selection([hit])
            return

        # Click on empty area → start drawing
        scene.clear_selection()
        page_idx = scene.get_page_index_at(pos)
        if page_idx < 0:
            return

        self._drawing = True
        self._start_pos = pos

        from app.app_state import AppState
        from core.shape_style import ShapeStyle

        app = AppState()
        style = ShapeStyle(
            shape_type=app.active_shape_type,
            stroke_color=app.tool_style.color,
            fill_color=app.shape_fill_color,
            stroke_width=app.tool_style.width,
        )

        from items.shape_item import ShapeItem
        self._preview_item = ShapeItem(
            rect=QRectF(pos, QSizeF(0, 0)),
            style=style,
            page_index=page_idx,
        )
        self._preview_item.setOpacity(0.7)
        scene.addItem(self._preview_item)

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if not self._drawing or not self._preview_item:
            return
        pos = event.scenePos()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        rect, constrained_end = self._build_rect(self._start_pos, pos, shift)
        self._preview_item.set_rect(rect)
        self._preview_item.set_line_dir(self._calc_line_dir(self._start_pos, constrained_end))

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._drawing or not self._preview_item:
            return

        self._drawing = False
        pos = event.scenePos()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        rect, constrained_end = self._build_rect(self._start_pos, pos, shift)
        line_dir = self._calc_line_dir(self._start_pos, constrained_end)

        # Too small → discard
        if math.hypot(rect.width(), rect.height()) < 8:
            scene.removeItem(self._preview_item)
            self._preview_item = None
            self._start_pos = None
            return

        # Finalize
        self._preview_item.set_rect(rect)
        self._preview_item.set_line_dir(line_dir)
        self._preview_item.setOpacity(1.0)

        scene.add_item_to_registry(self._preview_item)

        from commands.create_shape_command import CreateShapeCommand
        from core import undo_stack
        cmd = CreateShapeCommand(self._preview_item, scene)
        undo_stack.push(cmd)

        scene.set_selection([self._preview_item])

        self._preview_item = None
        self._start_pos = None
        self.tool_action_completed.emit()

    def _build_rect(
        self, start: QPointF, end: QPointF, constrain: bool
    ) -> tuple[QRectF, QPointF]:
        """Build rect from start/end. returns (normalized_rect, constrained_end)."""
        dx = end.x() - start.x()
        dy = end.y() - start.y()

        if constrain:
            from core.shape_style import ShapeType
            from app.app_state import AppState
            shape_type = AppState().active_shape_type

            if shape_type in (ShapeType.LINE, ShapeType.ARROW):
                # 45° snap for lines/arrows
                length = math.hypot(dx, dy)
                if length > 0:
                    angle = math.degrees(math.atan2(dy, dx))
                    snapped = round(angle / 45) * 45
                    rad = math.radians(snapped)
                    dx = math.cos(rad) * length
                    dy = math.sin(rad) * length
                end = QPointF(start.x() + dx, start.y() + dy)
            else:
                # Square/circle: shorter side determines both
                side = min(abs(dx), abs(dy))
                dx = math.copysign(side, dx)
                dy = math.copysign(side, dy)
                end = QPointF(start.x() + dx, start.y() + dy)

        return QRectF(start, end).normalized(), end

    def _calc_line_dir(self, start: QPointF, end: QPointF) -> int:
        """Calculate line direction flag based on relative coordinates."""
        sx, sy = start.x(), start.y()
        ex, ey = end.x(), end.y()
        if ex >= sx and ey >= sy:
            return 0  # TL to BR
        elif ex < sx and ey < sy:
            return 1  # BR to TL
        elif ex < sx and ey >= sy:
            return 2  # TR to BL
        else:
            return 3  # BL to TR



