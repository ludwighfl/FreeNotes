"""Graphics scene for PDF pages – arranges all pages vertically and dispatches tool events."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF, Signal, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsSceneMouseEvent,
)

from core.document_manager import DocumentManager
from core import undo_stack
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.selection_overlay_item import SelectionOverlayItem
from items.bounding_box_handle_manager import BoundingBoxHandleManager
from items.shape_item import ShapeItem

from ui.scene_registry import SceneRegistryMixin
from ui.scene_clipboard import SceneClipboardMixin
from ui.scene_selection import SceneSelectionMixin
from ui.scene_page_manager import ScenePageManagerMixin

# TYPE_CHECKING import to avoid circular dependency
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.base_tool import BaseTool


class PageScene(
    SceneRegistryMixin,
    SceneClipboardMixin,
    SceneSelectionMixin,
    ScenePageManagerMixin,
    QGraphicsScene,
):
    """QGraphicsScene that holds all PDF pages stacked vertically.

    Each page is a QGraphicsPixmapItem placed below the previous one
    with a 20px gap between pages. Supports HiDPI pixmaps via
    devicePixelRatio – layout uses logical sizes.

    Also dispatches mouse events to the active tool for drawing.

    Functionality is split across mixins:
        SceneRegistryMixin    – per-page item tracking (strokes, highlights, textboxes, shapes)
        SceneClipboardMixin   – copy/cut/paste + serialization
        SceneSelectionMixin   – multi-selection and bounding box overlay
        ScenePageManagerMixin – page reordering, insertion, cloning
    """

    PAGE_GAP: int = 20

    tool_switch_requested = Signal(str)
    selection_changed = Signal()

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)
        self._page_items: list[QGraphicsPixmapItem] = []
        self._page_rects: list[QRectF] = []
        self._active_tool: BaseTool | None = None
        self._stroke_items: dict[int, list[StrokeItem]] = {}
        self._highlight_items: dict[int, list[HighlightItem]] = {}
        self._text_box_items: dict[int, list[TextBoxItem]] = {}
        self._shape_items: dict[int, list] = {}

        # Disable BSP tree for dynamic item compatibility (fixes zoom ghosts)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        # Central selection state (used by SceneSelectionMixin)
        self._selected_items: set = set()
        self._selection_overlay: SelectionOverlayItem = SelectionOverlayItem()
        self.addItem(self._selection_overlay)
        self._selection_overlay.setVisible(False)

        # Bounding box resize handles
        self._bbox_handle_manager = BoundingBoxHandleManager(self)
        self.selection_changed.connect(self._on_selection_changed)

    def load_document(self, doc_manager: DocumentManager) -> None:
        """Load all pages from the document manager into the scene.

        Args:
            doc_manager: An open DocumentManager instance.
        """
        self.clear()
        self._page_items.clear()
        self._page_rects.clear()
        self._stroke_items.clear()
        self._highlight_items.clear()
        self._text_box_items.clear()
        self._selected_items.clear()

        # Recreate overlay (self.clear() destroys all scene items)
        self._selection_overlay = SelectionOverlayItem()
        self.addItem(self._selection_overlay)
        self._selection_overlay.setVisible(False)

        page_count = doc_manager.get_page_count()
        if page_count == 0:
            return

        y_offset: float = self.PAGE_GAP

        for i in range(page_count):
            pixmap = doc_manager.get_page_pixmap(i)
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

            # Use logical size for layout (accounts for devicePixelRatio)
            dpr = pixmap.devicePixelRatio()
            logical_w = pixmap.width() / dpr
            logical_h = pixmap.height() / dpr

            item.setPos(0, y_offset)
            self._page_items.append(item)
            self.addItem(item)

            page_rect = QRectF(0, y_offset, logical_w, logical_h)
            self._page_rects.append(page_rect)

            y_offset += logical_h + self.PAGE_GAP

        # Center all pages horizontally
        if self._page_items:
            max_width = max(
                item.pixmap().width() / item.pixmap().devicePixelRatio()
                for item in self._page_items
            )
            for i, item in enumerate(self._page_items):
                pix = item.pixmap()
                logical_w = pix.width() / pix.devicePixelRatio()
                logical_h = pix.height() / pix.devicePixelRatio()
                x_offset = (max_width - logical_w) / 2.0
                item.setPos(x_offset, item.pos().y())
                self._page_rects[i] = QRectF(
                    x_offset, item.pos().y(), logical_w, logical_h
                )

    # ------------------------------------------------------------------
    # Tool management
    # ------------------------------------------------------------------

    def set_tool(self, tool: BaseTool) -> None:
        """Set the active tool, deactivating any previous tool.

        Args:
            tool: The new tool to activate.
        """
        if self._active_tool is not None:
            self._active_tool.deactivate(self)
        self._active_tool = tool
        if self._active_tool is not None:
            self._active_tool.activate(self)

    @property
    def active_tool(self) -> BaseTool | None:
        """Return the currently active tool."""
        return self._active_tool

    # ------------------------------------------------------------------
    # Mouse event dispatch to active tool
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Dispatch press to active tool, then call super."""
        # Deselect all textboxes when clicking empty space with non-text tool
        from tools.text_tool import TextTool

        if not isinstance(self._active_tool, TextTool):
            # Check if click is NOT on a TextBoxItem
            items_at = self.items(
                QRectF(
                    event.scenePos().x() - 2,
                    event.scenePos().y() - 2,
                    4,
                    4,
                )
            )
            has_textbox = any(isinstance(i, TextBoxItem) for i in items_at)
            if not has_textbox:
                self.deselect_all_textboxes()

        if self._active_tool is not None:
            self._active_tool.on_press(event, self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Dispatch move to active tool, then call super."""
        if self._active_tool is not None:
            self._active_tool.on_move(event, self)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Dispatch release to active tool, then call super."""
        if self._active_tool is not None:
            self._active_tool.on_release(event, self)
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key events: forward to editing TextBox, Escape, Delete, Copy, Paste."""
        # Forward to editing TextBox if one has focus
        focus = self.focusItem()
        if isinstance(focus, TextBoxItem) and focus._is_editing:
            focus.keyPressEvent(event)
            event.accept()
            return

        from PySide6.QtGui import QKeySequence
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Cut):
            self.cut_selected()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste_clipboard()
            event.accept()
            return

        key = event.key()

        # Escape: deselect all textboxes and selections
        if key == Qt.Key.Key_Escape:
            self.deselect_all_textboxes()
            self.clear_selection()
            event.accept()
            return

        # Delete/Backspace: delete selected items globally
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            event.accept()
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Page queries
    # ------------------------------------------------------------------

    def get_page_rect(self, page_index: int) -> QRectF:
        """Return the bounding rectangle of a specific page in scene coords.

        Args:
            page_index: Zero-based page index.

        Returns:
            QRectF of the page, or an empty QRectF if index is out of range.
        """
        if 0 <= page_index < len(self._page_rects):
            return self._page_rects[page_index]
        return QRectF()

    def get_page_index_at(self, scene_pos: QPointF) -> int:
        """Determine which page contains the given scene position.

        Args:
            scene_pos: A position in scene coordinates.

        Returns:
            Zero-based page index, or -1 if outside all pages.
        """
        for i, rect in enumerate(self._page_rects):
            if rect.contains(scene_pos):
                return i
        return -1

    @property
    def page_count(self) -> int:
        """Number of pages currently in the scene."""
        return len(self._page_items)

    # ------------------------------------------------------------------
    # Eraser cursor visibility
    # ------------------------------------------------------------------

    def set_eraser_cursor_visible(self, visible: bool) -> None:
        """Show/hide the eraser cursor item if the active tool is an eraser."""
        from tools.eraser_tool import EraserTool
        if isinstance(self._active_tool, EraserTool):
            if self._active_tool._cursor_item is not None:
                self._active_tool._cursor_item.setVisible(visible)

    def get_ephemeral_items(self) -> list:
        """Return a list of UI graphics items that shouldn't be rendered in exporting or thumbnails."""
        items = []

        # Active tool cursor (e.g. eraser circle)
        from tools.eraser_tool import EraserTool
        if isinstance(self._active_tool, EraserTool):
            if self._active_tool._cursor_item is not None:
                try:
                    if self._active_tool._cursor_item.isVisible():
                        items.append(self._active_tool._cursor_item)
                except RuntimeError:
                    pass

        # TextBox selection frames are handled in their respective paint methods dynamically.

        return items
