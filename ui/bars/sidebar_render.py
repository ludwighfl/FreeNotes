"""Mixin handling thumbnail lazy loading, worker threads, and overlay painting."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter

from core.thumbnail_worker import ThumbnailWorker

# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.bars.sidebar_widget import SidebarWidget


class SidebarRenderMixin:
    """Handles rendering operations, scene changes, and lazy loaded thumbnails."""

    # Minimum interval between processing scene.changed signals (seconds)
    _SCENE_CHANGED_COOLDOWN: float = 0.2

    def _on_scene_changed(self: 'SidebarWidget', rects: list) -> None:
        """Invalidate thumbnails that overlap with the changed area.

        Uses binary search on page Y-offsets to find affected pages in
        O(rects × log pages) instead of O(rects × pages).  All actual
        re-rendering is deferred to the existing debounced _lazy_timer.

        A 200ms cooldown prevents re-processing during rapid-fire updates
        (scroll, zoom, hover).  Small rects (< 100 px²) from cursor blinks
        and handle hovers are skipped entirely.
        """
        if self._scene is None or not self._cards:
            return
        if getattr(self._scene, '_is_rendering_thumbnail', False):
            return
        if getattr(self._scene, '_suppress_scene_changed', False):
            return

        # Cooldown: skip if called too recently
        now = time.monotonic()
        if now - getattr(self, '_last_scene_changed_time', 0.0) < self._SCENE_CHANGED_COOLDOWN:
            # Ensure a deferred check fires after the cooldown expires
            if not self._lazy_timer.isActive():
                self._lazy_timer.start()
            return

        page_rects = self._scene._page_rects
        n = len(page_rects)
        if n == 0:
            return

        dirty = False
        for rect in rects:
            # Skip tiny rects (cursor blinks, handle hovers, etc.)
            if rect.width() * rect.height() < 100.0:
                continue

            # Binary search for first page whose bottom >= rect.top
            lo, hi = 0, n - 1
            start = n
            while lo <= hi:
                mid = (lo + hi) // 2
                if page_rects[mid].bottom() >= rect.top():
                    start = mid
                    hi = mid - 1
                else:
                    lo = mid + 1

            # Walk forward from start until page.top > rect.bottom
            for i in range(start, n):
                if page_rects[i].top() > rect.bottom():
                    break
                if rect.intersects(page_rects[i]):
                    self._loaded_pages.discard(i)
                    self._queued_pages.discard(i)
                    dirty = True

        if dirty:
            self._last_scene_changed_time = now
            self._lazy_timer.start()

    def invalidate_thumb(self: 'SidebarWidget', page_idx: int) -> None:
        """Mark a thumbnail as needing re-render. Re-renders if visible."""
        self._loaded_pages.discard(page_idx)
        self._queued_pages.discard(page_idx)
        self._lazy_timer.start()

    def _load_visible_thumbnails(self: 'SidebarWidget') -> None:
        """Load thumbnails for visible cards + 2 buffer pages.

        Uses doc_manager.get_page_pixmap(dpi=36, use_hidpi=False) directly instead of
        scene.render() to avoid capturing gray placeholders from virtual
        rendering.
        """
        if self._doc_manager is None or not self._cards:
            return

        if self._thumb_worker is not None:
            worker_ref = self._thumb_worker
            self._thumb_worker = None
            try:
                worker_ref.cancel()
                for current_idx, _ in worker_ref._tasks:
                    self._queued_pages.discard(current_idx)
                # Keep python reference alive until C++ thread exits natively
                self._zombie_workers.add(worker_ref)
                worker_ref.finished.connect(lambda w=worker_ref: self._zombie_workers.discard(w))
            except RuntimeError:
                pass

        viewport_rect = self.viewport().rect()
        buffer = 2

        first_visible = -1
        last_visible = -1

        vp_global = self.viewport().mapToGlobal(QPoint(0, 0))

        for i, card in enumerate(self._cards):
            card_global = card.mapToGlobal(QPoint(0, 0))
            rel = card_global - vp_global
            card_rect = card.rect().translated(rel.x(), rel.y())
            if viewport_rect.intersects(card_rect):
                if first_visible == -1:
                    first_visible = i
                last_visible = i

        if first_visible == -1:
            first_visible = 0
            last_visible = min(4, len(self._cards) - 1)

        start = max(0, first_visible - buffer)
        end = min(len(self._cards) - 1, last_visible + buffer)

        indices = [i for i in range(start, end + 1) 
                   if i not in self._loaded_pages and i not in self._queued_pages]
        if not indices:
            return

        tasks = []
        for i in indices:
            self._queued_pages.add(i)
            orig_idx = self._doc_manager.page_map[i] if i < len(self._doc_manager.page_map) else -1
            tasks.append((i, orig_idx))

        self._thumb_generation_id += 1
        self._thumb_worker = ThumbnailWorker(
            self._doc_manager, tasks, self.THUMBNAIL_DPI, False, self._thumb_generation_id
        )
        self._thumb_worker.finished.connect(self._thumb_worker.deleteLater)
        self._thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._thumb_worker.start()

    def _on_thumbnail_ready(self: 'SidebarWidget', gen_id: int, idx: int, img: QImage) -> None:
        self._queued_pages.discard(idx)
        
        if gen_id != self._thumb_generation_id:
            return
            
        if idx < len(self._cards) and not img.isNull():
            self._loaded_pages.add(idx)
            pixmap = QPixmap.fromImage(img)
            
            # --- Overlay Annotations (direct item painting) ---
            if self._scene is not None and idx < len(self._scene._page_items):
                source_rect = self._scene.get_page_rect(idx)
                if not source_rect.isEmpty():
                    self._paint_annotations_overlay(pixmap, idx, source_rect)
            # ---------------------------
            
            self._cards[idx].set_thumbnail(pixmap)

    def _paint_annotations_overlay(
        self: 'SidebarWidget', pixmap: QPixmap, page_idx: int, source_rect: QRectF
    ) -> None:
        """Paint annotation items directly onto the thumbnail pixmap.

        Instead of scene.render() (which traverses ALL scene items including
        tiles, placeholders, and handles), this iterates only the per-page
        annotation registries and calls each item's paint() with a
        transformed painter.  O(annotations_on_page) vs O(all_scene_items).
        """
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        # Collect all annotation items for this page
        items = []
        for registry in (
            self._scene._stroke_items,
            self._scene._highlight_items,
            self._scene._text_box_items,
            self._scene._shape_items,
            self._scene._image_items,
        ):
            items.extend(registry.get(page_idx, []))

        if not items:
            return

        overlay = QPixmap(pixmap.size())
        overlay.setDevicePixelRatio(pixmap.devicePixelRatio())
        overlay.fill(Qt.GlobalColor.transparent)

        dpr = overlay.devicePixelRatio()
        target_w = overlay.width() / dpr
        target_h = overlay.height() / dpr

        sx = target_w / source_rect.width()
        sy = target_h / source_rect.height()

        self._scene._is_rendering_thumbnail = True
        try:
            painter = QPainter(overlay)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            option = QStyleOptionGraphicsItem()

            for item in items:
                try:
                    item_pos = item.pos()
                    # Map item position from scene coords to overlay coords
                    local_x = (item_pos.x() - source_rect.x()) * sx
                    local_y = (item_pos.y() - source_rect.y()) * sy

                    painter.save()
                    painter.translate(local_x, local_y)
                    painter.scale(sx, sy)

                    # Apply item rotation if any
                    rotation = item.rotation()
                    if rotation != 0.0:
                        tp = item.transformOriginPoint()
                        painter.translate(tp.x(), tp.y())
                        painter.rotate(rotation)
                        painter.translate(-tp.x(), -tp.y())

                    item.paint(painter, option, None)
                    painter.restore()
                except RuntimeError:
                    # C++ object may have been deleted
                    pass

            painter.end()
        finally:
            self._scene._is_rendering_thumbnail = False

        p2 = QPainter(pixmap)
        p2.setRenderHint(QPainter.RenderHint.Antialiasing)
        p2.drawPixmap(0, 0, overlay)
        p2.end()
