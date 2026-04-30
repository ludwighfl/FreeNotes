"""Graphics scene for PDF pages – arranges all pages vertically and dispatches tool events."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QPointF, Signal, Qt
from PySide6.QtGui import QKeyEvent, QColor, QPixmap, QPainter
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsSceneMouseEvent,
)

from core.document_manager import DocumentManager
from core.tile_cache import TileCache, TileKey, MipLevel
from core.tile_renderer import TileRenderer
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.selection_overlay_item import SelectionOverlayItem
from items.bounding_box_handle_manager import BoundingBoxHandleManager

from ui.scene.scene_registry import SceneRegistryMixin
from ui.scene.scene_clipboard import SceneClipboardMixin
from ui.scene.scene_selection import SceneSelectionMixin
from ui.scene.scene_page_manager import ScenePageManagerMixin
from ui.scene.scene_tiling import SceneTilingMixin
from ui.scene.scene_image_manager import SceneImageManagerMixin

# TYPE_CHECKING import to avoid circular dependency
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.base_tool import BaseTool


class PageScene(
    SceneRegistryMixin,
    SceneClipboardMixin,
    SceneSelectionMixin,
    ScenePageManagerMixin,
    SceneTilingMixin,
    SceneImageManagerMixin,
    QGraphicsScene,
):
    """QGraphicsScene that holds all PDF pages stacked vertically.

    Uses tile-based rendering: pages start as gray placeholders and tiles
    are rendered on demand at multiple mip levels (THUMB → MEDIUM → FULL)
    when they become visible in the viewport.

    Functionality is heavily split across mixins:
        SceneRegistryMixin     – per-page item tracking
        SceneClipboardMixin    – copy/cut/paste + serialization
        SceneSelectionMixin    – multi-selection and bounding box overlay
        ScenePageManagerMixin  – page reordering, insertion, cloning
        SceneTilingMixin       – rendering logic and tile lifecycle
        SceneImageManagerMixin – image dropping handling
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
        self._image_items: dict[int, list] = {}

        # Enable BSP tree for high performance with mass annotations (O(log N))
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)

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

        # --- Tile rendering system ---
        self._tile_cache: TileCache = TileCache()
        self._tile_renderer: TileRenderer = TileRenderer(self._tile_cache)
        self._tile_renderer.tile_ready.connect(self._on_tile_ready)

        # Maps TileKey → QGraphicsPixmapItem in the scene
        self._tile_items: dict[TileKey, QGraphicsPixmapItem] = {}

        # Tracks which tiles have been requested to avoid duplicate requests
        self._pending_tiles: set[TileKey] = set()

        # Current mip level based on zoom (updated by PageView)
        self._current_mip: MipLevel = MipLevel.MEDIUM

        # Flags used by sidebar and thumbnail rendering to suppress signals
        self._suppress_scene_changed: bool = False
        self._is_rendering_thumbnail: bool = False

    def _get_placeholder_pixmap(self) -> QPixmap:
        """Return a shared tiny gray placeholder pixmap."""
        if self._placeholder_pm is None:
            self._placeholder_pm = QPixmap(2, 2)
            self._placeholder_pm.fill(QColor("#2a2a2a"))
        return self._placeholder_pm

    def load_document(self, doc_manager: DocumentManager) -> None:
        """Load pages as placeholders and kick off initial tile rendering."""
        # --- Cancel / clear tile system ---
        self._tile_renderer.cancel_all()
        self._tile_cache.invalidate_all()

        # Tile items will be destroyed by self.clear() below — just drop refs
        self._tile_items.clear()
        self._pending_tiles.clear()

        self.clear()
        self._page_items.clear()
        self._page_rects.clear()
        self._page_states.clear()
        self._page_y_offsets.clear()
        self._rendered_set.clear()
        self._stroke_items.clear()
        self._highlight_items.clear()
        self._text_box_items.clear()
        self._shape_items.clear()
        self._image_items.clear()
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
            # Scale the 2px placeholder to fill the logical page size exactly
            from PySide6.QtGui import QTransform
            transform = QTransform()
            transform.scale(log_w / 2.0, log_h / 2.0)
            item.setTransform(transform)
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

        # Request THUMB tiles for the first few pages immediately
        doc_path = doc_manager.get_doc_path()
        if doc_path:
            initial_count = min(5, page_count)
            for i in range(initial_count):
                page_rect = self._page_rects[i]
                self._request_tiles_for_page(i, MipLevel.THUMB, page_rect, doc_path)

            # Pre-render first 10 pages at MEDIUM resolution in background
            for i in range(min(10, page_count)):
                page_rect = self._page_rects[i]
                self._request_tiles_for_page(
                    i, MipLevel.MEDIUM, page_rect, doc_path, priority=5)

        # Views will repaint on their own via MinimalViewportUpdate +
        # tile_ready callbacks — no full-scene invalidation needed.

    # ------------------------------------------------------------------
    # Virtual rendering bounds logic
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
                
        # Explicitly set scene rect so Scrollbars update accurately and shrink!
        # Because QGraphicsScene NEVER shrinks its rect automatically.
        if self._page_rects:
            max_y = max(r.bottom() for r in self._page_rects) + self.PAGE_GAP
            self.setSceneRect(0, 0, max_w, max_y)
        else:
            self.setSceneRect(0, 0, 0, 0)

    def _render_page(self, i: int) -> None:
        """Replaced by tile rendering — see _request_tiles_for_page()."""
        pass

    def _unload_page(self, i: int) -> None:
        """Replaced by tile rendering — see update_visible_pages()."""
        pass

    def _render_range(self, first: int, last: int) -> None:
        """Replaced by tile rendering — see _request_tiles_for_page()."""
        pass

    # ------------------------------------------------------------------
    # Overlay rendering for active drawing tools (Bypass BSP Tree Lag)
    # ------------------------------------------------------------------

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Render active strokes directly to the viewport to bypass BSP tree lag."""
        super().drawForeground(painter, rect)
        if self._active_tool and hasattr(self._active_tool, "draw_active_stroke"):
            self._active_tool.draw_active_stroke(painter, rect)

    # ------------------------------------------------------------------
    # Tool management
    # ------------------------------------------------------------------

    def set_tool(self, tool: BaseTool) -> None:
        """Set the active tool, deactivating any previous tool.
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
            # Check if click is NOT on a TextBoxItem (or its handles) via registry
            pos = event.scenePos()
            page_idx = self.get_page_index_at(pos)
            has_textbox = False
            
            if page_idx >= 0:
                rect = QRectF(pos.x() - 2, pos.y() - 2, 4, 4)
                for box in self.get_textboxes_for_page(page_idx):
                    if box.sceneBoundingRect().intersects(rect):
                        has_textbox = True
                        break

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

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double clicks on items like text boxes in selection mode."""
        super().mouseDoubleClickEvent(event)
        
        # Tools might override double click behavior
        if self._active_tool is not None:
            self._active_tool.on_double_click(event, self)

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
        """Return the bounding rectangle of a specific page in scene coords."""
        if 0 <= page_index < len(self._page_rects):
            return self._page_rects[page_index]
        return QRectF()

    def get_page_index_at(self, scene_pos: QPointF) -> int:
        """Determine which page contains the given scene position.

        Uses binary search over page Y-offsets for O(log n) performance
        instead of linear scan, critical for documents with many pages.
        """
        if not self._page_rects:
            return -1

        y = scene_pos.y()
        x = scene_pos.x()

        # Binary search: find the page whose top <= y
        lo, hi = 0, len(self._page_rects) - 1
        result = -1
        while lo <= hi:
            mid = (lo + hi) // 2
            rect = self._page_rects[mid]
            if rect.top() <= y:
                result = mid
                lo = mid + 1
            else:
                hi = mid - 1

        # Check if the found page actually contains the point
        if result >= 0:
            rect = self._page_rects[result]
            if rect.contains(scene_pos):
                return result
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

        return items
