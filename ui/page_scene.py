"""Graphics scene for PDF pages – arranges all pages vertically and dispatches tool events."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF, Signal, Qt
from PySide6.QtGui import QKeyEvent, QBrush, QColor, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
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
    from PySide6.QtWidgets import QGraphicsItem


class PageScene(
    SceneRegistryMixin,
    SceneClipboardMixin,
    SceneSelectionMixin,
    ScenePageManagerMixin,
    QGraphicsScene,
):
    """QGraphicsScene that holds all PDF pages stacked vertically.

    Uses virtual rendering: pages start as gray placeholders and are
    rendered on demand when they become visible in the viewport.
    Far-away pages are unloaded to conserve memory.

    Functionality is split across mixins:
        SceneRegistryMixin    – per-page item tracking (strokes, highlights, textboxes, shapes)
        SceneClipboardMixin   – copy/cut/paste + serialization
        SceneSelectionMixin   – multi-selection and bounding box overlay
        ScenePageManagerMixin – page reordering, insertion, cloning
    """

    PAGE_GAP: int = 20
    RENDER_DPI: int = 150

    tool_switch_requested = Signal(str)
    selection_changed = Signal()

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)
        self._page_items: list[QGraphicsPixmapItem] = []
        self._page_rects: list[QRectF] = []
        self._page_states: list[str] = []  # "placeholder" or "rendered"
        self._page_y_offsets: list[float] = []  # sorted Y starts for binary search
        self._rendered_set: set[int] = set()  # fast lookup for unload iteration
        self._doc_manager: DocumentManager | None = None
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

        # Shared placeholder pixmap (tiny, gets stretched by item size)
        self._placeholder_pm: QPixmap | None = None

    def _get_placeholder_pixmap(self) -> QPixmap:
        """Return a shared tiny gray placeholder pixmap."""
        if self._placeholder_pm is None:
            self._placeholder_pm = QPixmap(2, 2)
            self._placeholder_pm.fill(QColor("#2a2a2a"))
        return self._placeholder_pm

    def load_document(self, doc_manager: DocumentManager) -> None:
        """Load pages as placeholders (virtual rendering).

        All pages use QGraphicsPixmapItem. Render/unload just swap
        the pixmap content — no scene item add/remove needed.

        Args:
            doc_manager: An open DocumentManager instance.
        """
        self.clear()
        self._page_items.clear()
        self._page_rects.clear()
        self._page_states.clear()
        self._page_y_offsets.clear()
        self._rendered_set.clear()
        self._stroke_items.clear()
        self._highlight_items.clear()
        self._text_box_items.clear()
        self._selected_items.clear()
        self._doc_manager = doc_manager

        # Recreate overlay (self.clear() destroys all scene items)
        self._selection_overlay = SelectionOverlayItem()
        self.addItem(self._selection_overlay)
        self._selection_overlay.setVisible(False)

        page_count = doc_manager.get_page_count()
        if page_count == 0:
            return

        scale = self.RENDER_DPI / 72.0
        y_offset: float = self.PAGE_GAP
        placeholder = self._get_placeholder_pixmap()

        for i in range(page_count):
            w_pt, h_pt = doc_manager.get_page_size(i)
            log_w = w_pt * scale
            log_h = h_pt * scale

            item = QGraphicsPixmapItem(placeholder)
            item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            # Scale the 2px placeholder to fill the logical page size
            item.setScale(log_w / 2.0)
            item.setPos(0, y_offset)
            item.setZValue(0)
            self.addItem(item)

            self._page_items.append(item)
            self._page_rects.append(
                QRectF(0, y_offset, log_w, log_h))
            self._page_states.append("placeholder")
            self._page_y_offsets.append(y_offset)

            y_offset += log_h + self.PAGE_GAP

        # Center all pages horizontally
        self._center_pages()

        # Render first few pages immediately
        self._render_range(0, min(3, page_count - 1))

        # Force viewport repaint (MinimalViewportUpdate won't auto-repaint)
        self.update(self.sceneRect())

    # ------------------------------------------------------------------
    # Virtual rendering
    # ------------------------------------------------------------------

    def _center_pages(self) -> None:
        """Center all pages horizontally based on widest page."""
        if not self._page_items:
            return
        max_w = max(r.width() for r in self._page_rects)
        for i, item in enumerate(self._page_items):
            r = self._page_rects[i]
            x_off = (max_w - r.width()) / 2.0
            item.setPos(x_off, item.pos().y())
            self._page_rects[i] = QRectF(
                x_off, item.pos().y(), r.width(), r.height())

    def _render_page(self, i: int) -> None:
        """Render a single page — just swap pixmap content, no item changes."""
        if self._doc_manager is None:
            return
        if i < 0 or i >= len(self._page_items):
            return
        if self._page_states[i] == "rendered":
            return

        pixmap = self._doc_manager.get_page_pixmap(i, self.RENDER_DPI)
        if pixmap.isNull():
            return

        item = self._page_items[i]
        item.setScale(1.0)  # Reset scale from placeholder
        item.setPixmap(pixmap)
        self._page_states[i] = "rendered"
        self._rendered_set.add(i)

    def _unload_page(self, i: int) -> None:
        """Unload a rendered page — swap pixmap back to tiny placeholder."""
        if self._page_states[i] != "rendered":
            return

        rect = self._page_rects[i]
        item = self._page_items[i]
        item.setPixmap(self._get_placeholder_pixmap())
        item.setScale(rect.width() / 2.0)  # Stretch to page size
        self._page_states[i] = "placeholder"
        self._rendered_set.discard(i)

    def _render_range(self, first: int, last: int) -> None:
        """Render all pages in the given range."""
        for i in range(first, last + 1):
            self._render_page(i)

    def _find_visible_range(self, viewport_rect: QRectF) -> tuple[int, int]:
        """Binary search for the range of pages intersecting viewport_rect.

        Returns (first, last) inclusive, or (-1, -1) if none visible.
        """
        if not self._page_y_offsets:
            return (-1, -1)

        vp_top = viewport_rect.top()
        vp_bottom = viewport_rect.bottom()
        n = len(self._page_y_offsets)

        # Binary search: find first page whose bottom edge >= vp_top
        lo, hi = 0, n - 1
        first = n
        while lo <= hi:
            mid = (lo + hi) // 2
            page_bottom = self._page_y_offsets[mid] + self._page_rects[mid].height()
            if page_bottom >= vp_top:
                first = mid
                hi = mid - 1
            else:
                lo = mid + 1

        if first >= n:
            return (-1, -1)

        # Find last page whose top edge <= vp_bottom
        lo, hi = first, n - 1
        last = first
        while lo <= hi:
            mid = (lo + hi) // 2
            if self._page_y_offsets[mid] <= vp_bottom:
                last = mid
                lo = mid + 1
            else:
                hi = mid - 1

        return (first, last)

    def update_visible_pages(
        self, viewport_rect: QRectF, buffer: int = 2
    ) -> None:
        """Render visible pages and unload far-away pages.

        Uses binary search for O(log n) visible detection.

        Args:
            viewport_rect: The visible area in scene coordinates.
            buffer: Number of extra pages to pre-render above/below.
        """
        if not self._page_states:
            return

        vis_first, vis_last = self._find_visible_range(viewport_rect)
        if vis_first < 0:
            return

        first = max(0, vis_first - buffer)
        last = min(len(self._page_rects) - 1, vis_last + buffer)

        # Render pages in the visible + buffer range
        for i in range(first, last + 1):
            if self._page_states[i] == "placeholder":
                self._render_page(i)

        # Unload far-away rendered pages (iterate only rendered set)
        unload_threshold = buffer + 5
        to_unload = [
            i for i in self._rendered_set
            if i < first - unload_threshold or i > last + unload_threshold
        ]
        for i in to_unload:
            self._unload_page(i)

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
