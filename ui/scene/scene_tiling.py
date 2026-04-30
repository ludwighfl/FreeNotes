"""Mixin for PageScene to handle tile-based virtual rendering."""

from __future__ import annotations

import math
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPixmap 
from PySide6.QtWidgets import QGraphicsPixmapItem

from core.tile_cache import TileKey, MipLevel
from core.tile_renderer import TILE_SIZE_PX

# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class SceneTilingMixin:
    """Handles async chunked/tiled rendering of PDF pages based on viewport visibility."""

    def _find_visible_range(self: 'PageScene', viewport_rect: QRectF) -> tuple[int, int]:
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

    def _request_tiles_for_page(
        self: 'PageScene',
        page_index: int,
        mip_level: MipLevel,
        area_rect: QRectF,
        doc_path: str,
        priority: int | None = None,
    ) -> None:
        """Compute the tile grid for *page_index* and enqueue tiles that intersect *area_rect*."""
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

        # --- Batch cache lookup: acquire lock once instead of per-tile ---
        all_keys_to_check: list[TileKey] = []
        tile_positions: list[tuple[float, int, int, QRectF]] = []

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
                tile_positions.append((dist, c, r, tile_scene_rect))

                for m in MipLevel:
                    all_keys_to_check.append(TileKey(page_index, c, r, m))

        cached_keys = self._tile_cache.contains_batch(all_keys_to_check)

        for dist, c, r, tile_scene_rect in tile_positions:
            has_thumb = (
                TileKey(page_index, c, r, MipLevel.THUMB) in cached_keys or
                TileKey(page_index, c, r, MipLevel.THUMB) in self._pending_tiles
            )
            has_medium = (
                TileKey(page_index, c, r, MipLevel.MEDIUM) in cached_keys or
                TileKey(page_index, c, r, MipLevel.MEDIUM) in self._pending_tiles
            )
            has_full = (
                TileKey(page_index, c, r, MipLevel.FULL) in cached_keys or
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
                if key in cached_keys:
                    # Tile is cached — ensure it has a scene item
                    if key not in self._tile_items:
                        self._on_tile_ready(key)
                elif key not in self._pending_tiles:
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

    def _on_tile_ready(self: 'PageScene', key: TileKey) -> None:
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

        self._suppress_scene_changed = True
        try:
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

            # scene.changed → sidebar thumbnail invalidation for tile updates.
            # Note: QGraphicsPixmapItem.setPixmap automatically schedules a repaint.
        finally:
            self._suppress_scene_changed = False

    def update_visible_pages(
        self: 'PageScene', viewport_rect: QRectF, buffer: int = 2
    ) -> None:
        """Request tiles for visible pages and manage tile lifecycle."""
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
        keys_to_evict: list[TileKey] = [
            key for key in self._tile_items
            if key.mip_level == MipLevel.FULL
            and abs(key.page_index - vis_first) > evict_threshold
        ]
        for key in keys_to_evict:
            item = self._tile_items.pop(key)
            self.removeItem(item)

            # Unhide lower mips so they act as placeholders if we scroll back
            medium_key = TileKey(key.page_index, key.tile_col, key.tile_row, MipLevel.MEDIUM)
            thumb_key = TileKey(key.page_index, key.tile_col, key.tile_row, MipLevel.THUMB)

            if medium_key in self._tile_items:
                self._tile_items[medium_key].setVisible(True)
            elif thumb_key in self._tile_items:
                self._tile_items[thumb_key].setVisible(True)
            # Do not remove from cache — L1 cache handles its own eviction

        # Cancel pending tasks for evicted pages (preserve THUMB lookahead tasks)
        self._pending_tiles = {
            k for k in self._pending_tiles
            if abs(k.page_index - vis_first) <= evict_threshold
            or (k.mip_level == MipLevel.THUMB and abs(k.page_index - vis_first) <= buffer + THUMB_LOOKAHEAD)
        }
