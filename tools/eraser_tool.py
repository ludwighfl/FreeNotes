"""Eraser tool – Object and Pixel eraser modes for removing annotations."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QObject, QRectF, QPointF
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsSceneMouseEvent, QGraphicsItem

from items.eraser_cursor_item import EraserCursorItem
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.shape_item import ShapeItem
from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.page_scene import PageScene


class EraserMode(Enum):
    """Eraser operating mode."""
    OBJECT = "object"  # Remove entire item on touch
    PIXEL = "pixel"    # Remove only the touched portion of strokes


class EraserTool(BaseTool):
    """Eraser tool with Object and Pixel modes.

    Object mode: touching an item removes it entirely.
    Pixel mode: subtracts eraser shape from StrokeItem paths;
    HighlightItems fall back to object-mode removal.
    """

    EraserMode = EraserMode  # Expose enum as class attribute

    DEFAULT_RADIUS: float = 15.0
    AFFECTED_ITEM_TYPES = (StrokeItem, HighlightItem, ShapeItem)

    def __init__(
        self,
        mode: EraserMode = EraserMode.OBJECT,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._mode: EraserMode = mode
        self._radius: float = self.DEFAULT_RADIUS
        self._cursor_item: EraserCursorItem | None = None
        self._is_erasing: bool = False
        # Object eraser: list of (item, None)
        self._affected_items: list[tuple] = []
        self._erased_items: list[QGraphicsItem] = []
        # Pixel eraser: deduplicated original paths (first encounter only)
        self._original_paths: dict[int, QPainterPath] = {}
        # Pixel eraser: id(item) → item reference for lookup
        self._item_refs: dict[int, QGraphicsItem] = {}
        # Pixel eraser: items fully deleted during this drag
        self._deleted_items: list[QGraphicsItem] = []
        # Pixel eraser: new items created by highlight splits
        self._created_items: list[HighlightItem] = []
        # Interpolation: remember last mouse position
        self._last_erase_pos: QPointF | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> EraserMode:
        return self._mode

    @mode.setter
    def mode(self, value: EraserMode) -> None:
        self._mode = value

    @property
    def radius(self) -> float:
        return self._radius

    @radius.setter
    def radius(self, value: float) -> None:
        self._radius = value
        if self._cursor_item is not None:
            self._cursor_item.radius = value

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.BlankCursor

    # ------------------------------------------------------------------
    # Tool lifecycle
    # ------------------------------------------------------------------

    def activate(self, scene: PageScene) -> None:
        for view in scene.views():
            view.setCursor(Qt.CursorShape.BlankCursor)
        self._cursor_item = EraserCursorItem(self._radius)
        scene.addItem(self._cursor_item)
        self._cursor_item.setVisible(False)

    def deactivate(self, scene: PageScene) -> None:
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)
        if self._cursor_item is not None:
            scene.removeItem(self._cursor_item)
            self._cursor_item = None
        self._is_erasing = False
        self._affected_items.clear()
        self._erased_items.clear()
        self._original_paths.clear()
        self._item_refs.clear()
        self._deleted_items.clear()
        self._created_items.clear()
        self._last_erase_pos = None

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._is_erasing = True
        self._affected_items.clear()
        self._erased_items.clear()
        self._original_paths.clear()
        self._item_refs.clear()
        self._deleted_items.clear()
        self._created_items.clear()
        self._last_erase_pos = event.scenePos()
        if self._cursor_item is not None:
            self._cursor_item.setVisible(True)
            self._cursor_item.update_position(event.scenePos())
        self._erase_at(event.scenePos(), scene)

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        pos = event.scenePos()
        if self._cursor_item is not None:
            self._cursor_item.setVisible(True)
            self._cursor_item.update_position(pos)
        if self._is_erasing:
            self._erase_at(pos, scene)

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._is_erasing = False
        self._last_erase_pos = None
        self.tool_action_completed.emit()

    # ------------------------------------------------------------------
    # Erase logic
    # ------------------------------------------------------------------

    def _erase_at(self, pos: QPointF, scene: PageScene) -> None:
        """Erase items along the path from last position to current position."""
        from PySide6.QtGui import QPainterPathStroker

        # 1. Build a continuous line separating the last mouse tick from the current one
        line_path = QPainterPath()
        if self._last_erase_pos is not None:
            line_path.moveTo(self._last_erase_pos)
            line_path.lineTo(pos)
        else:
            line_path.moveTo(pos)
            line_path.lineTo(pos)
        
        # 2. Thicken this line to the exact width and shape of the eraser radius
        stroker = QPainterPathStroker()
        stroker.setWidth(self._radius * 2)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        eraser_path = stroker.createStroke(line_path)

        # 3. Find candidates colliding with this thick sausage-shape
        candidates = scene.items(eraser_path)
        from items import TextBoxItem
        items = [
            i for i in candidates
            if isinstance(i, self.AFFECTED_ITEM_TYPES)
            and not isinstance(i, TextBoxItem)
        ]

        if items:
            if self._mode == EraserMode.OBJECT:
                self._erase_object_mode(items, scene)
            else:
                self._erase_pixel_mode(items, eraser_path, scene)
        
        # Record new position for next move event
        self._last_erase_pos = pos

    def _erase_object_mode(
        self, items: list[QGraphicsItem], scene: PageScene
    ) -> None:
        """Remove entire items on contact."""
        for item in items:
            if item not in self._erased_items:
                self._erased_items.append(item)
                self._affected_items.append((item, None))
                scene.remove_item_from_registry(item)
                scene.update(item.sceneBoundingRect())
                scene.removeItem(item)

    def _erase_pixel_mode(
        self,
        items: list[QGraphicsItem],
        eraser_path: QPainterPath,
        scene: PageScene,
    ) -> None:
        """Subtract eraser shape from StrokeItem/HighlightItem paths."""
        for item in items:
            if item in self._erased_items:
                continue  # Already fully deleted this drag

            # ShapeItems cannot be partially erased — delete whole item
            if isinstance(item, ShapeItem):
                if item not in self._erased_items:
                    self._erased_items.append(item)
                    self._affected_items.append((item, None))
                    scene.remove_item_from_registry(item)
                    scene.update(item.sceneBoundingRect())
                    scene.removeItem(item)
                continue

            item_id = id(item)

            if isinstance(item, StrokeItem):
                # Convert to outline FIRST, then store original (deep copy)
                item.ensure_outline_mode()
                if item_id not in self._original_paths:
                    copy = QPainterPath()
                    copy.addPath(item.path)
                    self._original_paths[item_id] = copy
                    self._item_refs[item_id] = item

                still_visible = item.subtract_path(eraser_path)
                if not still_visible:
                    self._erased_items.append(item)
                    self._deleted_items.append(item)
                    scene.remove_item_from_registry(item)
                    scene.update(item.sceneBoundingRect())
                    scene.removeItem(item)

            elif isinstance(item, HighlightItem):
                # Store original path ONLY on first encounter (deep copy)
                if item_id not in self._original_paths:
                    copy = QPainterPath()
                    copy.addPath(item.path)
                    self._original_paths[item_id] = copy
                    self._item_refs[item_id] = item

                still_visible = item.subtract_path(eraser_path)
                if not still_visible:
                    self._erased_items.append(item)
                    self._deleted_items.append(item)
                    scene.remove_item_from_registry(item)
                    scene.update(item.sceneBoundingRect())
                    scene.removeItem(item)
                else:
                    # Handle split: create new HighlightItems for extra segments
                    extra_segs = item.pop_extra_segments()
                    orig = self._original_paths[item_id]
                    h_y = orig.boundingRect().center().y()
                    for x_start, x_end in extra_segs:
                        new_path = QPainterPath()
                        new_path.moveTo(QPointF(x_start, h_y))
                        new_path.lineTo(QPointF(x_end, h_y))
                        new_item = HighlightItem(
                            style=item.style,
                            page_index=item.page_index,
                        )
                        new_item.set_path(new_path)
                        scene.addItem(new_item)
                        scene.add_item_to_registry(new_item)
                        self._created_items.append(new_item)

    # ------------------------------------------------------------------
    # Undo/Redo data (Phase 6)
    # ------------------------------------------------------------------

    def get_last_action_data(self) -> list[tuple]:
        """Return deduplicated affected items from the last erase action.

        For object eraser: list of (item, None).
        For pixel eraser: list of (item, original_path) – one entry per item.
        """
        if self._mode == EraserMode.OBJECT:
            return list(self._affected_items)

        # Build deduplicated list for pixel eraser
        result: list[tuple] = []
        deleted_ids = {id(it) for it in self._deleted_items}

        for item_id, orig_path in self._original_paths.items():
            item = self._item_refs.get(item_id)
            if item is None:
                continue
            if item_id in deleted_ids:
                # Fully deleted: pass None as original so command knows
                result.append((item, orig_path))
            else:
                # Modified but still visible
                result.append((item, orig_path))
        return result

    def get_created_items(self) -> list[HighlightItem]:
        """Return new HighlightItems created by highlight splits."""
        return list(self._created_items)
