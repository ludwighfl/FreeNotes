"""Highlighter tool – draws Y-locked semitransparent strokes over PDF text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QObject
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from app.app_state import AppState
from core.tool_style import ToolStyle
from items.highlight_item import HighlightItem
from tools.base_tool import BaseTool

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class HighlighterTool(BaseTool):
    """Highlighter tool: draws horizontal, semitransparent path strokes.

    Y-coordinate is locked on press – only X changes during drag.
    Strokes use RoundCap/RoundJoin and fixed 0.35 opacity.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_item: HighlightItem | None = None
        self._last_completed_item: HighlightItem | None = None

    @property
    def last_completed_item(self) -> HighlightItem | None:
        """The most recently completed HighlightItem (set after on_release)."""
        return self._last_completed_item

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    def activate(self, scene: PageScene) -> None:
        for view in scene.views():
            view.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self, scene: PageScene) -> None:
        if self._current_item is not None:
            self._current_item.finish()
            self._current_item = None
        for view in scene.views():
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()

        # Skip if clicking on a TextBox
        from items import TextBoxItem
        from PySide6.QtCore import QRectF as _QRF
        items_at = scene.items(_QRF(pos.x() - 2, pos.y() - 2, 4, 4))
        if any(isinstance(i, TextBoxItem) for i in items_at):
            return

        page_index = scene.get_page_index_at(pos)
        if page_index < 0:
            return

        app_style = AppState().tool_style
        style = ToolStyle(
            color=app_style.color,
            width=app_style.width,
            opacity=0.35,
            tool_type="highlighter",
        )

        self._current_item = HighlightItem(style, page_index)
        scene.addItem(self._current_item)
        scene.add_highlight_item(self._current_item, page_index)
        self._current_item.start(pos)

    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if self._current_item is None:
            return
        self._current_item.extend(event.scenePos())

    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._current_item is None:
            return
        self._current_item.finish()
        self._last_completed_item = self._current_item
        self._current_item = None
        self.tool_action_completed.emit()
