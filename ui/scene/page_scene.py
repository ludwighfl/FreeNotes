"""Graphics scene for PDF pages – arranges all pages vertically and dispatches tool events."""

from __future__ import annotations

import math

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
from core.tile_cache import TileCache, TileKey, MipLevel
from core.tile_renderer import TileRenderer, TILE_SIZE_PX, MIP_DPI
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.selection_overlay_item import SelectionOverlayItem
from items.bounding_box_handle_manager import BoundingBoxHandleManager
from items.shape_item import ShapeItem

from ui.scene.scene_registry import SceneRegistryMixin
from ui.scene.scene_clipboard import SceneClipboardMixin
from ui.scene.scene_selection import SceneSelectionMixin
from ui.scene.scene_page_manager import ScenePageManagerMixin

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

    Uses tile-based rendering: pages start as gray placeholders and tiles
    are rendered on demand at multiple mip levels (THUMB → MEDIUM → FULL)
    when they become visible in the viewport.  Far-away tiles are evicted
    to conserve memory.

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
        self._image_items: dict[int, list] = {}

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

    def _get_placeholder_pixmap(self) -> QPixmap:
        """Return a shared tiny gray placeholder pixmap."""
        if self._placeholder_pm is None:
            self._placeholder_pm = QPixmap(2, 2)
            self._placeholder_pm.fill(QColor("#2a2a2a"))
        return self._placeholder_pm

    def load_document(self, doc_manager: DocumentManager) -> None:
        """Load pages as placeholders and kick off initial tile rendering.

        All pages use QGraphicsPixmapItem placeholders for layout/hit-testing.
        Actual pixel content is delivered by the tile rendering pipeline.

        Args:
            doc_manager: An open DocumentManager instance.
        """
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

        # Force viewport repaint (MinimalViewportUpdate won't auto-repaint)
        self.update(self.sceneRect())

    # ------------------------------------------------------------------
    # Virtual rendering (tile-based)
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

    def _request_tiles_for_page(
        self,
        page_index: int,
        mip_level: MipLevel,
        area_rect: QRectF,
        doc_path: str,
        priority: int | None = None,
    ) -> None:
        """Compute the tile grid for *page_index* and enqueue tiles that
        intersect *area_rect*.

        Args:
            page_index: Zero-based index of the page.
            mip_level: Resolution level to render at.
            area_rect: Visible area in scene coordinates, **or** the full
                page rect when requesting thumbnails for off-screen pages.
            doc_path: Absolute path to the PDF document.
            priority: Optional explicitly set priority for TileRenderer.
        """
        if page_index < 0 or page_index >= len(self._page_rects):
            return

        page_rect = self._page_rects[page_index]
        page_w = page_rect.width()
        page_h = page_rect.height()

        if page_w <= 0 or page_h <= 0:
            return

        cols = 1 # We span the entire width of the PDF page automatically
        rows = math.ceil(page_h / TILE_SIZE_PX)

        # Viewport center in scene coords — for distance-based priority
        vp_center_x = area_rect.center().x()
        vp_center_y = area_rect.center().y()

        tiles_to_request: list[tuple[float, TileKey]] = []

        for r in range(rows):
            for c in range(cols):
                # Tile rect in scene coordinates
                tile_x = page_rect.x()
                tile_y = page_rect.y() + r * TILE_SIZE_PX
                tile_w = page_w
                tile_h = min(TILE_SIZE_PX, page_h - r * TILE_SIZE_PX)
                tile_scene_rect = QRectF(tile_x, tile_y, tile_w, tile_h)

                if not tile_scene_rect.intersects(area_rect):
                    continue

                # Distance to viewport center (lower = higher priority)
                tile_cx = tile_scene_rect.center().x()
                tile_cy = tile_scene_rect.center().y()
                dist = math.hypot(tile_cx - vp_center_x, tile_cy - vp_center_y)

                has_thumb = (
                    self._tile_cache.contains(TileKey(page_index, c, r, MipLevel.THUMB)) or
                    TileKey(page_index, c, r, MipLevel.THUMB) in self._pending_tiles
                )
                has_medium = (
                    self._tile_cache.contains(TileKey(page_index, c, r, MipLevel.MEDIUM)) or
                    TileKey(page_index, c, r, MipLevel.MEDIUM) in self._pending_tiles
                )
                has_full = (
                    self._tile_cache.contains(TileKey(page_index, c, r, MipLevel.FULL)) or
                    TileKey(page_index, c, r, MipLevel.FULL) in self._pending_tiles
                )
                has_any = has_thumb or has_medium or has_full

                mips_to_request = []
                # If no tile exists for this position, always request THUMB first
                if not has_any:
                    mips_to_request.append(MipLevel.THUMB)

                # Then enqueue progressively higher mips up to the target mip_level
                if mip_level >= MipLevel.MEDIUM and not has_medium:
                    mips_to_request.append(MipLevel.MEDIUM)
                if mip_level >= MipLevel.FULL and not has_full:
                    mips_to_request.append(MipLevel.FULL)
                if mip_level == MipLevel.THUMB and not has_thumb and has_any:
                    mips_to_request.append(MipLevel.THUMB)

                for m in mips_to_request:
                    key = TileKey(page_index, c, r, m)
                    if not self._tile_cache.contains(key) and key not in self._pending_tiles:
                        tiles_to_request.append((dist, key))

        # Sort by mip level first (ensuring all THUMBs are requested before FULLs),
        # then by distance to viewport center
        tiles_to_request.sort(key=lambda t: (t[1].mip_level, t[0]))

        for _dist, key in tiles_to_request:
            self._pending_tiles.add(key)
            orig_idx = -1
            if self._doc_manager and key.page_index < len(self._doc_manager.page_map):
                orig_idx = self._doc_manager.page_map[key.page_index]
                
            self._tile_renderer.request_tile(
                key,
                page_rect,
                doc_path,
                priority,
                orig_page_idx=orig_idx,
                is_cancelled=lambda k=key: k not in self._pending_tiles
            )

    def _on_tile_ready(self, key: TileKey) -> None:
        """Called on main thread when a tile has been rendered and cached."""
        self._pending_tiles.discard(key)

        image = self._tile_cache.get(key)
        if image is None or image.isNull():
            return
            
        # GPU upload occurs safely on the native GUI thread
        pixmap = QPixmap.fromImage(image)

        # Validate page index is still in range (crucial if back navigation clears scene)
        if key.page_index < 0 or key.page_index >= len(self._page_rects):
            return

        # Create or update the tile item for this key
        item = self._tile_items.get(key)
        if item is None:
            item = QGraphicsPixmapItem()
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            item.setZValue(0)

            # Position tile correctly in scene coordinates
            page_rect = self._page_rects[key.page_index]
            x = page_rect.x() # full width tile
            y = page_rect.y() + key.tile_row * TILE_SIZE_PX
            item.setPos(x, y)

            self.addItem(item)
            self._tile_items[key] = item

        item.setPixmap(pixmap)
        item.setVisible(True)

        # Hide lower-quality tiles for the same position now that
        # a higher-quality tile is available
        if key.mip_level == MipLevel.FULL:
            medium_key = TileKey(key.page_index, key.tile_col, key.tile_row, MipLevel.MEDIUM)
            thumb_key  = TileKey(key.page_index, key.tile_col, key.tile_row, MipLevel.THUMB)
            for lower_key in (medium_key, thumb_key):
                lower_item = self._tile_items.get(lower_key)
                if lower_item is not None:
                    lower_item.setVisible(False)
        elif key.mip_level == MipLevel.MEDIUM:
            thumb_key = TileKey(key.page_index, key.tile_col, key.tile_row, MipLevel.THUMB)
            thumb_item = self._tile_items.get(thumb_key)
            if thumb_item is not None:
                thumb_item.setVisible(False)

        # Repaint only the affected tile region, not the whole scene
        page_rect = self._page_rects[key.page_index]
        tile_scene_rect = QRectF(
            page_rect.x() + key.tile_col * TILE_SIZE_PX,
            page_rect.y() + key.tile_row * TILE_SIZE_PX,
            TILE_SIZE_PX,
            TILE_SIZE_PX,
        ).intersected(page_rect)
        self.update(tile_scene_rect)

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
        """Request tiles for visible pages and manage tile lifecycle.

        Uses binary search for O(log n) visible detection.

        Args:
            viewport_rect: The visible area in scene coordinates.
            buffer: Number of extra pages to pre-render above/below.
        """
        if not self._page_rects:
            return

        vis_first, vis_last = self._find_visible_range(viewport_rect)
        if vis_first < 0:
            return

        doc_path = self._doc_manager.get_doc_path() if self._doc_manager else None
        if not doc_path:
            return

        n = len(self._page_rects)

        # --- 1. Visible pages: request FULL + MEDIUM for visible tile area ---
        for i in range(vis_first, vis_last + 1):
            page_rect = self._page_rects[i]
            visible_tile_area = viewport_rect.intersected(page_rect)
            if visible_tile_area.isEmpty():
                continue
            self._request_tiles_for_page(i, MipLevel.FULL,   visible_tile_area, doc_path)
            self._request_tiles_for_page(i, MipLevel.MEDIUM, visible_tile_area, doc_path)

        # --- 2. Pre-render buffer pages: MEDIUM only, full page rect ---
        pre_first = max(0, vis_first - buffer)
        pre_last  = min(n - 1, vis_last + buffer)

        for i in range(pre_first, vis_first):
            page_rect = self._page_rects[i]
            self._request_tiles_for_page(i, MipLevel.MEDIUM, page_rect, doc_path)

        for i in range(vis_last + 1, pre_last + 1):
            page_rect = self._page_rects[i]
            self._request_tiles_for_page(i, MipLevel.MEDIUM, page_rect, doc_path)

        # --- 3. THUMB for all pages (entire document, lowest priority) ---
        # Only request if not already cached — provides instant scroll preview
        # for pages far away. Uses priority 10 so it never blocks visible tiles.
        THUMB_LOOKAHEAD = 10  # pages beyond the buffer zone
        thumb_first = max(0, vis_first - buffer - THUMB_LOOKAHEAD)
        thumb_last  = min(n - 1, vis_last + buffer + THUMB_LOOKAHEAD)

        for i in range(thumb_first, thumb_last + 1):
            page_rect = self._page_rects[i]
            self._request_tiles_for_page(
                i, MipLevel.THUMB, page_rect, doc_path, priority=10)

        # --- 4. Evict FULL tiles for far-away pages ---
        evict_threshold = buffer + 5
        for key, item in list(self._tile_items.items()):
            if key.mip_level == MipLevel.FULL:
                distance = abs(key.page_index - vis_first)
                if distance > evict_threshold:
                    self.removeItem(item)
                    del self._tile_items[key]
                    # Do not remove from cache — L1 cache handles its own eviction

        # Cancel pending tasks for evicted pages
        self._pending_tiles = {
            k for k in self._pending_tiles
            if abs(k.page_index - vis_first) <= evict_threshold
        }

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
            # Check if click is NOT on a TextBoxItem (or its handles)
            items_at = self.items(
                QRectF(
                    event.scenePos().x() - 2,
                    event.scenePos().y() - 2,
                    4,
                    4,
                )
            )
            has_textbox = False
            for i in items_at:
                if isinstance(i, TextBoxItem):
                    has_textbox = True
                    break
                if hasattr(i, "parentItem") and isinstance(i.parentItem(), TextBoxItem):
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

    # ------------------------------------------------------------------
    # Action Handlers
    # ------------------------------------------------------------------

    def insert_image_from_file_dialog(self, pos: QPointF | None = None) -> None:
        """Open a file dialog to select an image, then insert it at the given pos or center."""
        from PySide6.QtWidgets import QFileDialog
        import os

        # Use the first view to get a parent widget for the dialog
        views = self.views()
        parent_widget = views[0] if views else None

        file_path, _ = QFileDialog.getOpenFileName(
            parent_widget,
            "Bild einfügen",
            "",
            "Bilder (*.png *.jpg *.jpeg *.webp);;Alle Dateien (*.*)"
        )

        if not file_path or not os.path.exists(file_path):
            return

        from app.app_state import AppState
        page_idx = -1

        if pos is None:
            # Drop at center of current page
            page_idx = AppState().current_page
            page_rect = self.get_page_rect(page_idx)
            if not page_rect.isEmpty():
                pos = QPointF(page_rect.center().x(), page_rect.top() + 50)
            else:
                pos = QPointF(100, 100)
        else:
            page_idx = self.get_page_index_at(pos)
            if page_idx < 0:
                page_idx = AppState().current_page

        try:
            from items.image_item import ImageItem
            item = ImageItem.from_image_file(file_path, pos, page_idx)
            
            # Scale down large images
            page_rect = self.get_page_rect(page_idx)
            if not page_rect.isEmpty() and item._rect.width() > page_rect.width() * 0.8:
                scale = (page_rect.width() * 0.8) / item._rect.width()
                new_w = item._rect.width() * scale
                new_h = item._rect.height() * scale
                from PySide6.QtCore import QRectF
                item.set_rect(QRectF(pos.x(), pos.y(), new_w, new_h))
                
            self.addItem(item)
            self.add_item_to_registry(item)

            # Push undo command
            from commands.paste_items_command import PasteItemsCommand
            from core import undo_stack
            cmd = PasteItemsCommand([item], self)
            undo_stack.push(cmd)

            # Select dropped items
            self.set_selection([item])

            # Auto-switch to hand tool
            self.tool_switch_requested.emit("hand")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Image insert failed: %s", e)
